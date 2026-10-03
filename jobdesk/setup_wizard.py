"""First-run setup for non-technical users, driven from the review page.

Everything here is called by server.py endpoints. Long steps (installing
Claude, signing in, onboarding, applying answers, revising the CV, the first
search) run as background tasks whose state the page polls.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime

CODE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(CODE)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NO_AGENTS = os.environ.get("JOB_DESK_NO_AGENTS") == "1"
CV_EXTS = (".pdf", ".docx", ".doc", ".txt", ".md", ".rtf")
MAX_CV_BYTES = 10 * 1024 * 1024

_lock = threading.Lock()
_running = {}  # task name -> Popen


# ---------- small helpers ----------

def _load(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def python_exe():
    """Console-free Python on Windows so no black windows flash up."""
    exe = sys.executable
    if platform.system() == "Windows" and exe.lower().endswith("python.exe"):
        w = exe[:-10] + "pythonw.exe"
        if os.path.isfile(w):
            return w
    return exe


def claude_path():
    for c in (shutil.which("claude"), os.path.expanduser("~/.local/bin/claude.exe"), os.path.expanduser("~/.local/bin/claude")):
        if c and os.path.isfile(c):
            return c
    return None


# ---------- Claude account ----------

def claude_status():
    exe = claude_path()
    if not exe:
        return {"installed": False, "logged_in": False}
    try:
        r = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        data = json.loads(r.stdout or "{}")
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return {"installed": True, "logged_in": False}
    return {"installed": True, "logged_in": bool(data.get("loggedIn")),
            "plan": data.get("subscriptionType") or "", "email": data.get("email") or ""}


def claude_logout():
    exe = claude_path()
    if not exe or NO_AGENTS:
        return None
    try:
        r = subprocess.run([exe, "auth", "logout"], capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    except (subprocess.TimeoutExpired, OSError):
        return "Couldn't sign out of Claude. Please try again."
    return None if r.returncode == 0 else "Couldn't sign out of Claude: " + (r.stderr or r.stdout).strip()[:200]


def home_id(home):
    """Short fingerprint of a data folder, so two Job Desks on one PC never open each other's page."""
    import hashlib
    return hashlib.sha256(os.path.normcase(os.path.realpath(home)).encode("utf-8")).hexdigest()[:16]


