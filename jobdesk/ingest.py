"""Pull open roles from companies' public job-board feeds (no scraping, no AI cost).

Supported public feeds: Greenhouse (US and EU), Lever, Ashby, Workable, SmartRecruiters, Teamtailor (RSS; slug = the career site host, e.g. "careers.example.com"),
Workday (slug = "tenant/wdN/site" from the career-site URL https://tenant.wdN.myworkdayjobs.com/site;
optional "search" narrows large boards, e.g. "Dubai").
Reads HOME/profile/boards.json, writes HOME/state/ingested/<date>.json with the
postings that match the filters and were not seen before.

boards.json:
{
  "filters": {
    "locations": ["riyadh", "saudi", "dubai", "abu dhabi", "uae", "remote"],
    "title_include": ["strategy", "operations", "chief of staff", "product", "partnership"],
    "title_exclude": ["intern", "engineer", "developer", "graduate"]
  },
  "boards": [
    {"company": "Careem", "ats": "greenhouse", "slug": "careem"},
    {"company": "Voodoo", "ats": "ashby", "slug": "voodoo"}
  ]
}
Usage: python ingest.py [--home HOME] [--date YYYY-MM-DD]
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html import unescape

UA = {"User-Agent": "JobDesk/0.1 (personal job search; public job-board feeds)", "Accept": "application/json"}

FEEDS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "greenhouse_eu": "https://boards-api.eu.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{slug}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
    "teamtailor": "https://{slug}/jobs.rss",
    "workday": "workday",
}


def fetch_workday(board, max_jobs=200, timeout=20):
    """Workday career sites are backed by a public JSON search endpoint (the one the site itself calls)."""
    tenant, wd, site = board["slug"].split("/")
    base = f"https://{tenant}.{wd}.myworkdayjobs.com"
    api = f"{base}/wday/cxs/{tenant}/{site}/jobs"
    postings, offset = [], 0
    while offset < max_jobs:
        body = json.dumps({"limit": 20, "offset": offset, "searchText": board.get("search", ""), "appliedFacets": {}}).encode()
        req = urllib.request.Request(api, data=body, method="POST", headers={**UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            page = json.load(r)
        batch = page.get("jobPostings", [])
        postings.extend(batch)
        if len(batch) < 20:
            break
        offset += 20
    return {"postings": postings, "base": f"{base}/{site}"}


def fetch_teamtailor(url, timeout=20):
    """Teamtailor career sites publish an RSS feed; turn it into the same shape as the JSON feeds."""
    import xml.etree.ElementTree as ET
    req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        root = ET.fromstring(r.read())
    tt = "{https://teamtailor.com/locations}"
    items = []
    for it in root.iter("item"):
        locs = []
        for loc in it.iter(tt + "location"):
            parts = [(loc.findtext(tt + k) or "").strip() for k in ("city", "country")]
            locs.append(", ".join(x for x in parts if x) or (loc.findtext(tt + "name") or "").strip())
        items.append({"title": (it.findtext("title") or "").strip(), "location": " | ".join(x for x in locs if x),
                      "url": (it.findtext("link") or "").strip(), "pubDate": it.findtext("pubDate") or "",
                      "description": it.findtext("description") or "", "remote": (it.findtext("remoteStatus") or "").lower() in ("fully", "remote")})
    return {"items": items}


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def strip_html(s):
    s = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n{3,}", "\n\n", unescape(s)).strip()


def normalise(board, raw):
    """Map one board's feed to a list of {company, title, location, url, posted, description}."""
    ats, company = board["ats"], board["company"]
    out = []
    if ats in ("greenhouse", "greenhouse_eu"):
        for j in raw.get("jobs", []):
            out.append({"title": j.get("title", ""), "location": (j.get("location") or {}).get("name", ""),
                        "url": j.get("absolute_url", ""), "posted": (j.get("updated_at") or "")[:10],
                        "description": strip_html(unescape(j.get("content", "")))})
    elif ats == "lever":
        for j in raw if isinstance(raw, list) else []:
            cat = j.get("categories") or {}
            locs = cat.get("allLocations") or [cat.get("location", "")]
            out.append({"title": j.get("text", ""), "location": ", ".join(l for l in locs if l),
                        "url": j.get("hostedUrl", ""),
                        "posted": date.fromtimestamp(j["createdAt"] / 1000).isoformat() if j.get("createdAt") else "",
                        "description": strip_html(j.get("description", "") + "\n" + "\n".join(
                            (l.get("text", "") + "\n" + strip_html(l.get("content", ""))) for l in j.get("lists", [])))})
    elif ats == "ashby":
        for j in raw.get("jobs", []):
            locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations", []) or []]
            comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
            out.append({"title": j.get("title", ""), "location": ", ".join(l for l in locs if l),
                        "url": j.get("jobUrl", ""), "posted": (j.get("publishedAt") or "")[:10],
                        "description": (("Compensation: " + comp + "\n\n") if comp else "") + strip_html(j.get("descriptionHtml", "")),
                        "remote": bool(j.get("isRemote"))})
    elif ats == "workable":
        for j in raw.get("jobs", []):
            loc = ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
            out.append({"title": j.get("title", ""), "location": loc, "url": j.get("url") or j.get("shortlink", ""),
                        "posted": (j.get("published_on") or j.get("created_at") or "")[:10],
                        "description": strip_html(j.get("description", "")), "remote": bool(j.get("telecommuting"))})
    elif ats == "teamtailor":
        from email.utils import parsedate_to_datetime
        for j in raw.get("items", []):
            try:
                posted = parsedate_to_datetime(j["pubDate"]).date().isoformat()
            except (TypeError, ValueError):
                posted = ""
            out.append({"title": j["title"], "location": j["location"], "url": j["url"], "posted": posted,
                        "description": strip_html(j["description"]), "remote": j["remote"]})
    elif ats == "workday":
        for j in raw.get("postings", []):
            out.append({"title": j.get("title", ""), "location": j.get("locationsText", ""),
                        "url": raw["base"] + j.get("externalPath", ""), "posted": j.get("postedOn", ""),
                        "description": ""})
    elif ats == "smartrecruiters":
        for j in raw.get("content", []):
            l = j.get("location") or {}
            loc = ", ".join(x for x in (l.get("city"), l.get("region"), l.get("country")) if x)
            out.append({"title": j.get("name", ""), "location": loc,
                        "url": f"https://jobs.smartrecruiters.com/{board['slug']}/{j.get('id', '')}",
                        "posted": (j.get("releasedDate") or "")[:10], "description": "", "remote": bool(l.get("remote"))})
    for o in out:
        o["company"] = company
        o["ats"] = ats
    return out


