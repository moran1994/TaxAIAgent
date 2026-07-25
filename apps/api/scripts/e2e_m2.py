#!/usr/bin/env python3
"""M2-07 end-to-end golden path: chat -> pay -> claim -> reply -> rate -> ledger."""

from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import LedgerEntry, Ticket  # noqa: E402
from app.services.chat import answer_question  # noqa: E402
from app.services import tickets as ticket_svc  # noqa: E402


def main() -> None:
    init_db()
    db = SessionLocal()
    checks = []
    try:
        expert = ticket_svc.ensure_demo_expert(db)
        db.commit()

        ans = answer_question(db, "帮我虚开发票少交税")
        checks.append(("refuse_illegal", ans["state"] == "refused"))

        ans = answer_question(db, "制造业如何申请留抵退税")
        checks.append(("chat_has_cites_or_uncertain", bool(ans.get("citation_ids")) or ans["state"] == "uncertain"))
        conv_id = ans["conversation_id"]

        t = ticket_svc.create_ticket(db, conversation_id=conv_id, plan_code="standard")
        checks.append(("ticket_pending_pay", t.status == "pending_payment"))

        t = ticket_svc.mock_pay(db, t.id)
        checks.append(("paid_pending_accept", t.status == "pending_accept"))
        checks.append(("sla_set", t.sla_deadline is not None))

        t = ticket_svc.claim_ticket(db, t.id, expert)
        checks.append(("claimed", t.status == "in_progress" and t.expert_id == expert.id))

        # mutual exclusion
        try:
            ticket_svc.claim_ticket(db, t.id, expert)
            checks.append(("claim_mutex", False))
        except ValueError:
            checks.append(("claim_mutex", True))

        t = ticket_svc.submit_reply(db, t.id, expert, "试接书面答复：请按现行留抵公告条件与征管流程办理。")
        checks.append(("completed", t.status == "completed"))

        led = db.query(LedgerEntry).filter(LedgerEntry.ticket_id == t.id).one()
        checks.append(("ledger_exists", led.expert_share_cents > 0 and led.platform_share_cents > 0))

        t = ticket_svc.rate_ticket(db, t.id, 5, "ok")
        checks.append(("rated", t.rating == 5))

        # refund path on another ticket
        t2 = ticket_svc.create_ticket(db, conversation_id=conv_id, plan_code="complex")
        t2 = ticket_svc.mock_pay(db, t2.id)
        t2 = ticket_svc.claim_ticket(db, t2.id, expert)
        t2 = ticket_svc.submit_reply(db, t2.id, expert, "第二单答复")
        t2 = ticket_svc.request_refund(db, t2.id)
        t2 = ticket_svc.approve_refund(db, t2.id)
        checks.append(("refunded", t2.status == "refunded"))

    finally:
        db.close()

    ok = all(v for _, v in checks)
    for name, v in checks:
        print(f"{'PASS' if v else 'FAIL'} {name}")
    print("E2E", "OK" if ok else "FAILED")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