def start_over(home):
    """Move the profile, picks and history into _archive/<time>/ (nothing is deleted) and reset setup."""
    if any(proc.poll() is None for proc in list(_running.values())):
        return "Please wait until the current task finishes, then try again."
    dest = os.path.join(home, "_archive", datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    os.makedirs(dest, exist_ok=True)
    for d in ("profile", "daily", "state"):
        src = os.path.join(home, d)
        if os.path.isdir(src):
            shutil.move(src, os.path.join(dest, d))
        os.makedirs(src, exist_ok=True)
    for rel, default in (("state/seen.json", {"jobs": {}}), ("state/decisions.json", {})):
        _save(os.path.join(home, rel), default)
    cfg = config(home)
    shutil.copy2(os.path.join(home, "config.json"), dest)
    keep = {k: cfg[k] for k in ("port", "allowed_hosts", "check_updates") if k in cfg}
    _save(os.path.join(home, "config.json"), dict(keep, owner="", networks=[]))
    if platform.system() == "Windows" and not NO_AGENTS:
        set_schedule(home, False)
    return None


def install_claude_cmd():
    if platform.system() == "Windows":
        ps = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
        return [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://claude.ai/install.ps1 | iex"]
    return ["/bin/sh", "-c", "curl -fsSL https://claude.ai/install.sh | bash"]


# ---------- background tasks ----------

def tasks_path(home):
    return os.path.join(home, "state", "setup_tasks.json")


def task_states(home):
    states = _load(tasks_path(home), {})
    # A task recorded as running whose process is gone (server restarted) is reported as failed
    for name, t in states.items():
        if t.get("state") == "running" and name not in _running:
            t["state"] = "failed"
            t["detail"] = "Interrupted. Please try again."
    return states


def _set_task(home, name, **fields):
    with _lock:
        states = _load(tasks_path(home), {})
        t = states.get(name, {})
        t.update(fields, updated=datetime.now().isoformat(timespec="seconds"))
        states[name] = t
        _save(tasks_path(home), states)


def start_task(home, name, cmd, done_check=None):
    """Run cmd in the background; state goes running -> done/failed. Returns False if already running."""
    with _lock:
        if name in _running and _running[name].poll() is None:
            return False
    log = os.path.join(home, "logs", f"setup-{name}.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    _set_task(home, name, state="running", detail="", started=datetime.now().isoformat(timespec="seconds"))
    if NO_AGENTS:  # tests: record the request, start nothing
        _set_task(home, name, state="queued", cmd=" ".join(cmd[:3]))
        return True

    def run():
        try:
            with open(log, "a", encoding="utf-8") as lf:
                lf.write(f"=== {datetime.now().isoformat(timespec='seconds')} {' '.join(cmd[:4])}\n")
                lf.flush()
                p = subprocess.Popen(cmd, cwd=home, stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT,
                                     creationflags=NO_WINDOW, env=dict(os.environ, JOB_DESK_HOME=home))
                with _lock:
                    _running[name] = p
                code = p.wait()
            ok = code == 0 and (done_check() if done_check else True)
            _set_task(home, name, state="done" if ok else "failed", exit=code,
                      detail="" if ok else "It didn't finish properly. Press the button to try again.")
        except OSError as e:
            _set_task(home, name, state="failed", detail=str(e)[:200])
        finally:
            with _lock:
                _running.pop(name, None)

    threading.Thread(target=run, daemon=True).start()
    return True


def cli(*args):
    return [python_exe(), os.path.join(CODE, "cli.py"), *args]


# ---------- profile steps ----------

def config(home):
    return _load(os.path.join(home, "config.json"), {})


def save_name(home, name):
    name = re.sub(r"\s+", " ", (name or "").strip())[:80]
    if len(name) < 2:
        return "Please enter your full name."
    cfg = config(home)
    cfg.setdefault("port", 8765)
    cfg.setdefault("networks", [])
    cfg["owner"] = name
    _save(os.path.join(home, "config.json"), cfg)
    for d in ("profile", "daily", "state", "logs"):
        os.makedirs(os.path.join(home, d), exist_ok=True)
    return None


def source_cv(home):
    prof = os.path.join(home, "profile")
    if not os.path.isdir(prof):
        return None
    for f in sorted(os.listdir(prof)):
        if f.startswith("source_cv") and f.lower().endswith(CV_EXTS):
            return os.path.join(prof, f)
    return None


def save_cv(home, filename, data):
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in CV_EXTS:
        return "Please upload your CV as a PDF or Word file."
    if not data or len(data) > MAX_CV_BYTES:
        return "That file is empty or larger than 10 MB."
    prof = os.path.join(home, "profile")
    os.makedirs(prof, exist_ok=True)
    old = source_cv(home)
    if old:
        os.remove(old)
    with open(os.path.join(prof, "source_cv" + ext), "wb") as f:
        f.write(data)
    return None


GOAL_FIELDS = ("roles", "cities", "pay", "industries", "avoid", "level", "extra")


def save_goals(home, goals):
    g = {k: str(goals.get(k, "")).strip()[:500] for k in GOAL_FIELDS}
    if not g["roles"] or not g["cities"]:
        return "Please tell us at least which roles and which cities you want."
    _save(os.path.join(home, "profile", "goals.json"), g)
    return None


def goals_text(home):
    g = _load(os.path.join(home, "profile", "goals.json"), {})
    parts = [("Roles", g.get("roles")), ("Level", g.get("level")), ("Cities", g.get("cities")),
             ("Minimum pay", g.get("pay")), ("Industries of interest", g.get("industries")),
             ("Avoid", g.get("avoid")), ("Other", g.get("extra"))]
    return ". ".join(f"{k}: {v}" for k, v in parts if v)


def profile_ready(home):
    prof = os.path.join(home, "profile")
    need = ("cv_spec.json", "fact_bank.md", "criteria.md", "application_answers.md")
    return all(os.path.isfile(os.path.join(prof, f)) for f in need)


def start_onboarding(home):
    cv = source_cv(home)
    if not cv:
        return "Please upload your CV first."
    if not os.path.isfile(os.path.join(home, "profile", "goals.json")):
        return "Please tell us what you're looking for first."
    if profile_ready(home):
        backup_profile(home)  # a returning user rebuilding from a new CV: keep the old profile
    start_task(home, "onboard", cli("onboard", "--home", home, "--cv", cv, "--goals", goals_text(home)),
               done_check=lambda: profile_ready(home))
    return None


def backup_profile(home):
    """Copy the profile files into profile/_previous/<time>/ before they are rebuilt."""
    prof = os.path.join(home, "profile")
    dest = os.path.join(prof, "_previous", datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    os.makedirs(dest, exist_ok=True)
    for name in os.listdir(prof):
        src = os.path.join(prof, name)
        if os.path.isfile(src) and not name.startswith("source_cv"):
            shutil.copy2(src, dest)
    return dest


def apply_goals(home):
    """A returning user changed what they're looking for: fold it into their search settings."""
    if not profile_ready(home):
        return None  # the profile build will read the goals itself
    start_task(home, "goals", cli("apply", "--home", home, "--what", "goals"))
    return None


def questions(home):
    q = _load(os.path.join(home, "profile", "questions.json"), [])
    return q if isinstance(q, list) else []


def save_answers(home, answers):
    if not isinstance(answers, dict):
        return "Bad answers."
    clean = {str(k)[:40]: str(v).strip()[:2000] for k, v in answers.items() if str(v).strip()}
    _save(os.path.join(home, "profile", "answers.json"), clean)
    start_task(home, "answers", cli("apply", "--home", home, "--what", "answers"))
    return None


def request_cv_change(home, text):
    text = (text or "").strip()[:3000]
    if len(text) < 3:
        return "Tell us what to change."
    with open(os.path.join(home, "profile", "change_request.md"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    start_task(home, "revise", cli("apply", "--home", home, "--what", "revise"))
    return None


def preview_pdf(home):
    d = os.path.join(home, "profile", "_preview")
    if not os.path.isdir(d):
        return None
    pdfs = sorted((f for f in os.listdir(d) if f.lower().endswith(".pdf")),
                  key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
    return os.path.join(d, pdfs[0]) if pdfs else None


# ---------- companies to watch ----------

COUNTRY_WORDS = {
    "saudi": ["riyadh", "jeddah", "dammam", "khobar", "saudi", "ksa"],
    "uae": ["dubai", "abu dhabi", "sharjah", "uae", "emirates"],
    "qatar": ["doha", "qatar"], "uk": ["london", "manchester", "uk", "united kingdom"],
    "france": ["paris", "lyon", "france"], "germany": ["berlin", "munich", "hamburg", "germany"],
    "spain": ["barcelona", "madrid", "spain"], "usa": ["new york", "san francisco", "seattle", "usa", "united states"],
}


def feed_catalog():
    return _load(os.path.join(REPO, "docs", "feeds.json"), {}).get("feeds", [])


def selected_boards(home):
    return _load(os.path.join(home, "profile", "boards.json"), {}).get("boards", [])


def save_boards(home, chosen_slugs):
    g = _load(os.path.join(home, "profile", "goals.json"), {})
    cities = [c.strip().lower() for c in re.split(r"[,;/]| and ", g.get("cities", "")) if c.strip()]
    locations = set(cities)
    for words in COUNTRY_WORDS.values():
        if any(w in " ".join(cities) for w in words):
            locations.update(words)
    if "remote" in g.get("cities", "").lower():
        locations.add("remote")
    roles = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z&+-]{2,}", g.get("roles", ""))
             if w.lower() not in ("and", "the", "for", "with", "roles", "role", "manager", "senior", "lead", "head", "junior")]
    by_slug = {f["slug"]: f for f in feed_catalog()}
    boards = []
    for s in chosen_slugs:
        f = by_slug.get(s)
        if f:
            b = {"company": f["company"], "ats": f["ats"], "slug": f["slug"]}
            if f["ats"] == "workday" and cities:
                b["search"] = cities[0].title()
            boards.append(b)
    data = {"filters": {
                "locations": sorted(locations),
                "title_include": sorted(set(roles)),
                "title_exclude": ["intern", "internship", "graduate", "trainee", "student"],
                "level_exclude": [],
                "max_age_days": 30},
            "boards": boards}
    _save(os.path.join(home, "profile", "boards.json"), data)
    return None


# ---------- daily search + schedule ----------

def start_search(home):
    start_task(home, "search", cli("daily", "--home", home, "--force"))


SCHEDULE_NAME = "Job Desk - morning search"


def schedule_status():
    if platform.system() != "Windows":
        return {"supported": False, "enabled": False}
    r = subprocess.run(["schtasks", "/Query", "/TN", SCHEDULE_NAME], capture_output=True, text=True, creationflags=NO_WINDOW)
    return {"supported": True, "enabled": r.returncode == 0}


def set_schedule(home, enabled, time_hhmm="09:00"):
    if platform.system() != "Windows":
        return "Automatic morning searches are only available on Windows for now."
    if not enabled:
        subprocess.run(["schtasks", "/Delete", "/TN", SCHEDULE_NAME, "/F"], capture_output=True, creationflags=NO_WINDOW)
        return None
    if not re.fullmatch(r"\d{2}:\d{2}", time_hhmm or ""):
        time_hhmm = "09:00"
    xml_path = os.path.join(home, "state", "schedule_task.xml")
    os.makedirs(os.path.dirname(xml_path), exist_ok=True)
    with open(xml_path, "w", encoding="utf-16") as f:
        f.write(schedule_xml(python_exe(), os.path.join(CODE, "app.py"), home, time_hhmm))
    r = subprocess.run(["schtasks", "/Create", "/F", "/TN", SCHEDULE_NAME, "/XML", xml_path],
                       capture_output=True, text=True, creationflags=NO_WINDOW)
    return None if r.returncode == 0 else ("Windows refused to create the schedule: " + (r.stderr or r.stdout).strip()[:200])


def schedule_xml(python, app, home, time_hhmm):
    """Task Scheduler definition. Unlike plain `schtasks /SC DAILY`, it runs as soon as the PC is back
    if it was off or asleep at the set time, and also runs on battery (most friends use laptops)."""
    from xml.sax.saxutils import escape
    start = datetime.now().strftime("%Y-%m-%d") + "T" + time_hhmm + ":00"
    args = f'"{app}" --search --home "{home}"'
    return f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Job Desk: find new jobs for you each morning</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>{escape(python)}</Command><Arguments>{escape(args)}</Arguments></Exec>
  </Actions>
</Task>
'''


# ---------- overall state for the page ----------

# ---------- CV design: their own (as is or improved) or the Job Desk design ----------

DESIGNS = {"keep": ("own", False), "improve": ("own", True), "switch": ("jobdesk", False)}
PHOTO_CHOICES = ("keep", "auto", "remove")


def design_settings(home):
    """None until the person has chosen; otherwise {"design", "improved", "photo", "pages"}."""
    d = _load(os.path.join(home, "profile", "cv_design.json"), None)
    return d if isinstance(d, dict) else None


def cv_review(home):
    r = _load(os.path.join(home, "profile", "cv_review.json"), None)
    return r if isinstance(r, dict) else None


def photo_file(home):
    folder = os.path.join(home, "profile", "design")
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.lower().startswith("photo.") and os.path.splitext(name)[1].lower() in (".jpg", ".jpeg", ".png", ".webp"):
                return os.path.join(folder, name)
    return None


def look_image(home, n):
    p = os.path.join(home, "profile", "_look", f"page-{int(n)}.png")
    return p if os.path.isfile(p) else None


def choose_design(home, choice, photo):
    if choice not in DESIGNS:
        return "Please choose one of the three options."
    if not profile_ready(home):
        return "Your profile isn't ready yet."
    design, improved = DESIGNS[choice]
    if not photo_file(home):
        photo = "remove"
    elif photo not in PHOTO_CHOICES:
        return "Please choose what to do with your photo."
    review = cv_review(home) or {}
    try:
        pages = max(1, min(3, int(review.get("pages") or 1)))
    except (TypeError, ValueError):
        pages = 1
    if design == "jobdesk":
        pages = 1
    _save(os.path.join(home, "profile", "cv_design.json"),
          {"design": design, "improved": improved, "photo": photo, "pages": pages, "chosen": choice})
    start_task(home, "design", cli("apply", "--home", home, "--what", "design"))
    return None


def has_picks(home):
    daily = os.path.join(home, "daily")
    return os.path.isdir(daily) and any(os.path.isfile(os.path.join(daily, d, "picks.json")) for d in os.listdir(daily))


def state(home):
    cfg = config(home)
    tasks = task_states(home)
    return {
        "name": cfg.get("owner", ""),
        "claude": claude_status() if not NO_AGENTS else {"installed": True, "logged_in": True, "plan": "test"},
        "has_cv": bool(source_cv(home)),
        "goals": _load(os.path.join(home, "profile", "goals.json"), {}),
        "profile_ready": profile_ready(home),
        "questions": questions(home),
        "answered": os.path.isfile(os.path.join(home, "profile", "answers.json")),
        "preview": bool(preview_pdf(home)),
        "boards": [b.get("slug") for b in selected_boards(home)],
        "setup_done": bool(cfg.get("setup_done")) or has_picks(home),
        "tasks": tasks,
        "schedule": schedule_status() if not NO_AGENTS else {"supported": False, "enabled": False},
        "custom_builder": bool(cfg.get("cv_builder")),
        "review": cv_review(home),
        "design": design_settings(home),
        "has_photo": bool(photo_file(home)),
        "has_look": bool(look_image(home, 1)),
    }


def finish(home):
    cfg = config(home)
    cfg["setup_done"] = True
    _save(os.path.join(home, "config.json"), cfg)
