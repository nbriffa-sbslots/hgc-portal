"""
Load gaming_platforms.csv into SQLite, upsert on HGC code.
Run manually or via the GitHub Actions workflow.
"""

import csv
import html
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH       = Path(__file__).parent / "hgc.db"
CSV_PATH      = Path(__file__).parent / "gaming_platforms.csv"
NEW_CERTS_PATH = Path(__file__).parent / "new_certs.json"


def ingest(csv_path: Path = CSV_PATH, db_path: Path = DB_PATH):
    con = sqlite3.connect(db_path)

    # Snapshot existing HGC codes before ingest (for What's New diff)
    existing_codes: set[str] = set()
    try:
        rows = con.execute("SELECT hgc_code FROM certifications").fetchall()
        existing_codes = {r[0] for r in rows}
    except Exception:
        pass  # table may not exist yet

    con.execute("""
        CREATE TABLE IF NOT EXISTS certifications (
            hgc_code        TEXT PRIMARY KEY,
            trade_name      TEXT,
            title           TEXT,
            manufacturer    TEXT,
            operator        TEXT,
            category        TEXT,
            type            TEXT,
            version         TEXT,
            created         TEXT,
            modified        TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_title ON certifications(title COLLATE NOCASE)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_trade  ON certifications(trade_name COLLATE NOCASE)")

    inserted = updated = 0
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {k: html.unescape(v) if isinstance(v, str) else v for k, v in row.items()}
        cur = con.execute(
                "SELECT modified FROM certifications WHERE hgc_code = ?",
                (row["EniaiosKodikosAdeias"],),
            )
            existing = cur.fetchone()
            if existing is None:
                con.execute(
                    "INSERT INTO certifications VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["EniaiosKodikosAdeias"],
                        row["EmporikiOnomasia"],
                        row["Title"],
                        row["Kataskevastis"],
                        row["Xrisi"],
                        row["Katigoria"],
                        row["Eidos"],
                        row["Ekdosi"],
                        row["Created"],
                        row["Modified"],
                    ),
                )
                inserted += 1
            elif existing[0] != row["Modified"]:
                con.execute(
                    """UPDATE certifications SET
                        trade_name=?, title=?, manufacturer=?, operator=?,
                        category=?, type=?, version=?, created=?, modified=?
                    WHERE hgc_code=?""",
                    (
                        row["EmporikiOnomasia"],
                        row["Title"],
                        row["Kataskevastis"],
                        row["Xrisi"],
                        row["Katigoria"],
                        row["Eidos"],
                        row["Ekdosi"],
                        row["Created"],
                        row["Modified"],
                        row["EniaiosKodikosAdeias"],
                    ),
                )
                updated += 1

    con.commit()

    # Build new_certs.json — certifications added in this run
    new_items = []
    if existing_codes:  # skip on first-ever ingest (everything would be "new")
        new_rows = con.execute(
            "SELECT hgc_code, title, trade_name, manufacturer, operator, created "
            "FROM certifications WHERE hgc_code NOT IN ({})".format(
                ",".join("?" * len(existing_codes))
            ),
            list(existing_codes),
        ).fetchall()
        new_items = [
            {
                "hgc_code":    r[0],
                "title":       r[1],
                "trade_name":  r[2],
                "manufacturer": r[3],
                "operator":    r[4],
                "created":     r[5],
            }
            for r in new_rows
        ]

    con.close()

    new_certs = {
        "generated_at": datetime.now().isoformat(),
        "new_count":    len(new_items),
        "items":        new_items,
    }
    NEW_CERTS_PATH.write_text(json.dumps(new_certs, ensure_ascii=False, indent=2))
    print(f"Ingest complete — {inserted} inserted, {updated} updated, {len(new_items)} new certs written.")

    # Check watch list and auto-resolve any newly matched games
    try:
        from watchlist import check_watchlist
        resolved = check_watchlist(db_path)
        if resolved:
            print(f"Watch list: auto-resolved {len(resolved)} game(s):")
            for item in resolved:
                print(f"  ✓ {item['game_name']} → {item['hgc_code']} ({item['matched_title']}) in run '{item['run_name']}'")
        else:
            print("Watch list: no new matches.")
    except Exception as e:
        print(f"Watch list check skipped: {e}")


if __name__ == "__main__":
    csv_file = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV_PATH
    ingest(csv_file)
