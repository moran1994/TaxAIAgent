"""FastAPI entry — health, search, chat, knowledge ops."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, init_db
from app.knowledge.search import search_chunks
from app.llm.gateway import LLMGateway, load_prompt
from app.models import AuditLog, Chunk, Clause, Policy, PublishStatus
from app.services.chat import answer_question, export_conversation

app = FastAPI(title="TaxAIAgent API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    top_k: int = 5


class ClauseStatusUpdate(BaseModel):
    status: str
    actor: str = "ops"


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": get_settings().app_env, "version": "0.2.0"}


@app.get("/v1/meta/disclaimer")
def disclaimer() -> dict:
    settings = get_settings()
    path = Path(settings.disclaimer_path)
    short = "本回答仅供参考，不构成税务鉴证或申报依据。重要决策请咨询持证专业人士或转专家。"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        marker = "## 1. 答案页固定免责（短版 · UI 页脚）"
        if marker in text:
            chunk = text.split(marker, 1)[1].split("## 2.", 1)[0]
            lines = [
                ln.strip("> ").strip()
                for ln in chunk.splitlines()
                if ln.strip().startswith(">")
            ]
            if lines:
                short = " ".join(lines)
    return {"disclaimer_short": short, "source": "ops/m0/disclaimer-and-refusal.md"}


@app.get("/v1/meta/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    policies = db.scalar(select(func.count()).select_from(Policy)) or 0
    published = db.scalar(
        select(func.count())
        .select_from(Clause)
        .where(Clause.status == PublishStatus.published.value)
    ) or 0
    drafts = db.scalar(
        select(func.count())
        .select_from(Clause)
        .where(Clause.status == PublishStatus.draft.value)
    ) or 0
    chunks = db.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.status == PublishStatus.published.value)
    ) or 0
    return {
        "policies": policies,
        "clauses_published": published,
        "clauses_draft": drafts,
        "chunks_published": chunks,
        "llm_configured": bool(get_settings().llm_api_key),
        "prompt_version": load_prompt().get("version", "vat_qa_v1"),
    }


@app.get("/v1/meta/prompt")
def prompt_meta() -> dict:
    p = load_prompt()
    return {
        "version": p.get("version"),
        "path": p.get("_path"),
        "llm_configured": LLMGateway().configured,
    }


@app.get("/v1/knowledge/search")
def knowledge_search(
    q: str = Query(min_length=1, max_length=500),
    top_k: int = Query(default=5, ge=1, le=20),
    only_active: bool = True,
    db: Session = Depends(get_db),
) -> dict:
    hits, meta = search_chunks(db, q, top_k=top_k, only_active=only_active)
    return {
        "query": q,
        "meta": meta,
        "results": [
            {
                "chunk_id": h.chunk_id,
                "clause_id": h.clause_id,
                "corpus_id": h.corpus_id,
                "doc_no": h.doc_no,
                "clause_no": h.clause_no,
                "body": h.body,
                "source_url": h.source_url,
                "tags": h.tags,
                "score": h.score,
                "keyword_score": h.keyword_score,
                "semantic_score": h.semantic_score,
            }
            for h in hits
        ],
    }


@app.get("/v1/knowledge/clauses")
def list_clauses(
    corpus_id: str | None = None,
    status: str = "published",
    limit: int = 20,
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(Clause).join(Policy)
    if status:
        q = q.filter(Clause.status == status)
    if corpus_id:
        q = q.filter(Policy.corpus_id == corpus_id)
    rows = q.order_by(Policy.corpus_id, Clause.id).limit(min(limit, 100)).all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": c.id,
                "corpus_id": c.policy.corpus_id,
                "doc_no": c.policy.doc_no,
                "clause_no": c.clause_no,
                "tags": c.tax_tags,
                "status": c.status,
                "preview": c.body[:160].replace("\n", " "),
                "body": c.body,
            }
            for c in rows
        ],
    }


@app.get("/v1/knowledge/clauses/{clause_id}")
def get_clause(clause_id: int, db: Session = Depends(get_db)) -> dict:
    c = db.get(Clause, clause_id)
    if not c:
        raise HTTPException(404, "clause not found")
    return {
        "id": c.id,
        "corpus_id": c.policy.corpus_id,
        "doc_no": c.policy.doc_no,
        "clause_no": c.clause_no,
        "tags": c.tax_tags,
        "status": c.status,
        "body": c.body,
        "source_url": c.policy.source_url,
    }


@app.patch("/v1/knowledge/clauses/{clause_id}/status")
def update_clause_status(
    clause_id: int,
    body: ClauseStatusUpdate,
    db: Session = Depends(get_db),
) -> dict:
    allowed = {s.value for s in PublishStatus}
    if body.status not in allowed:
        raise HTTPException(400, f"status must be one of {sorted(allowed)}")
    c = db.get(Clause, clause_id)
    if not c:
        raise HTTPException(404, "clause not found")
    old = c.status
    c.status = body.status
    for ch in c.chunks:
        ch.status = body.status
    db.add(
        AuditLog(
            actor=body.actor,
            action="clause_status_update",
            entity_type="clause",
            entity_id=str(clause_id),
            detail=f"{old} -> {body.status}",
        )
    )
    db.commit()
    return {"id": clause_id, "status": c.status, "previous": old}


@app.get("/v1/knowledge/audit")
def list_audit(limit: int = 50, db: Session = Depends(get_db)) -> dict:
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 200)).all()
    return {
        "items": [
            {
                "id": a.id,
                "actor": a.actor,
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "detail": a.detail,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in rows
        ]
    }


@app.post("/v1/chat")
def chat(req: ChatRequest, db: Session = Depends(get_db)) -> dict:
    return answer_question(
        db,
        req.query.strip(),
        conversation_id=req.conversation_id,
        top_k=req.top_k,
    )


@app.get("/v1/conversations/{conversation_id}/export")
def conversation_export(conversation_id: int, db: Session = Depends(get_db)) -> dict:
    data = export_conversation(db, conversation_id)
    if not data:
        raise HTTPException(404, "conversation not found")
    return data
