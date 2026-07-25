#!/usr/bin/env python3
"""Golden-set style eval gate (M1-08) — retrieval citation hit rate.

Definition (MVP):
- citation_correct: top-k search returns at least one chunk from expected corpus_id
- hallucinated_hard_answer: chat state=answered with empty citation_ids (should be 0)
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

# Seed questions mapped to expected corpus (clause_ref TBD by experts)
GOLDEN = [
    {"id": "Q01", "q": "增值税税率有哪些档次", "expect_corpus": ["C01", "C02"]},
    {"id": "Q05", "q": "视同应税交易包括哪些情形", "expect_corpus": ["C01"]},
    {"id": "Q11", "q": "哪些进项税额不得抵扣", "expect_corpus": ["C01", "C02"]},
    {"id": "Q29", "q": "小规模纳税人的标准是什么", "expect_corpus": ["C01", "C02"]},
    {"id": "Q37", "q": "2025年完善增值税期末留抵退税政策依据哪份公告", "expect_corpus": ["C05"]},
    {"id": "Q38", "q": "制造业等四个行业如何申请留抵退税", "expect_corpus": ["C05"]},
    {"id": "Q41", "q": "办理留抵退税的征管事项公告是哪一份", "expect_corpus": ["C06"]},
    {"id": "Q21", "q": "将自产货物用于集体福利是否视同销售", "expect_corpus": ["C01"]},
]


def main() -> None:
    init_db()
    db = SessionLocal()
    rows = []
    try:
        for g in GOLDEN:
            hits, meta = search_chunks(db, g["q"], top_k=5)
            hit_corpus = {h.corpus_id for h in hits}
            ok = bool(hit_corpus & set(g["expect_corpus"]))
            ans = answer_question(db, g["q"], top_k=5)
            hard_halluc = ans.get("state") == "answered" and not ans.get("citation_ids")
            rows.append(
                {
                    "id": g["id"],
                    "ok": ok,
                    "hit_corpus": sorted(hit_corpus),
                    "expect": g["expect_corpus"],
                    "state": ans.get("state"),
                    "citation_ids": ans.get("citation_ids"),
                    "hard_hallucination": hard_halluc,
                    "latency_ms": meta.get("latency_ms"),
                }
            )
            print(
                f"{g['id']}: retrieval={'PASS' if ok else 'FAIL'} "
                f"state={ans.get('state')} cites={ans.get('citation_ids')}"
            )
    finally:
        db.close()

    n = len(rows)
    recall = sum(1 for r in rows if r["ok"]) / n if n else 0
    halluc = sum(1 for r in rows if r["hard_hallucination"]) / n if n else 0
    gate_ok = recall >= 0.7 and halluc <= 0.05
    report = {
        "definition": {
            "citation_correct": "top5 命中期望 corpus_id 任一",
            "hard_hallucination": "answered 且 citation_ids 为空",
            "release_gate": "recall>=0.70 and hard_hallucination<=0.05",
        },
        "metrics": {
            "n": n,
            "retrieval_hit_rate": round(recall, 4),
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
