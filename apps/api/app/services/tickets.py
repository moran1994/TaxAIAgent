"""Expert ticket lifecycle, mock pay, ledger (M2)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    LedgerEntry,
    Message,
    Ticket,
    TicketStatus,
    TicketType,
    User,
)

# price tiers (cents)
PLANS = {
    "standard": {"price_cents": 9900, "label": "标准书面答 ¥99"},
    "complex": {"price_cents": 19900, "label": "复杂书面答 ¥199"},
}

EXPERT_RATIO_DEFAULT = 0.70
FEE_RATE = 0.006  # mock channel fee 0.6%

TRANSITIONS: dict[str, set[str]] = {
    TicketStatus.pending_payment.value: {
        TicketStatus.pending_accept.value,
        TicketStatus.cancelled.value,
    },
    TicketStatus.pending_accept.value: {
        TicketStatus.in_progress.value,
        TicketStatus.cancelled.value,
        TicketStatus.refunded.value,
    },
    TicketStatus.in_progress.value: {
        TicketStatus.completed.value,
        TicketStatus.refunded.value,
        TicketStatus.cancelled.value,
    },
    TicketStatus.completed.value: {TicketStatus.refunded.value},
    TicketStatus.refunded.value: set(),
    TicketStatus.cancelled.value: set(),
}


def ensure_demo_expert(db: Session) -> User:
    expert = db.query(User).filter(User.phone == "expert-demo").one_or_none()
    if expert:
        return expert
    expert = User(phone="expert-demo", display_name="试接专家甲", role="expert")
    db.add(expert)
    db.flush()
    return expert


def _transition(ticket: Ticket, new_status: str) -> None:
    allowed = TRANSITIONS.get(ticket.status, set())
    if new_status not in allowed:
        raise ValueError(f"illegal transition {ticket.status} -> {new_status}")
    ticket.status = new_status
    ticket.updated_at = datetime.utcnow()


def build_context_summary(db: Session, conversation_id: int | None) -> str:
    if not conversation_id:
        return ""
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(6)
        .all()
    )
    msgs = list(reversed(msgs))
    parts = []
    for m in msgs:
        parts.append(f"[{m.role}] {m.content[:500]}")
    return "\n\n".join(parts)


def create_ticket(
    db: Session,
    *,
    conversation_id: int | None,
    plan_code: str = "standard",
    ticket_type: str = TicketType.expert_consult.value,
    user_id: int | None = None,
) -> Ticket:
    if plan_code not in PLANS:
        raise ValueError("unknown plan_code")
    if ticket_type not in {t.value for t in TicketType}:
        raise ValueError("unknown ticket_type")
    summary = build_context_summary(db, conversation_id)
    ticket = Ticket(
        conversation_id=conversation_id,
        user_id=user_id,
        ticket_type=ticket_type,
        status=TicketStatus.pending_payment.value,
        price_cents=PLANS[plan_code]["price_cents"],
        plan_code=plan_code,
        context_summary=summary,
    )
    db.add(ticket)
    db.flush()
    db.add(
        AuditLog(
            actor="user",
            action="ticket_created",
            entity_type="ticket",
            entity_id=str(ticket.id),
            detail=f"plan={plan_code};price={ticket.price_cents}",
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def mock_pay(db: Session, ticket_id: int, *, fail: bool = False) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise LookupError("ticket not found")
    if fail:
        raise ValueError("mock payment failed")
    if ticket.status != TicketStatus.pending_payment.value:
        raise ValueError("ticket not awaiting payment")
    _transition(ticket, TicketStatus.pending_accept.value)
    ticket.payment_channel = "mock_wechat"
    ticket.sla_deadline = datetime.utcnow() + timedelta(hours=24)
    db.add(
        AuditLog(
            actor="pay",
            action="mock_pay_success",
            entity_type="ticket",
            entity_id=str(ticket.id),
            detail=ticket.payment_channel,
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def claim_ticket(db: Session, ticket_id: int, expert: User) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise LookupError("ticket not found")
    if ticket.status != TicketStatus.pending_accept.value:
        raise ValueError("ticket not claimable")
    if ticket.expert_id is not None:
        raise ValueError("ticket already claimed")
    _transition(ticket, TicketStatus.in_progress.value)
    ticket.expert_id = expert.id
    db.add(
        AuditLog(
            actor=expert.display_name or str(expert.id),
            action="ticket_claim",
            entity_type="ticket",
            entity_id=str(ticket.id),
            detail=None,
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def submit_reply(
    db: Session,
    ticket_id: int,
    expert: User,
    reply: str,
    *,
    suggest_reflow: bool = False,
) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise LookupError("ticket not found")
    if ticket.expert_id != expert.id:
        raise ValueError("not your ticket")
    if ticket.status != TicketStatus.in_progress.value:
        raise ValueError("ticket not in progress")
    if not reply.strip():
        raise ValueError("empty reply")
    ticket.expert_reply = reply.strip()
    ticket.suggest_reflow = suggest_reflow
    _transition(ticket, TicketStatus.completed.value)
    _write_ledger(db, ticket)
    db.add(
        AuditLog(
            actor=expert.display_name or str(expert.id),
            action="ticket_complete",
            entity_type="ticket",
            entity_id=str(ticket.id),
            detail=f"reflow={suggest_reflow}",
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def _write_ledger(db: Session, ticket: Ticket, expert_ratio: float = EXPERT_RATIO_DEFAULT) -> LedgerEntry:
    existing = db.query(LedgerEntry).filter(LedgerEntry.ticket_id == ticket.id).one_or_none()
    if existing:
        return existing
    gross = ticket.price_cents
    fee = int(round(gross * FEE_RATE))
    alloc = gross - fee
    expert_share = int(round(alloc * expert_ratio))
    platform_share = alloc - expert_share
    row = LedgerEntry(
        ticket_id=ticket.id,
        gross_cents=gross,
        fee_cents=fee,
        expert_share_cents=expert_share,
        platform_share_cents=platform_share,
        expert_ratio=expert_ratio,
    )
    db.add(row)
    db.flush()
    return row


def rate_ticket(db: Session, ticket_id: int, rating: int, comment: str | None = None) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise LookupError("ticket not found")
    if ticket.status != TicketStatus.completed.value:
        raise ValueError("rate only completed tickets")
    if rating < 1 or rating > 5:
        raise ValueError("rating 1-5")
    ticket.rating = rating
    ticket.rating_comment = comment
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    return ticket


def request_refund(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise LookupError("ticket not found")
    if ticket.status in {
        TicketStatus.cancelled.value,
        TicketStatus.pending_payment.value,
    }:
        raise ValueError("cannot refund in current status")
    ticket.refund_requested = True
    ticket.updated_at = datetime.utcnow()
    db.add(
        AuditLog(
            actor="user",
            action="refund_request",
            entity_type="ticket",
            entity_id=str(ticket.id),
            detail=None,
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def approve_refund(db: Session, ticket_id: int, actor: str = "ops") -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise LookupError("ticket not found")
    if ticket.status == TicketStatus.refunded.value:
        return ticket
    _transition(ticket, TicketStatus.refunded.value)
    # reverse ledger: zero platform/expert by adding offsetting row semantics — mark shares 0
    led = db.query(LedgerEntry).filter(LedgerEntry.ticket_id == ticket.id).one_or_none()
    if led:
        led.expert_share_cents = 0
        led.platform_share_cents = 0
        led.fee_cents = led.gross_cents  # treat as reversed for MVP export clarity
    db.add(
        AuditLog(
            actor=actor,
            action="refund_approved",
            entity_type="ticket",
            entity_id=str(ticket.id),
            detail="ledger zeroed",
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def ticket_to_dict(ticket: Ticket, *, include_context: bool = False) -> dict:
    sla_overdue = bool(
        ticket.sla_deadline
        and ticket.status in {TicketStatus.pending_accept.value, TicketStatus.in_progress.value}
        and datetime.utcnow() > ticket.sla_deadline
    )
    data = {
        "id": ticket.id,
        "conversation_id": ticket.conversation_id,
        "status": ticket.status,
        "ticket_type": ticket.ticket_type,
        "plan_code": ticket.plan_code,
        "price_cents": ticket.price_cents,
        "price_yuan": round(ticket.price_cents / 100, 2),
        "expert_id": ticket.expert_id,
        "sla_deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
        "sla_overdue": sla_overdue,
        "expert_reply": ticket.expert_reply,
        "suggest_reflow": ticket.suggest_reflow,
        "rating": ticket.rating,
        "rating_comment": ticket.rating_comment,
        "refund_requested": ticket.refund_requested,
        "payment_channel": ticket.payment_channel,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
    }
    if include_context:
        data["context_summary"] = ticket.context_summary
    return data
