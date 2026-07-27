#!/usr/bin/env python3
"""Golden-set eval gate (M1-08) — retrieval + optional clause_ref hit.

Loads `knowledge/m0/golden-eval-seed.json`.

Definitions (MVP):
- corpus_hit: top-5 search returns ≥1 chunk from expect_corpus
- clause_ref_hit: top-8 matches ≥1 of clause_ref entries (`corpus_id:clause_no`)
- hard_hallucination: chat state=answered with empty citation_ids
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT))

from app.db import SessionLocal, init_db  # noqa: E402
from app.knowledge.search import search_chunks  # noqa: E402
from app.services.chat import answer_question  # noqa: E402

SEED_PATH = REPO / "knowledge" / "m0" / "golden-eval-seed.json"


def load_golden() -> list[dict]:
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return data["items"]


def parse_ref(ref: str) -> tuple[str, str]:
    corpus, _, clause = ref.partition(":")
    return corpus, clause


def clause_ref_hit(hits, refs: list[str]) -> bool:
    if not refs:
        return True
    keys = {(h.corpus_id, h.clause_no) for h in hits}
    for ref in refs:
        corpus, clause = parse_ref(ref)
        if (corpus, clause) in keys:
            return True
    return False


def main() -> None:
    golden = load_golden()
    init_db()
    db = SessionLocal()
    rows = []
    try:
        for g in golden:
            hits5, meta = search_chunks(db, g["q"], top_k=5)
            hits8, _ = search_chunks(db, g["q"], top_k=8)
            hit_corpus = {h.corpus_id for h in hits5}
            corpus_ok = bool(hit_corpus & set(g["expect_corpus"]))
            refs = g.get("clause_ref") or []
            ref_ok = clause_ref_hit(hits8, refs)
            ans = answer_question(db, g["q"], top_k=5)
            hard_halluc = ans.get("state") == "answered" and not ans.get("citation_ids")
            rows.append(
                {
                    "id": g["id"],
                    "ok": corpus_ok,
                    "clause_ref_ok": ref_ok,
                    "hit_corpus": sorted(hit_corpus),
                    "hit_clauses_top5": [f"{h.corpus_id}:{h.clause_no}" for h in hits5],
                    "hit_clauses_top8": [f"{h.corpus_id}:{h.clause_no}" for h in hits8],
                    "expect": g["expect_corpus"],
                    "clause_ref": refs,
                    "state": ans.get("state"),
                    "citation_ids": ans.get("citation_ids"),
                    "hard_hallucination": hard_halluc,
                    "latency_ms": meta.get("latency_ms"),
                    "tags": g.get("tags") or [],
                }
            )
            print(
                f"{g['id']}: corpus={'PASS' if corpus_ok else 'FAIL'} "
                f"clause_ref={'PASS' if ref_ok else 'FAIL'} "
                f"state={ans.get('state')} cites={ans.get('citation_ids')}"
            )
    finally:
        db.close()

    n = len(rows)
    recall = sum(1 for r in rows if r["ok"]) / n if n else 0
    ref_rate = sum(1 for r in rows if r["clause_ref_ok"]) / n if n else 0
    halluc = sum(1 for r in rows if r["hard_hallucination"]) / n if n else 0
    gate_ok = recall >= 0.7 and halluc <= 0.05
    report = {
        "seed": str(SEED_PATH.relative_to(REPO)),
        "definition": {
            "corpus_hit": "top5 命中期望 corpus_id 任一",
            "clause_ref_hit": "top8 命中 clause_ref（corpus_id:clause_no）任一",
            "hard_hallucination": "answered 且 citation_ids 为空",
            "release_gate": "corpus_recall>=0.70 and hard_hallucination<=0.05",
        },
        "metrics": {
            "n": n,
            "retrieval_hit_rate": round(recall, 4),
            "clause_ref_hit_rate": round(ref_rate, 4),
            "hard_hallucination_rate": round(halluc, 4),
            "gate_ok": gate_ok,
        },
        "rows": rows,
    }
    out = REPO / "knowledge" / "m1" / "qa" / "golden_eval_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False))
    print("wrote", out)
    raise SystemExit(0 if gate_ok else 2)


if __name__ == "__main__":
    main()
