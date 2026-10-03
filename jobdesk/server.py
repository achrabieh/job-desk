"""Job Desk local server.

Serves the review page at http://127.0.0.1:8765 and a tiny JSON API:
  GET  /api/jobs         all picks (daily/*/picks.json) merged with decisions
  POST /api/decision     {"id", "status", "skip_reasons"?: [...], "skip_note"?} -> state/decisions.json
  POST /api/open-folder  {"id"} -> opens that pick's folder in Explorer
  GET  /files/<path>     files under daily/ (tailored CVs, notes)
Bound to localhost only. POSTs require the X-JobDesk header, which a
cross-site page cannot send without a CORS preflight this server never grants.
"""
import glob
import json
import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import setup_wizard as wiz
import updater

CODE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(CODE)
# JOB_DESK_HOME is the user's data folder (profile/, daily/, state/, logs/).
ENGINE = os.path.abspath(os.environ.get("JOB_DESK_HOME") or os.path.join(REPO, "home"))
DAILY = os.path.join(ENGINE, "daily")
DECISIONS = os.path.join(ENGINE, "state", "decisions.json")
TAILOR_STATUS = os.path.join(ENGINE, "state", "tailor_status.json")
TAILOR_Q = queue.Queue()
# Tests set JOB_DESK_NO_AGENTS=1: jobs are marked queued but no AI run is started
NO_AGENTS = os.environ.get("JOB_DESK_NO_AGENTS") == "1"
PAGE = os.path.join(CODE, "dashboard.html")
SETUP_PAGE = os.path.join(CODE, "setup.html")
HOST, PORT = "127.0.0.1", int(os.environ.get("JOB_DESK_PORT", "8765"))
VALID_STATUS = {"new", "apply", "submitted", "skipped", "interview", "offer", "rejected"}
LOCK = threading.Lock()
MIME = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".md": "text/plain; charset=utf-8", ".json": "application/json", ".html": "text/html; charset=utf-8"}


def load_decisions():
    try:
        with open(DECISIONS, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_decisions(data):
    os.makedirs(os.path.dirname(DECISIONS), exist_ok=True)
    tmp = DECISIONS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, DECISIONS)


def log_error(where):
    """Append the current exception with its traceback to logs/server.log (the server runs hidden)."""
    import traceback
    try:
        os.makedirs(os.path.join(ENGINE, "logs"), exist_ok=True)
        with open(os.path.join(ENGINE, "logs", "server.log"), "a", encoding="utf-8") as f:
            f.write(f"--- {datetime.now().isoformat(timespec='seconds')} {where}" + chr(10) + traceback.format_exc() + chr(10))
    except OSError:
        pass


def load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def set_tailor_state(jid, state, folder=None):
    with LOCK:
        st = load_json(TAILOR_STATUS, {})
        entry = st.get(jid, {})
        entry.update({"state": state, "updated": datetime.now().isoformat(timespec="seconds")})
        if folder:
            entry["folder"] = folder
        st[jid] = entry
        save_json(TAILOR_STATUS, st)


def enqueue_tailor(job):
    folder = job.get("folder")
    if not folder or job.get("pack") in ("queued", "running"):
        return False
    set_tailor_state(job["id"], "queued", folder)
    if not NO_AGENTS:
        TAILOR_Q.put(("tailor", job["id"], folder))
    return True


def enqueue_prep(job):
    folder = job.get("folder")
    if not folder or job.get("prep") in ("queued", "running", "ready"):
        return False
    set_tailor_state(job["id"] + "#prep", "queued", folder)
    if not NO_AGENTS:
        TAILOR_Q.put(("prep", job["id"], folder))
    return True


FACTCHECK = os.path.join(CODE, "factcheck.py")


