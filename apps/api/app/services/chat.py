"""Forced-citation chat orchestration (M1-06) + session persistence (M1-09)."""

from __future__ import annotations

import json
import re
from sqlalchemy.orm import Session

from app.knowledge.search import search_chunks
from app.llm.gateway import LLMGateway
from app.models import Conversation, Message

REFUSAL_PATTERNS = [
    re.compile(r"虚开|偷税|逃税|骗税|隐匿收入|伪造发票|怎么规避稽查"),
]


def _is_refusal(query: str) -> bool:
    return any(p.search(query) for p in REFUSAL_PATTERNS)


def answer_question(
    db: Session,
    query: str,
    *,
    conversation_id: int | None = None,
    top_k: int = 5,
) -> dict:
    gateway = LLMGateway()

    if conversation_id is None:
        conv = Conversation(user_id=None, enterprise_id=None)
        db.add(conv)
        db.flush()
        conversation_id = conv.id
    else:
        conv = db.get(Conversation, conversation_id)
        if conv is None:
            conv = Conversation(user_id=None, enterprise_id=None)
            db.add(conv)
            db.flush()
            conversation_id = conv.id

    db.add(
        Message(
            conversation_id=conversation_id,
            role="user",
            content=query,
            citation_ids=None,
        )
    )

    if _is_refusal(query):
        payload = {
            "conversation_id": conversation_id,
            "state": "refused",
            "conclusion": "无法提供可能涉及违法违规的操作建议。如需合规咨询，请使用转专家。",
            "uncertainty": True,
            "boundary": "平台拒绝协助偷逃税、虚开发票等行为。",
            "citations": [],
            "citation_ids": [],
            "disclaimer": _disclaimer_short(),
            "expert_cta": True,
            "meta": {"refusal": True},
        }
        db.add(
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content=json.dumps(payload, ensure_ascii=False),
                citation_ids="",
            )
        )
        db.commit()
        return payload

    hits, search_meta = search_chunks(db, query, top_k=top_k, only_active=True)
    # filter weak hits
    hits = [h for h in hits if h.keyword_score > 0 or h.semantic_score > 0.05]

    if not hits:
        payload = {
            "conversation_id": conversation_id,
            "state": "uncertain",
            "conclusion": "依据当前知识库，我无法给出有足够法规支撑的确定结论（原因：无检索命中）。你可以补充纳税人类型/所属地区/业务事实，或选择转专家。",
            "uncertainty": True,
            "boundary": "无引用不得给出确定性结论。",
            "citations": [],
            "citation_ids": [],
            "disclaimer": _disclaimer_short(),
            "expert_cta": True,
            "meta": {"search": search_meta, "forced_citation": True},
        }
        db.add(
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content=json.dumps(payload, ensure_ascii=False),
                citation_ids="",
            )
        )
        db.commit()
        return payload

    context_lines = []
    citations = []
    for h in hits:
        context_lines.append(
            f"[chunk_id={h.chunk_id}] {h.doc_no or h.corpus_id} {h.clause_no or ''}\n{h.body}"
        )
        citations.append(
            {
                "chunk_id": h.chunk_id,
                "clause_id": h.clause_id,
                "corpus_id": h.corpus_id,
                "doc_no": h.doc_no,
                "clause_no": h.clause_no,
                "body": h.body,
                "source_url": h.source_url,
                "score": h.score,
            }
        )
    context_block = "\n\n---\n\n".join(context_lines)
    llm_payload, llm_meta = gateway.complete_json(query, context_block)

    uncertainty = bool(llm_payload.get("uncertainty", False))
    conclusion = str(llm_payload.get("conclusion") or "").strip()
    if not conclusion:
        uncertainty = True
        conclusion = "未能生成有效结论，请转专家或补充问题。"

    # FORCE: never allow deterministic answer without citations
    citation_ids = [c["chunk_id"] for c in citations]
    if not citation_ids:
        uncertainty = True

    state = "uncertain" if uncertainty or llm_payload.get("refusal") else "answered"
    payload = {
        "conversation_id": conversation_id,
        "state": state,
        "conclusion": conclusion,
        "uncertainty": uncertainty,
        "boundary": llm_payload.get("boundary")
        or "请以主管税务机关口径及正式文件全文为准。",
        "citations": citations,
        "citation_ids": citation_ids,
        "disclaimer": _disclaimer_short(),
        "expert_cta": True,
        "meta": {
            "search": search_meta,
            "llm": llm_meta,
            "forced_citation": True,
            "prompt_version": llm_meta.get("prompt_version"),
        },
    }
    db.add(
        Message(
            conversation_id=conversation_id,
            role="assistant",
            content=json.dumps(
                {
                    "conclusion": conclusion,
                    "uncertainty": uncertainty,
                    "citation_ids": citation_ids,
                },
                ensure_ascii=False,
            ),
            citation_ids=",".join(str(i) for i in citation_ids),
        )
    )
    db.commit()
    return payload


def export_conversation(db: Session, conversation_id: int) -> dict | None:
    conv = db.get(Conversation, conversation_id)
    if not conv:
        return None
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id)
        .all()
    )
    return {
        "conversation_id": conversation_id,
        "enterprise_id": conv.enterprise_id,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "citation_ids": [
                    int(x) for x in (m.citation_ids or "").split(",") if x.strip().isdigit()
                ],
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ],
    }


def _disclaimer_short() -> str:
    from pathlib import Path

    from app.config import get_settings

    path = Path(get_settings().disclaimer_path)
    default = "本回答仅供参考，不构成税务鉴证或申报依据。"
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8")
    marker = "## 1. 答案页固定免责（短版 · UI 页脚）"
    if marker not in text:
        return default
    chunk = text.split(marker, 1)[1].split("## 2.", 1)[0]
    lines = [ln.strip("> ").strip() for ln in chunk.splitlines() if ln.strip().startswith(">")]
    return " ".join(lines) if lines else default
