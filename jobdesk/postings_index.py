"""Local postings index (SQLite): every posting seen in the company feeds, with
first-seen / last-seen dates and a closed date once it leaves its feed.

This is milestone 1 of the hosted design (docs/HOSTED.md): the same table, but
local. ingest.py calls record_run() after each successful feed fetch.

    python postings_index.py --home HOME stats
    python postings_index.py --home HOME new --since 2026-09-28
"""
import argparse
import json
import os
import sqlite3
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    url TEXT PRIMARY KEY,
    company TEXT, ats TEXT, board TEXT, title TEXT, location TEXT, posted TEXT,
    first_seen TEXT, last_seen TEXT, closed_on TEXT
);
CREATE INDEX IF NOT EXISTS idx_board ON postings(board);
CREATE INDEX IF NOT EXISTS idx_first_seen ON postings(first_seen);
"""


def connect(home):
    path = os.path.join(home, "state", "postings.db")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def board_key(board):
    return f"{board.get('ats', '')}:{board.get('slug', '')}:{board.get('search', '')}"


def record_run(home, board, jobs, today=None):
    """Upsert every posting a board returned today; close the board's postings that disappeared.
    Call only when the board fetched successfully (a failed fetch must not close anything)."""
    today = today or date.today().isoformat()
    key = board_key(board)
    db = connect(home)
    with db:
        seen = set()
        for j in jobs:
            url = j.get("url")
            if not url:
                continue
            seen.add(url)
            db.execute("""INSERT INTO postings (url, company, ats, board, title, location, posted, first_seen, last_seen, closed_on)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                          ON CONFLICT(url) DO UPDATE SET title=excluded.title, location=excluded.location,
                              last_seen=excluded.last_seen, closed_on=NULL""",
                       (url, j.get("company"), j.get("ats"), key, j.get("title"), j.get("location"), j.get("posted"), today, today))
        open_urls = [r[0] for r in db.execute("SELECT url FROM postings WHERE board=? AND closed_on IS NULL", (key,))]
        gone = [u for u in open_urls if u not in seen]
        db.executemany("UPDATE postings SET closed_on=? WHERE url=?", [(today, u) for u in gone])
    db.close()
    return len(gone)


def closed_urls(home):
    db = connect(home)
    rows = dict(db.execute("SELECT url, closed_on FROM postings WHERE closed_on IS NOT NULL"))
    db.close()
    return rows


def stats(home):
    db = connect(home)
    total, open_, closed = db.execute(
        "SELECT COUNT(*), SUM(closed_on IS NULL), SUM(closed_on IS NOT NULL) FROM postings").fetchone()
    db.close()
    return {"postings": total or 0, "open": open_ or 0, "closed": closed or 0}


def new_since(home, since):
    db = connect(home)
    rows = db.execute("SELECT company, title, location, url, first_seen FROM postings WHERE first_seen >= ? AND closed_on IS NULL "
                      "ORDER BY first_seen DESC, company", (since,)).fetchall()
    db.close()
    return [dict(zip(("company", "title", "location", "url", "first_seen"), r)) for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=os.environ.get("JOB_DESK_HOME"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    n = sub.add_parser("new"); n.add_argument("--since", default=date.today().isoformat())
    a = ap.parse_args()
    home = os.path.abspath(a.home)
    print(json.dumps(stats(home) if a.cmd == "stats" else new_since(home, a.since), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
