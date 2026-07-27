#!/usr/bin/env python3
"""Expert auth + claim mutex across two experts."""

from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import auth as auth_svc  # noqa: E402
from app.services import tickets as ticket_svc  # noqa: E402
from app.services.chat import answer_question  # noqa: E402


def main() -> None:
    init_db()
    db = SessionLocal()
    checks: list[tuple[str, bool]] = []
    try:
        auth_svc.ensure_demo_experts(db)
        db.commit()

        client = TestClient(app)

        bad = client.post("/v1/auth/login", json={"phone": "expert-demo", "password": "wrong"})
        checks.append(("bad_login_401", bad.status_code == 401))

        ok = client.post(
            "/v1/auth/login",
            json={"phone": "expert-demo", "password": "demo1234"},
        )
        checks.append(("login_ok", ok.status_code == 200 and "token" in ok.json()))
        token_a = ok.json()["token"]

        me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})
        checks.append(("me_ok", me.status_code == 200 and me.json()["expert"]["phone"] == "expert-demo"))

        noauth = client.get("/v1/expert/queue")
        checks.append(("queue_requires_auth", noauth.status_code == 401))

        ans = answer_question(db, "建筑服务一般纳税人适用什么税率")
        t = ticket_svc.create_ticket(db, conversation_id=ans["conversation_id"], plan_code="standard")
        t = ticket_svc.mock_pay(db, t.id)

        q = client.get("/v1/expert/queue", headers={"Authorization": f"Bearer {token_a}"})
        checks.append(("queue_lists_ticket", q.status_code == 200 and any(i["id"] == t.id for i in q.json()["items"])))

        claim = client.post(
            f"/v1/expert/tickets/{t.id}/claim",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        checks.append(("claim_ok", claim.status_code == 200 and claim.json()["status"] == "in_progress"))

        ok_b = client.post(
            "/v1/auth/login",
            json={"phone": "expert-demo-b", "password": "demo1234"},
        )
        token_b = ok_b.json()["token"]
        steal = client.post(
            f"/v1/expert/tickets/{t.id}/claim",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        checks.append(("claim_mutex_other_expert", steal.status_code == 409))

        reply = client.post(
            f"/v1/expert/tickets/{t.id}/reply",
            headers={"Authorization": f"Bearer {token_a}", "Content-Type": "application/json"},
            json={"reply": "书面答复：请按现行增值税法及注释核对建筑服务税率。", "suggest_reflow": True},
        )
        checks.append(("reply_ok", reply.status_code == 200 and reply.json()["status"] == "completed"))

        mine = client.get("/v1/expert/mine", headers={"Authorization": f"Bearer {token_a}"})
        checks.append(("mine_ok", mine.status_code == 200 and len(mine.json().get("items", [])) >= 1))

        logout = client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {token_a}"})
        checks.append(("logout_ok", logout.status_code == 200))
        after = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})
        checks.append(("token_revoked", after.status_code == 401))

    finally:
        db.close()

    ok_all = all(v for _, v in checks)
    for name, v in checks:
        print(f"{'PASS' if v else 'FAIL'} {name}")
    print("AUTH E2E", "OK" if ok_all else "FAILED")
    raise SystemExit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
