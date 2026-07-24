#!/usr/bin/env python3
"""Import knowledge/raw corpora into SQLite as draft clauses/chunks (M1-02)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# apps/api on path
API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.db import SessionLocal, init_db  # noqa: E402
from app.knowledge.chunker import chunk_document, distill_tags, fidelity_ok  # noqa: E402
from app.models import Chunk, Clause, Policy, PublishStatus  # noqa: E402

REPO_ROOT = API_ROOT.parents[1]
RAW_ROOT = REPO_ROOT / "knowledge" / "raw"
REPORT_DIR = REPO_ROOT / "knowledge" / "m1" / "qa"


DEFAULT_DIRS = [
    "C01_vat_law",
    "C02_vat_law_reg",
    "C04_2019_39",
    "C05_liudi_2025_7",
    "C06_liudi_admin_2025_20",
]


def load_meta(folder: Path) -> dict:
    meta_path = folder / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return {
        "corpus_id": folder.name,
        "title": folder.name,
        "source_url": None,
        "doc_no": None,
        "effective_from": None,
    }


def import_folder(db, folder_name: str, publish: bool) -> dict:
    folder = RAW_ROOT / folder_name
    txt_path = folder / "source.txt"
    if not txt_path.exists():
        raise FileNotFoundError(txt_path)

    meta = load_meta(folder)
    corpus_id = meta.get("corpus_id") or folder_name
    raw_text = txt_path.read_text(encoding="utf-8")
    source, chunks, strategy = chunk_document(raw_text)

    # replace existing policy for idempotent re-import
    existing = db.query(Policy).filter(Policy.corpus_id == corpus_id).one_or_none()
    if existing:
        for cl in list(existing.clauses):
            for ch in list(cl.chunks):
                db.delete(ch)
            db.delete(cl)
        db.delete(existing)
        db.flush()

    status = PublishStatus.published.value if publish else PublishStatus.draft.value
    policy = Policy(
        corpus_id=corpus_id,
        title=meta.get("title") or folder_name,
        doc_no=meta.get("doc_no"),
        source_url=meta.get("source_url"),
        tax_type="vat",
        effective_from=meta.get("effective_from"),
        is_active=True,
        raw_path=str(txt_path.relative_to(REPO_ROOT)),
    )
    db.add(policy)
    db.flush()

    qa_rows = []
    ok_count = 0
    for c in chunks:
        ok = fidelity_ok(source, c.body)
        ok_count += int(ok)
        note = "fidelity_pass" if ok else "fidelity_fail"
        # first batch: only publish if fidelity pass and --publish
        cl_status = status if ok and publish else PublishStatus.draft.value
        if publish and not ok:
            cl_status = PublishStatus.rejected.value

        clause = Clause(
            policy_id=policy.id,
            clause_no=c.clause_no,
            title=c.clause_no,
            body=c.body,
            status=cl_status,
            tax_tags=distill_tags(c.body),
            condition_draft=None,
            qa_note=note,
        )
        db.add(clause)
        db.flush()
        chunk = Chunk(
            clause_id=clause.id,
            body=c.body,
            status=cl_status,
        )
        db.add(chunk)
        qa_rows.append(
            {
                "corpus_id": corpus_id,
                "clause_no": c.clause_no,
                "chars": len(c.body),
                "fidelity_ok": ok,
                "tags": clause.tax_tags,
                "status": cl_status,
                "strategy": strategy,
            }
        )

    return {
        "corpus_id": corpus_id,
        "strategy": strategy,
        "chunks": len(chunks),
        "fidelity_pass": ok_count,
        "fidelity_fail": len(chunks) - ok_count,
        "qa_rows": qa_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="M1-02 import raw corpus")
    parser.add_argument(
        "--dirs",
        nargs="*",
        default=DEFAULT_DIRS,
        help="Folders under knowledge/raw",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Mark fidelity-pass clauses as published (default: all draft)",
    )
    args = parser.parse_args()

    init_db()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    summary = []

    db = SessionLocal()
    try:
        for name in args.dirs:
            result = import_folder(db, name, publish=args.publish)
            summary.append({k: v for k, v in result.items() if k != "qa_rows"})
            all_rows.extend(result["qa_rows"])
            print(
                f"{result['corpus_id']}: {result['chunks']} chunks "
                f"({result['strategy']}), fidelity "
                f"{result['fidelity_pass']}/{result['chunks']}"
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    report_json = REPORT_DIR / "chunk_import_report.json"
    report_csv = REPORT_DIR / "chunk_import_report.csv"
    report_json.write_text(
        json.dumps({"summary": summary, "rows": all_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with report_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "corpus_id",
                "clause_no",
                "chars",
                "fidelity_ok",
                "tags",
                "status",
                "strategy",
            ],
        )
        w.writeheader()
        w.writerows(all_rows)

    total = len(all_rows)
    passed = sum(1 for r in all_rows if r["fidelity_ok"])
    print(f"\nQA: {passed}/{total} fidelity pass")
    print(f"Wrote {report_json}")
    print(f"Wrote {report_csv}")


if __name__ == "__main__":
    main()