def too_old(job, max_age_days, today):
    """True when the posting date is known and older than max_age_days."""
    if not max_age_days:
        return False
    try:
        posted = date.fromisoformat((job.get("posted") or "")[:10])
    except ValueError:
        return False
    return (today - posted).days > int(max_age_days)


def matches(job, f):
    title, loc = job["title"].lower(), (job["location"] or "").lower()
    locs = [x.lower() for x in f.get("locations", [])]
    if locs and not (any(x in loc for x in locs) or ("remote" in locs and job.get("remote"))):
        return False
    inc = [x.lower() for x in f.get("title_include", [])]
    if inc and not any(x in title for x in inc):
        return False
    if any(x.lower() in title for x in f.get("title_exclude", [])):
        return False
    # level_exclude: regular expressions matched against the lower-cased title
    return not any(re.search(p, title) for p in f.get("level_exclude", []))


def load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def run(home, today):
    cfg = load_json(os.path.join(home, "profile", "boards.json"), None)
    if not cfg or not cfg.get("boards"):
        print(json.dumps({"ok": False, "error": "profile/boards.json missing or empty"}))
        return 1
    seen = load_json(os.path.join(home, "state", "seen.json"), {"jobs": {}}).get("jobs", {})
    try:
        today_date = date.fromisoformat(today[:10])
    except ValueError:
        today_date = date.today()
    filters = cfg.get("filters", {})

    def one(board):
        url = FEEDS.get(board.get("ats", "").lower(), "").format(slug=board.get("slug", ""))
        if not url:
            return board, [], "unknown ats"
        try:
            if board.get("ats", "").lower() == "workday":
                return board, normalise(board, fetch_workday(board)), None
            if board.get("ats", "").lower() == "teamtailor":
                return board, normalise(board, fetch_teamtailor(url)), None
            raw = fetch(url)
            if board.get("ats", "").lower() == "smartrecruiters":  # paged, 100 per page
                total, items = raw.get("totalFound", 0), list(raw.get("content", []))
                while len(items) < min(total, 1000):
                    page = fetch(url + f"&offset={len(items)}")
                    if not page.get("content"):
                        break
                    items.extend(page["content"])
                raw = {"content": items}
            return board, normalise(board, raw), None
        except urllib.error.HTTPError as e:
            return board, [], f"HTTP {e.code}"
        except Exception as e:  # network errors, bad JSON
            return board, [], type(e).__name__

    kept, report = [], []
    try:
        import postings_index
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import postings_index
    with ThreadPoolExecutor(max_workers=8) as pool:
        for board, jobs, err in pool.map(one, cfg["boards"]):
            if not err:
                try:
                    postings_index.record_run(home, board, jobs, today=today_date.isoformat())
                except Exception:  # the index is a helper; never fail ingestion because of it
                    pass
            hits = [j for j in jobs if matches(j, filters) and j["url"] and j["url"] not in seen
                    and not too_old(j, filters.get("max_age_days", 30), today_date)]
            # One entry per company + title; a role posted in several cities keeps all its locations
            merged = {}
            for j in hits:
                key = (j["company"], j["title"].strip().lower())
                if key in merged:
                    if j["location"] and j["location"] not in merged[key]["location"]:
                        merged[key]["location"] += " | " + j["location"]
                else:
                    merged[key] = j
            hits = list(merged.values())
            kept.extend(hits)
            report.append({"company": board["company"], "ats": board.get("ats"), "open_roles": len(jobs),
                           "new_matches": len(hits), "error": err})
    out_dir = os.path.join(home, "state", "ingested")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{today}.json")
    for i, j in enumerate(kept, 1):
        j["n"] = i
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"date": today, "boards": report, "jobs": kept}, fh, indent=2, ensure_ascii=False)
    index = os.path.join(out_dir, f"{today}-index.md")
    nl = chr(10)
    with open(index, "w", encoding="utf-8") as fh:
        fh.write(f"# Feed matches {today} ({len(kept)} postings){nl}{nl}")
        fh.write(f"Full text for posting n is in `{today}.json` under jobs[n-1].description.{nl}{nl}")
        fh.write(f"| n | Company | Title | Location | Posted |{nl}|---|---|---|---|---|{nl}")
        for j in kept:
            cells = [str(j["n"]), j["company"], j["title"], (j["location"] or "")[:60], j.get("posted", "")]
            fh.write("| " + " | ".join(c.replace("|", "/") for c in cells) + " |" + nl)
    print(json.dumps({"ok": True, "boards": len(report), "errors": sum(1 for r in report if r["error"]),
                      "new_matches": len(kept), "file": out, "index": index}))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=os.environ.get("JOB_DESK_HOME") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "home"))
    ap.add_argument("--date", default=date.today().isoformat())
    a = ap.parse_args()
    sys.exit(run(os.path.abspath(a.home), a.date))


if __name__ == "__main__":
    main()
