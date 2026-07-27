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
from app.models import AuditLog, Chunk, Clause, LedgerEntry, Policy, PublishStatus, Ticket
from app.services.chat import answer_question, export_conversation
from app.services import tickets as ticket_svc

app = FastAPI(title="TaxAIAgent API", version="0.3.0")

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


class TicketCreate(BaseModel):
    conversation_id: int | None = None
    plan_code: str = "standard"
    ticket_type: str = "expert_consult"


class ExpertReply(BaseModel):
    reply: str = Field(min_length=1)
    suggest_reflow: bool = False


class RateBody(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


@app.on_event("startup")
def on_startup() -> None:
    from app.db import SessionLocal

    init_db()
    db = SessionLocal()
    try:
        ticket_svc.ensure_demo_expert(db)
        db.commit()
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": get_settings().app_env, "version": "0.4.0"}


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


@app.get("/v1/meta/payment")
def payment_meta() -> dict:
    from app.services.payment import get_payment_provider

    settings = get_settings()
    p = get_payment_provider()
    return {
        "provider": p.name,
        "configured_provider": settings.payment_provider,
        "wechat_mch_configured": bool(settings.wechat_mch_id),
    }


@app.get("/v1/tickets/plans")
def ticket_plans() -> dict:
    return {"plans": ticket_svc.PLANS, "expert_ratio_default": ticket_svc.EXPERT_RATIO_DEFAULT}


@app.post("/v1/tickets")
def create_ticket(body: TicketCreate, db: Session = Depends(get_db)) -> dict:
    try:
        t = ticket_svc.create_ticket(
            db,
            conversation_id=body.conversation_id,
            plan_code=body.plan_code,
            ticket_type=body.ticket_type,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ticket_svc.ticket_to_dict(t, include_context=True)


@app.post("/v1/tickets/{ticket_id}/pay/mock")
def pay_ticket_mock(
    ticket_id: int,
    fail: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    try:
        t = ticket_svc.mock_pay(db, ticket_id, fail=fail)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ticket_svc.ticket_to_dict(t)


@app.get("/v1/tickets/{ticket_id}")
def get_ticket(ticket_id: int, db: Session = Depends(get_db)) -> dict:
    t = db.get(Ticket, ticket_id)
    if not t:
        raise HTTPException(404, "ticket not found")
    return ticket_svc.ticket_to_dict(t, include_context=True)


@app.get("/v1/expert/queue")
def expert_queue(db: Session = Depends(get_db)) -> dict:
    ticket_svc.ensure_demo_expert(db)
    rows = (
        db.query(Ticket)
        .filter(Ticket.status == "pending_accept")
        .order_by(Ticket.id)
        .all()
    )
    return {"items": [ticket_svc.ticket_to_dict(t, include_context=True) for t in rows]}


@app.post("/v1/expert/tickets/{ticket_id}/claim")
def expert_claim(ticket_id: int, db: Session = Depends(get_db)) -> dict:
    expert = ticket_svc.ensure_demo_expert(db)
    try:
        t = ticket_svc.claim_ticket(db, ticket_id, expert)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return ticket_svc.ticket_to_dict(t, include_context=True)


@app.post("/v1/expert/tickets/{ticket_id}/reply")
def expert_reply(ticket_id: int, body: ExpertReply, db: Session = Depends(get_db)) -> dict:
    expert = ticket_svc.ensure_demo_expert(db)
    try:
        t = ticket_svc.submit_reply(
            db,
            ticket_id,
            expert,
            body.reply,
            suggest_reflow=body.suggest_reflow,
        )
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ticket_svc.ticket_to_dict(t)


@app.get("/v1/expert/mine")
def expert_mine(db: Session = Depends(get_db)) -> dict:
    expert = ticket_svc.ensure_demo_expert(db)
    rows = (
        db.query(Ticket)
        .filter(Ticket.expert_id == expert.id)
        .order_by(Ticket.id.desc())
        .limit(50)
        .all()
    )
    return {"expert": {"id": expert.id, "name": expert.display_name}, "items": [ticket_svc.ticket_to_dict(t) for t in rows]}


@app.post("/v1/tickets/{ticket_id}/rate")
def rate_ticket(ticket_id: int, body: RateBody, db: Session = Depends(get_db)) -> dict:
    try:
        t = ticket_svc.rate_ticket(db, ticket_id, body.rating, body.comment)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ticket_svc.ticket_to_dict(t)


@app.post("/v1/tickets/{ticket_id}/refund/request")
def refund_request(ticket_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        t = ticket_svc.request_refund(db, ticket_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ticket_svc.ticket_to_dict(t)


@app.post("/v1/tickets/{ticket_id}/refund/approve")
def refund_approve(ticket_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        t = ticket_svc.approve_refund(db, ticket_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ticket_svc.ticket_to_dict(t)


@app.get("/v1/ledger.csv")
def ledger_csv(db: Session = Depends(get_db)):
    from fastapi.responses import PlainTextResponse

    rows = db.query(LedgerEntry).order_by(LedgerEntry.id).all()
    lines = [
        "ticket_id,gross_cents,fee_cents,expert_share_cents,platform_share_cents,expert_ratio,created_at"
    ]
    for r in rows:
        lines.append(
            f"{r.ticket_id},{r.gross_cents},{r.fee_cents},{r.expert_share_cents},"
            f"{r.platform_share_cents},{r.expert_ratio},{r.created_at.isoformat() if r.created_at else ''}"
        )
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/csv")


@app.get("/v1/metrics/kr")
def metrics_kr(db: Session = Depends(get_db)) -> dict:
    """Minimal Concierge KR snapshot (M3-01)."""
    from pathlib import Path
    import json

    paid = db.query(Ticket).filter(Ticket.status != "pending_payment").count()
    completed = db.query(Ticket).filter(Ticket.status == "completed").count()
    rated = db.query(Ticket).filter(Ticket.rating.isnot(None)).all()
    avg_rating = round(sum(t.rating for t in rated) / len(rated), 2) if rated else None
    ledgers = db.query(LedgerEntry).all()
    gross = sum(x.gross_cents for x in ledgers)
    platform = sum(x.platform_share_cents for x in ledgers)
    fee = sum(x.fee_cents for x in ledgers)
    margin = None
    if gross:
        margin = round((platform) / gross, 4)

    golden_path = (
        Path(__file__).resolve().parents[3]
        / "knowledge"
        / "m1"
        / "qa"
        / "golden_eval_report.json"
    )
    golden = {}
    if golden_path.exists():
        golden = json.loads(golden_path.read_text(encoding="utf-8")).get("metrics", {})

    return {
        "KR1_retrieval_hit_rate": golden.get("retrieval_hit_rate"),
        "KR1_gate_ok": golden.get("gate_ok"),
        "KR2_paid_or_advanced_tickets": paid,
        "KR2_completed_tickets": completed,
        "KR3_avg_rating": avg_rating,
        "KR4_platform_share_over_gross": margin,
        "ledger_gross_cents": gross,
        "ledger_platform_cents": platform,
        "ledger_fee_cents": fee,
        "note": "转单点击率需前端埋点汇聚；SLA 见 ticket.sla_overdue",
    }
