"""FastAPI entry — health, meta, empty shell for chat."""

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, init_db
from app.models import Clause, Policy, PublishStatus

app = FastAPI(title="TaxAIAgent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": get_settings().app_env}


@app.get("/v1/meta/disclaimer")
def disclaimer() -> dict:
    """Load short disclaimer from ops single source when available."""
    settings = get_settings()
    path = Path(settings.disclaimer_path)
    short = (
        "本回答仅供参考，不构成税务鉴证或申报依据。重要决策请咨询持证专业人士或转专家。"
    )
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
    return {
        "policies": policies,
        "clauses_published": published,
        "clauses_draft": drafts,
        "llm_configured": bool(get_settings().llm_api_key),
    }


@app.get("/v1/chat/ping")
def chat_ping() -> dict:
    """Placeholder until M1-06 forced-citation orchestration lands."""
    return {
        "message": "chat not enabled yet — complete M1-03/M1-06",
        "forced_citation": True,
    }