def run_factcheck(folder):
    """Check a finished pack against the user's approved sources; writes factcheck.json in the job folder."""
    job = os.path.join(DAILY, folder)
    first = lambda *names: next((os.path.join(job, n) for n in names if os.path.isfile(os.path.join(job, n))), None)
    sources = [os.path.join(ENGINE, "profile", n) for n in ("fact_bank.md", "cv_spec.json", "base_spec.json", "application_answers.md")
               if os.path.isfile(os.path.join(ENGINE, "profile", n))]
    cv, posting = first("cv_spec.json", "spec.json"), first("posting.md", "job.md")
    texts = [t for t in (first("cover_note.md"), first("application_qa.md")) if t]
    if not sources or not os.path.isfile(FACTCHECK):
        return
    cmd = [sys.executable, FACTCHECK, "--sources", *sources, "--out", os.path.join(job, "factcheck.json")]
    if posting:
        cmd += ["--posting", posting]
    if cv:
        cmd += ["--cv", cv]
    if texts:
        cmd += ["--texts", *texts]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (subprocess.TimeoutExpired, OSError):
        pass


def tailor_worker():
    while True:
        kind, jid, folder = TAILOR_Q.get()
        if kind == "prep":
            key = jid + "#prep"
            set_tailor_state(key, "running")
            try:
                r = subprocess.run([sys.executable, os.path.join(CODE, "cli.py"), "prep", "--home", ENGINE, "--folder", folder],
                                   cwd=ENGINE, capture_output=True, timeout=2400, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                ok = r.returncode == 0 and os.path.isfile(os.path.join(DAILY, folder, "interview.json"))
            except (subprocess.TimeoutExpired, OSError):
                log_error(f"prep {folder}")
                ok = False
            set_tailor_state(key, "done" if ok else "failed")
            TAILOR_Q.task_done()
            continue
        set_tailor_state(jid, "running")
        try:
            r = subprocess.run([sys.executable, os.path.join(CODE, "cli.py"), "tailor", "--home", ENGINE, "--folder", folder],
                               cwd=ENGINE, capture_output=True, timeout=1800,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            ok = r.returncode == 0 and os.path.isfile(os.path.join(DAILY, folder, "pack.json"))
        except (subprocess.TimeoutExpired, OSError):
            ok = False
        if ok:
            run_factcheck(folder)
        set_tailor_state(jid, "done" if ok else "failed")
        TAILOR_Q.task_done()


EDITABLE = {
    "criteria.md": "What to search for",
    "fact_bank.md": "Facts your CVs may use",
    "application_answers.md": "Standard form answers and salary rules",
    "boards.json": "Company job feeds",
}


def last_run_status():
    """Latest daily-search log: when it finished and its exit code (non-zero means the run failed)."""
    import glob
    import re
    logs = [p for p in glob.glob(os.path.join(ENGINE, "logs", "????-??-??*.log")) if not p.endswith(".audit.log")]
    if not logs:
        return None
    latest = max(logs, key=os.path.getmtime)
    try:
        with open(latest, encoding="utf-8", errors="replace") as f:
            text = f.read()[-20000:]
    except OSError:
        return None
    runs = re.findall(r"=== finished ([0-9T:-]+), exit (-?\d+) ===", text)
    started = text.count("=== started")
    if not runs:
        return {"log": os.path.basename(latest), "state": "running" if started else "unknown"}
    at, code = runs[-1]
    running = started > len(runs)
    return {"log": os.path.basename(latest), "finished": at, "exit": int(code), "state": "running" if running else ("ok" if code == "0" else "failed")}


def latest_feed():
    """Today's (latest) feed matches that are not already picks."""
    import glob
    import re
    files = [f for f in glob.glob(os.path.join(ENGINE, "state", "ingested", "*.json"))
             if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", os.path.basename(f))]
    if not files:
        return None, []
    latest = max(files)
    data = load_json(latest, {})
    def norm_title(title):
        t = re.sub(r"\(.*?\)|\b[a-z]*\d[\w-]*\b", " ", (title or "").lower())
        return " ".join(re.findall(r"[a-z]+", t))

    def company_words(company):
        return {w for w in re.findall(r"[a-z0-9]+", (company or "").lower()) if len(w) >= 4}
    existing = load_jobs()[0]
    picked_urls = {j.get("url") for j in existing}
    picked = [(norm_title(j.get("role")), company_words(j.get("company"))) for j in existing]

    def already_picked(j):
        # Same title (ignoring punctuation and reference codes) at a company sharing a name word:
        # "HungerStation (Delivery Hero)" matches "Delivery Hero (talabat, HungerStation)"
        t, cw = norm_title(j.get("title")), company_words(j.get("company"))
        return any(t == pt and (cw & pc) for pt, pc in picked)
    rows = [{"n": j.get("n", i + 1), "company": j.get("company", ""), "title": j.get("title", ""), "location": j.get("location", ""),
             "posted": j.get("posted", ""), "url": j.get("url", "")}
            for i, j in enumerate(data.get("jobs", []))
            if j.get("url") not in picked_urls and not already_picked(j)]
    # Order: the user's location priority (order in boards.json), then title keyword hits, then newest
    filters = load_json(os.path.join(ENGINE, "profile", "boards.json"), {}).get("filters", {})
    locs = [x.lower() for x in filters.get("locations", [])]
    words = [x.lower() for x in filters.get("title_include", [])]

    def rank(r):
        loc = (r["location"] or "").lower()
        li = next((i for i, x in enumerate(locs) if x in loc), len(locs))
        hits = sum(1 for w in words if w in (r["title"] or "").lower())
        try:
            newest_first = -datetime.strptime((r["posted"] or "")[:10], "%Y-%m-%d").toordinal()
        except ValueError:
            newest_first = 0  # unknown dates go last within their group
        return (li, -hits, newest_first)
    rows.sort(key=rank)
    return os.path.basename(latest)[:10], rows


def add_feed_pick(day, n):
    """Turn feed posting n of `day` into a pick (job.md + posting.md) in daily/<day>-feed/."""
    import re
    path = os.path.join(ENGINE, "state", "ingested", f"{day}.json")
    data = load_json(path, {})
    job = next((j for i, j in enumerate(data.get("jobs", [])) if j.get("n", i + 1) == n), None)
    if not job:
        return None, "Posting not found in the feed"
    batch = f"{day}-feed"
    bdir = os.path.join(DAILY, batch)
    os.makedirs(bdir, exist_ok=True)
    picks_path = os.path.join(bdir, "picks.json")
    picks = load_json(picks_path, {"run": {"last_run": day, "summary": "Roles you added from the Feed tab."}, "jobs": []})
    if any(p.get("url") == job.get("url") for p in picks["jobs"]):
        return None, "Already in your picks"
    idx = len(picks["jobs"]) + 1
    slug = re.sub(r"[^a-z0-9]+", "-", (job.get("company", "") + "-" + job.get("title", "")).lower()).strip("-")[:40] or "role"
    folder = f"{batch}/{idx:02d}-{slug}"
    jdir = os.path.join(DAILY, *folder.split("/"))
    os.makedirs(jdir, exist_ok=True)
    nl = chr(10)
    with open(os.path.join(jdir, "job.md"), "w", encoding="utf-8") as f:
        f.write(f"# {job.get('company')} — {job.get('title')}{nl}{nl}- **City:** {job.get('location')}{nl}- **URL:** {job.get('url')}{nl}"
                f"- **Posted:** {job.get('posted')}{nl}- **Source:** added from the Feed tab{nl}")
    with open(os.path.join(jdir, "posting.md"), "w", encoding="utf-8") as f:
        f.write(f"# {job.get('title')} — {job.get('company')}{nl}Apply: {job.get('url')}{nl}Location: {job.get('location')}{nl}{nl}{job.get('description', '')}{nl}")
    pick = {"id": f"{batch}-{idx:02d}-{slug}", "date": day, "rank": 90 + idx, "company": job.get("company"), "role": job.get("title"),
            "city": job.get("location"), "track": "", "level_fit": "", "pay_estimate": "", "pay_flag": "unknown",
            "posted": job.get("posted"), "url": job.get("url"), "score": None, "why": [], "gaps": [],
            "about": "Added by you from the Feed tab. Press Apply to get a tailored CV, cover note and answers.",
            "folder": folder, "status": "new", "tag": "Feed"}
    picks["jobs"].append(pick)
    save_json(picks_path, picks)
    return pick, None


def profile_gaps():
    """Standard answers still marked as placeholders, e.g. '[to fill]' or '[your notice period]'."""
    import re
    path = os.path.join(ENGINE, "profile", "application_answers.md")
    if not os.path.isfile(path):
        return []
    gaps = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            if re.search(r"\[(to fill|fill in|your [^\]]*|tbc|todo)[^\]]*\]", line, re.I):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                label = cells[0] if len(cells) > 1 and cells[0] else re.sub(r"[*`#]|^\s*-\s*", "", line).split(":")[0].strip()[:60]
                gaps.append(label.strip("* ")[:60])
    return gaps


def profile_files():
    out = []
    for name, label in EDITABLE.items():
        path = os.path.join(ENGINE, "profile", name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8-sig") as f:
                out.append({"name": name, "label": label, "text": f.read()})
    return out


def save_profile_file(name, text):
    """Save one editable profile file; keeps the previous version as <name>.bak. Returns an error string or None."""
    if name not in EDITABLE:
        return "This file can't be edited here"
    if len(text) > 400_000:
        return "File too large"
    if name.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return f"Not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}"
        if name == "boards.json" and not isinstance(data.get("boards"), list):
            return 'boards.json needs a "boards" list'
    path = os.path.join(ENGINE, "profile", name)
    if os.path.isfile(path):
        with open(path, encoding="utf-8-sig") as f:
            old = f.read()
        with open(path + ".bak", "w", encoding="utf-8") as f:
            f.write(old)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return None


def load_jobs():
    jobs, meta = [], None
    if not os.path.isdir(DAILY):
        return jobs, meta
    decisions = load_decisions()
    tailor_status = load_json(TAILOR_STATUS, {})
    closed = load_json(os.path.join(ENGINE, "state", "closed.json"), {})
    for day in sorted(os.listdir(DAILY)):
        p = os.path.join(DAILY, day, "picks.json")
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            continue
        meta = data.get("run") or meta
        for j in data.get("jobs", []):
            j = dict(j)
            j.setdefault("date", day)
            j.setdefault("status", "new")
            j.update(decisions.get(j.get("id"), {}))
            folder = j.get("folder")
            pack = load_json(os.path.join(DAILY, folder, "pack.json"), None) if folder else None
            if pack:
                j.update({k: pack[k] for k in ("cv_file", "cover_file", "cover_note", "qa") if k in pack})
            iv = load_json(os.path.join(DAILY, folder, "interview.json"), None) if folder else None
            ps = tailor_status.get(str(j.get("id")) + "#prep", {}).get("state")
            if iv and iv.get("prep_file"):
                j["prep"], j["prep_file"] = "ready", iv["prep_file"]
            elif ps in ("queued", "running", "failed"):
                j["prep"] = ps
            if j.get("id") in closed:
                j["closed"] = closed[j["id"]]
            fc = load_json(os.path.join(DAILY, folder, "factcheck.json"), None) if folder else None
            if fc is not None:
                j["factcheck"] = fc.get("issues", [])
            t = tailor_status.get(j.get("id"), {}).get("state")
            if j.get("cv_file"):
                j["pack"] = "ready"
            elif t in ("queued", "running", "failed"):
                j["pack"] = t
            else:
                j["pack"] = "none"
            jobs.append(j)
    return jobs, meta


def safe_daily_path(rel):
    full = os.path.realpath(os.path.join(DAILY, rel))
    root = os.path.realpath(DAILY)
    return full if full == root or full.startswith(root + os.sep) else None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # Other sites can't frame the page (click tricks), and the browser must trust our content types
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self):
        # Only answer requests addressed to this machine by name or loopback IP (blocks DNS-rebinding reads)
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        extra = [h.lower() for h in load_json(os.path.join(ENGINE, "config.json"), {}).get("allowed_hosts", [])]
        return host in ("127.0.0.1", "localhost", "::1") or host in extra

    def do_GET(self):
        try:
            return self._do_GET()
        except Exception:  # noqa: BLE001 - keep serving, record the problem
            log_error("GET " + self.path)
            return self._send(500, {"error": "Something went wrong on the Job Desk server; details are in logs/server.log"})

    def do_POST(self):
        try:
            return self._do_POST()
        except Exception:  # noqa: BLE001
            log_error("POST " + self.path)
            return self._send(500, {"error": "Something went wrong on the Job Desk server; details are in logs/server.log"})

    def _setup_post(self, step, body):
        """First-run wizard actions. Each returns {ok} or {error: plain-language message}."""
        import base64
        err = None
        if step == "name":
            err = wiz.save_name(ENGINE, body.get("name", ""))
        elif step == "cv":
            try:
                data = base64.b64decode(str(body.get("data", "")).split(",")[-1], validate=True)
            except (ValueError, TypeError):
                data = b""
            err = wiz.save_cv(ENGINE, str(body.get("filename", "")), data)
        elif step == "goals":
            err = wiz.save_goals(ENGINE, body if isinstance(body, dict) else {})
        elif step == "onboard":
            err = wiz.start_onboarding(ENGINE)
        elif step == "answers":
            err = wiz.save_answers(ENGINE, body.get("answers", {}))
        elif step == "change":
            err = wiz.request_cv_change(ENGINE, body.get("text", ""))
        elif step == "boards":
            slugs = body.get("slugs", [])
            err = wiz.save_boards(ENGINE, [str(x) for x in slugs] if isinstance(slugs, list) else [])
        elif step == "search":
            wiz.start_search(ENGINE)
        elif step == "schedule":
            err = wiz.set_schedule(ENGINE, bool(body.get("enabled")), str(body.get("time", "09:00")))
        elif step == "finish":
            wiz.finish(ENGINE)
        elif step == "design":
            err = wiz.choose_design(ENGINE, body.get("choice"), body.get("photo"))
        elif step == "goals-apply":
            err = wiz.apply_goals(ENGINE)
        elif step == "logout":
            err = wiz.claude_logout()
        elif step == "reset":
            err = wiz.start_over(ENGINE) if body.get("confirm") is True else "Please confirm first."
        elif step == "install-claude":
            wiz.start_task(ENGINE, "install", wiz.install_claude_cmd(), done_check=lambda: bool(wiz.claude_path()))
        elif step == "login":
            exe = wiz.claude_path()
            if not exe:
                err = "Install Claude first."
            else:
                wiz.start_task(ENGINE, "login", [exe, "auth", "login", "--claudeai"],
                               done_check=lambda: wiz.claude_status().get("logged_in"))
        else:
            return self._send(404, {"error": "Unknown step"})
        return self._send(400 if err else 200, {"error": err} if err else {"ok": True})

    def _do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "Forbidden host"})
        path = urlparse(self.path).path
        if path == "/api/setup/photo" or path.startswith("/api/setup/look/"):
            if path == "/api/setup/photo":
                img = wiz.photo_file(ENGINE)
            else:
                n = path.rsplit("/", 1)[1]
                img = wiz.look_image(ENGINE, n) if n.isdigit() and 0 < int(n) < 10 else None
            if not img:
                return self._send(404, {"error": "Not found"})
            ctype = {".png": "image/png", ".webp": "image/webp"}.get(os.path.splitext(img)[1].lower(), "image/jpeg")
            with open(img, "rb") as f:
                return self._send(200, f.read(), ctype)
        if path == "/api/whoami":
            return self._send(200, {"app": "job-desk", "id": wiz.home_id(ENGINE)})
        if path == "/api/update":
            cfg = load_json(os.path.join(ENGINE, "config.json"), {})
            force = "force=1" in (urlparse(self.path).query or "")
            return self._send(200, updater.check(ENGINE, force=force, enabled=cfg.get("check_updates", True) is not False))
        if path in ("/", "/index.html", "/setup"):
            # New users get the setup wizard until it's finished; anyone with picks already is set up
            has_picks = bool(glob.glob(os.path.join(DAILY, "*", "picks.json")))
            needs_setup = not wiz.config(ENGINE).get("setup_done") and not has_picks
            page = SETUP_PAGE if (path == "/setup" or needs_setup) else PAGE
            with open(page, "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path == "/api/setup/state":
            return self._send(200, wiz.state(ENGINE))
        if path == "/api/setup/feeds":
            return self._send(200, {"feeds": wiz.feed_catalog()})
        if path == "/preview.pdf":
            pdf = wiz.preview_pdf(ENGINE)
            if not pdf:
                return self._send(404, {"error": "No preview yet"})
            with open(pdf, "rb") as f:
                return self._send(200, f.read(), "application/pdf")
        if path == "/api/profile":
            return self._send(200, {"files": profile_files(), "gaps": profile_gaps()})
        if path == "/api/feed":
            day, rows = latest_feed()
            return self._send(200, {"day": day, "jobs": rows})
        if path == "/api/runstatus":
            return self._send(200, {"run": last_run_status()})
        if path == "/api/alerts":
            alerts = load_json(os.path.join(ENGINE, "state", "alerts.json"), [])
            return self._send(200, {"alerts": [a for a in alerts if not a.get("acknowledged")]})
        if path == "/api/config":
            cfg = load_json(os.path.join(ENGINE, "config.json"), {})
            return self._send(200, {"owner": cfg.get("owner", ""), "networks": cfg.get("networks", [])})
        if path == "/api/jobs":
            jobs, meta = load_jobs()
            return self._send(200, {"jobs": jobs, "run": meta})
        if path.startswith("/files/"):
            full = safe_daily_path(unquote(path[len("/files/"):]))
            if not full or not os.path.isfile(full):
                return self._send(404, {"error": "File not found"})
            with open(full, "rb") as f:
                return self._send(200, f.read(), MIME.get(os.path.splitext(full)[1].lower(), "application/octet-stream"))
        return self._send(404, {"error": "Not found"})

    def _do_POST(self):
        if not self._host_ok() or self.headers.get("X-JobDesk") != "1":
            return self._send(403, {"error": "Missing header"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            limit = 16 * 1024 * 1024 if urlparse(self.path).path == "/api/setup/cv" else 65536
            if n > limit:
                return self._send(413, {"error": "That file is too large."})
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "Bad JSON"})
        path = urlparse(self.path).path
        if path == "/api/update/install":
            err = updater.start_update(ENGINE)
            if err:
                return self._send(400, {"error": err})
            threading.Timer(1.5, os._exit, (0,)).start()  # close so the installer can replace the files
            return self._send(200, {"ok": True})
        if path.startswith("/api/setup/"):
            return self._setup_post(path[len("/api/setup/"):], body)
        if path == "/api/feed/pick":
            import re
            day, n = str(body.get("day", "")), body.get("n")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or not isinstance(n, int):
                return self._send(400, {"error": "Bad request"})
            with LOCK:
                pick, err = add_feed_pick(day, n)
            return self._send(400 if err else 200, {"error": err} if err else {"ok": True, "id": pick["id"]})
        if path == "/api/profile":
            with LOCK:
                err = save_profile_file(str(body.get("name", "")), str(body.get("text", "")))
            return self._send(400 if err else 200, {"error": err} if err else {"ok": True})
        if path == "/api/alerts/ack":
            with LOCK:
                alerts = load_json(os.path.join(ENGINE, "state", "alerts.json"), [])
                for a in alerts:
                    a["acknowledged"] = datetime.now().isoformat(timespec="seconds")
                save_json(os.path.join(ENGINE, "state", "alerts.json"), alerts)
            return self._send(200, {"ok": True})
        jobs, _ = load_jobs()
        known = {j["id"]: j for j in jobs if "id" in j}
        jid = body.get("id")
        if jid not in known:
            return self._send(404, {"error": "Unknown job"})
        if path == "/api/decision":
            status = body.get("status")
            if status not in VALID_STATUS:
                return self._send(400, {"error": "Bad status"})
            with LOCK:
                d = load_decisions()
                entry = {"status": status, "decided_at": datetime.now().isoformat(timespec="seconds")}
                if status == "skipped":
                    reasons = body.get("skip_reasons")
                    if isinstance(reasons, list):
                        reasons = [str(r)[:60] for r in reasons if str(r).strip()][:8]
                    else:
                        reasons = [r for r in [str(body.get("skip_reason") or "")[:80]] if r]
                    note = str(body.get("skip_note") or "").strip()[:300]
                    entry["skip_reasons"] = reasons
                    if note:
                        entry["skip_note"] = note
                    # one readable line for the page and for the morning search
                    entry["skip_reason"] = "; ".join(reasons + ([note] if note else []))[:400]
                prev = d.get(jid, {})
                if status == "submitted":
                    entry["submitted_at"] = prev.get("submitted_at") or entry["decided_at"]
                elif status in ("interview", "offer", "rejected"):
                    entry["submitted_at"] = prev.get("submitted_at") or known[jid].get("submitted_at") or entry["decided_at"]
                    entry["outcome_at"] = entry["decided_at"]
                if status in ("new", "apply", "submitted", "skipped") and prev.get("followed_up_at"):
                    entry["followed_up_at"] = prev["followed_up_at"]
                if prev.get("note"):
                    entry["note"] = prev["note"]
                d[jid] = entry
                save_decisions(d)
            queued = False
            if status == "apply" and known[jid].get("pack") in ("none", "failed"):
                queued = enqueue_tailor(known[jid])
            if status == "interview":
                queued = enqueue_prep(known[jid]) or queued
            return self._send(200, {"ok": True, "tailoring": queued})
        if path == "/api/note":
            note = str(body.get("note", ""))[:4000]
            with LOCK:
                d = load_decisions()
                entry = d.get(jid, {"status": known[jid].get("status", "new")})
                entry["note"] = note
                d[jid] = entry
                save_decisions(d)
            return self._send(200, {"ok": True})
        if path == "/api/followed-up":
            with LOCK:
                d = load_decisions()
                entry = d.get(jid, {"status": known[jid].get("status", "submitted")})
                entry["followed_up_at"] = datetime.now().isoformat(timespec="seconds")
                d[jid] = entry
                save_decisions(d)
            return self._send(200, {"ok": True})
        if path == "/api/prep":
            return self._send(200, {"ok": True, "preparing": enqueue_prep(known[jid])})
        if path == "/api/tailor":
            if known[jid].get("pack") == "ready":
                return self._send(200, {"ok": True, "tailoring": False})
            return self._send(200, {"ok": True, "tailoring": enqueue_tailor(known[jid])})
        if path == "/api/open-folder":
            folder = known[jid].get("folder")
            full = safe_daily_path(folder) if folder else None
            if not full or not os.path.isdir(full):
                return self._send(404, {"error": "Folder not found"})
            os.startfile(full)  # noqa: S606 - local Explorer window for a validated folder
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "Not found"})


def main():
    # Resume anything that was queued or running when the server last stopped
    for jid, e in ({} if NO_AGENTS else load_json(TAILOR_STATUS, {})).items():
        if e.get("state") in ("queued", "running") and e.get("folder"):
            if jid.endswith("#prep"):
                TAILOR_Q.put(("prep", jid[:-5], e["folder"]))
            else:
                TAILOR_Q.put(("tailor", jid, e["folder"]))
    threading.Thread(target=tailor_worker, daemon=True).start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
