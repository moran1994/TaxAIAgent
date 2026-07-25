"""Hybrid retrieval: keyword + char-ngram lexical 'vector' scores, RRF fusion."""

from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session, joinedload

from app.models import Chunk, Clause, Policy, PublishStatus


def tokenize(text: str) -> list[str]:
    text = re.sub(r"\s+", "", text.lower())
    if not text:
        return []
    grams = [text[i : i + 2] for i in range(max(0, len(text) - 1))]
    # keep longer tokens (文号 fragments, tags)
    extras = re.findall(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{2,}", text)
    return grams + extras + list(text)


@dataclass
class SearchHit:
    chunk_id: int
    clause_id: int
    corpus_id: str
    doc_no: str | None
    clause_no: str | None
    body: str
    source_url: str | None
    tags: str | None
    score: float
    keyword_score: float
    semantic_score: float


def _kw_score(query_tokens: set[str], doc_tokens: Counter[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    hits = sum(doc_tokens[t] for t in query_tokens if t in doc_tokens)
    # prefer docs covering more unique query tokens
    cover = sum(1 for t in query_tokens if t in doc_tokens) / max(1, len(query_tokens))
    return hits * 0.3 + cover


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def search_chunks(
    db: Session,
    query: str,
    *,
    top_k: int = 5,
    only_active: bool = True,
    status: str = PublishStatus.published.value,
) -> tuple[list[SearchHit], dict]:
    t0 = time.perf_counter()
    q = (
        db.query(Chunk)
        .join(Clause)
        .join(Policy)
        .options(joinedload(Chunk.clause).joinedload(Clause.policy))
        .filter(Chunk.status == status, Clause.status == status)
    )
    if only_active:
        q = q.filter(Policy.is_active.is_(True))
    rows = q.all()

    q_tokens = tokenize(query)
    q_set = set(q_tokens)
    q_counter = Counter(q_tokens)

    scored: list[tuple[float, float, float, Chunk]] = []
    for ch in rows:
        doc_tokens = tokenize(ch.body + " " + (ch.clause.tax_tags or "") + " " + (ch.clause.clause_no or ""))
        doc_counter = Counter(doc_tokens)
        kw = _kw_score(q_set, doc_counter)
        sem = _cosine(q_counter, doc_counter)
        # boost exact clause/doc_no substring
        boost = 0.0
        body = ch.body
        qraw = query.strip()
        if qraw and qraw in body:
            boost += 0.5
        # phrase boosts for multi-char Chinese keywords in query
        for m in re.findall(r"[\u4e00-\u9fff]{3,}", qraw):
            if m in body:
                boost += 0.35
        if ch.clause.policy.doc_no and any(
            part in query for part in re.findall(r"\d+", ch.clause.policy.doc_no or "")
        ):
            boost += 0.15
        # tag overlap
        tags = ch.clause.tax_tags or ""
        for tag in tags.split(","):
            if tag and tag in qraw:
                boost += 0.25
        scored.append((kw + boost, sem, kw + sem + boost, ch))

    # rank lists for RRF
    by_kw = sorted(scored, key=lambda x: x[0], reverse=True)
    by_sem = sorted(scored, key=lambda x: x[1], reverse=True)
    rrf: dict[int, float] = {}
    kw_map: dict[int, float] = {}
    sem_map: dict[int, float] = {}
    for rank, (kw, sem, _tot, ch) in enumerate(by_kw[:50]):
        rrf[ch.id] = rrf.get(ch.id, 0.0) + 1.0 / (60 + rank)
        kw_map[ch.id] = kw
    for rank, (kw, sem, _tot, ch) in enumerate(by_sem[:50]):
        rrf[ch.id] = rrf.get(ch.id, 0.0) + 1.0 / (60 + rank)
        sem_map[ch.id] = sem

    id_to_chunk = {ch.id: ch for *_, ch in scored}
    ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:top_k]
    hits: list[SearchHit] = []
    for cid, score in ranked:
        ch = id_to_chunk[cid]
        # drop near-zero noise
        if score < 1e-6 and kw_map.get(cid, 0) <= 0:
            continue
        hits.append(
            SearchHit(
                chunk_id=ch.id,
                clause_id=ch.clause_id,
                corpus_id=ch.clause.policy.corpus_id,
                doc_no=ch.clause.policy.doc_no,
                clause_no=ch.clause.clause_no,
                body=ch.body,
                source_url=ch.clause.policy.source_url,
                tags=ch.clause.tax_tags,
                score=round(score, 6),
                keyword_score=round(kw_map.get(cid, 0.0), 4),
                semantic_score=round(sem_map.get(cid, 0.0), 4),
            )
        )

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    meta = {
        "latency_ms": latency_ms,
        "candidates": len(rows),
        "returned": len(hits),
        "only_active": only_active,
        "method": "rrf(keyword+char_ngram)",
    }
    return hits, meta
