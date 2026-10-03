"""Check whether open picks' postings are still live.

Visits the posting URL of every pick you haven't submitted or skipped, and
records in state/closed.json the ones that are gone (HTTP 404/410) or say they
no longer accept applications. The review page labels those cards.

Usage: python linkcheck.py --home HOME
"""
import argparse
import glob
import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JobDesk/0.2 link check",
      "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
CLOSED_TEXT = re.compile(
    r"no longer accepting applications|this job is no longer available|job (has|is) (been )?(closed|expired|filled)|"
    r"position (has been )?filled|posting (has )?(closed|expired)|this job has expired|job not found|"
    r"sorry, this job has expired|the job you are looking for (is|was) (no longer|not) available|"
    r"this position is no longer open|applications are closed|this job was removed|job (has been|was) removed|"
    r"this job is closed|job is no longer active|vacancy (is )?closed|this vacancy has expired", re.I)
OPEN_STATUSES = {"new", "apply"}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def check(url, timeout=20):
    """Returns (state, detail): state is 'open', 'closed' or 'unknown'."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(400_000).decode("utf-8", "replace")
            final = r.geturl()
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return "closed", f"HTTP {e.code}"
        return "unknown", f"HTTP {e.code}"
    except Exception as e:  # network error, timeout, blocked
        return "unknown", type(e).__name__
    m = CLOSED_TEXT.search(body)
    if m:
        return "closed", m.group(0)
    # Some boards redirect a removed posting to their job list
    if final.rstrip("/") != url.rstrip("/") and re.search(r"/(jobs|careers)/?(\?|$)", final):
        return "closed", "redirected to the job list"
    return "open", ""


def run(home):
    decisions = load_json(os.path.join(home, "state", "decisions.json"), {})
    picks = []
    for pf in glob.glob(os.path.join(home, "daily", "*", "picks.json")):
        for j in load_json(pf, {}).get("jobs", []):
            status = decisions.get(j.get("id"), {}).get("status", j.get("status", "new"))
            if status in OPEN_STATUSES and j.get("url"):
                picks.append(j)
    path = os.path.join(home, "state", "closed.json")
    closed = load_json(path, {})
    try:
        import postings_index
    except ImportError:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import postings_index
    left_feed = postings_index.closed_urls(home) if os.path.exists(os.path.join(home, "state", "postings.db")) else {}

    def one(j):
        if j["url"] in left_feed:
            return j, ("closed", f"left its company feed on {left_feed[j['url']]}")
        return j, check(j["url"])
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, picks))
    now = datetime.now().isoformat(timespec="seconds")
    newly = 0
    for j, (state, detail) in results:
        if state == "closed" and j["id"] not in closed:
            closed[j["id"]] = {"at": now, "reason": detail, "url": j["url"]}
            newly += 1
        elif state == "open" and j["id"] in closed:
            closed.pop(j["id"])  # reopened or a false alarm last time
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(closed, f, indent=2, ensure_ascii=False)
    counts = {s: sum(1 for _, (st, _) in results if st == s) for s in ("open", "closed", "unknown")}
    print(json.dumps({"checked": len(results), **counts, "newly_closed": newly}))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=os.environ.get("JOB_DESK_HOME"))
    a = ap.parse_args()
    raise SystemExit(run(os.path.abspath(a.home)))


if __name__ == "__main__":
    main()
