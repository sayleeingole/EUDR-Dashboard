"""One-off backfill: fill evidence.publisher for rows imported before the
column existed, by re-reading the original batch JSON (matched via
evidence.batch_file) and looking up the publisher for each source_name.

Safe to re-run: only touches rows where publisher IS NULL.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db

RESEARCH_DIR = db.BASE_DIR / "research"
IMPORTED_DIR = RESEARCH_DIR / "imported"


def _load_batch(batch_file):
    for d in (IMPORTED_DIR, RESEARCH_DIR):
        p = d / batch_file
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def main():
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, batch_file, section_code, source_name, url FROM evidence"
        " WHERE publisher IS NULL AND batch_file IS NOT NULL").fetchall()

    updated, missed = 0, 0
    batch_cache = {}
    for r in rows:
        batch = batch_cache.get(r["batch_file"])
        if batch is None and r["batch_file"] not in batch_cache:
            batch = _load_batch(r["batch_file"])
            batch_cache[r["batch_file"]] = batch
        if not batch:
            missed += 1
            continue
        match = next(
            (e for e in batch.get("evidence", [])
             if e.get("source_name") == r["source_name"]
             and e.get("section") == r["section_code"]),
            None)
        publisher = (match or {}).get("publisher")
        if publisher and publisher.strip():
            conn.execute("UPDATE evidence SET publisher=? WHERE id=?",
                        (publisher.strip(), r["id"]))
            updated += 1
        else:
            missed += 1
    conn.commit()
    print(f"Updated {updated} evidence rows with publisher.")
    print(f"Left {missed} rows unmatched (no publisher in source batch, or batch file not found).")


if __name__ == "__main__":
    main()
