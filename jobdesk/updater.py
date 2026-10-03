"""Update check and one-click update for installed copies.

The page asks GitHub for the latest release at most twice a day (turn off with
"check_updates": false in config.json). Installed copies (the Windows installer)
can update themselves: the new JobDesk-Setup.exe is downloaded from this
project's GitHub release, its SHA-256 is checked against the release's .sha256
file, then a small script waits for Job Desk to close, runs the installer
silently and opens Job Desk again. Your data folder is never touched.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta

REPO = "achrabieh/job-desk"
RELEASES = f"https://github.com/{REPO}/releases"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
SUPPORT_URL = f"https://github.com/{REPO}#support-job-desk"
ASSET = "JobDesk-Setup.exe"
CODE = os.path.dirname(os.path.abspath(__file__))           # .../app/jobdesk
INSTALL_DIR = os.path.dirname(os.path.dirname(CODE))         # the installer's {app} folder
CHECK_EVERY = timedelta(hours=12)


def current_version():
    try:
        with open(os.path.join(os.path.dirname(CODE), "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "dev"
    except OSError:
        return "dev"


def installed_copy():
    """True when running from the Windows installer's folder (it can update itself)."""
    return sys.platform == "win32" and os.path.isfile(os.path.join(INSTALL_DIR, "unins000.exe"))


def _vtuple(v):
    nums = re.findall(r"\d+", (v or "").split("-")[0])
    return tuple(int(n) for n in nums[:3]) if nums else ()


def newer(latest, current):
    if current == "dev" or "-dev" in current:
        return False
    return _vtuple(latest) > _vtuple(current)


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "job-desk-updater", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _cache_path(home):
    return os.path.join(home, "state", "update.json")


def check(home, force=False, enabled=True):
    """{current, latest, available, can_install, page, support, checked_at, error?}"""
    cur = current_version()
    base = {"current": cur, "can_install": installed_copy(), "page": RELEASES, "support": SUPPORT_URL}
    if not enabled:
        return dict(base, latest=None, available=False, disabled=True)
    cache = {}
    try:
        with open(_cache_path(home), encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        pass
    fresh = False
    try:
        fresh = datetime.now() - datetime.fromisoformat(cache.get("checked_at", "")) < CHECK_EVERY
    except ValueError:
        pass
    if force or not fresh:
        try:
            rel = json.loads(_get(LATEST_API))
            assets = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets", [])}
            cache = {"checked_at": datetime.now().isoformat(timespec="seconds"),
                     "latest": (rel.get("tag_name") or "").lstrip("v"), "page": rel.get("html_url") or RELEASES,
                     "setup_url": assets.get(ASSET), "sha_url": assets.get(ASSET + ".sha256")}
        except Exception as e:  # noqa: BLE001 - offline, private repo, rate limit: just say we couldn't check
            cache = dict(cache, checked_at=datetime.now().isoformat(timespec="seconds"), error=type(e).__name__)
        os.makedirs(os.path.dirname(_cache_path(home)), exist_ok=True)
        with open(_cache_path(home), "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    latest = cache.get("latest")
    out = dict(base, latest=latest, checked_at=cache.get("checked_at"), page=cache.get("page") or RELEASES,
               available=bool(latest) and newer(latest, cur))
    if cache.get("error") and not latest:
        out["error"] = "Couldn't reach GitHub to check for updates."
    return out


def _trusted(url):
    return isinstance(url, str) and url.startswith(f"https://github.com/{REPO}/releases/download/")


def cleanup_downloads():
    """Remove installers left in the temp folder by earlier updates."""
    import glob
    import shutil
    for d in glob.glob(os.path.join(tempfile.gettempdir(), "jobdesk-update-*")):
        shutil.rmtree(d, ignore_errors=True)


def start_update(home):
    """Download, verify and launch the new installer. Returns an error message or None.
    The caller must stop the server right after, so the installer can replace the files."""
    if not installed_copy():
        return "This copy wasn't installed with the Job Desk installer. Download the new version from GitHub instead."
    info = check(home, force=True)
    if not info.get("available"):
        return "You already have the latest version."
    with open(_cache_path(home), encoding="utf-8") as f:
        cache = json.load(f)
    setup_url, sha_url = cache.get("setup_url"), cache.get("sha_url")
    if not (_trusted(setup_url) and _trusted(sha_url)):
        return "The new version isn't published correctly yet. Please try again later."
    try:
        expected = _get(sha_url).decode("ascii", "replace").split()[0].lower()
        data = _get(setup_url, timeout=300)
    except Exception:  # noqa: BLE001
        return "The download didn't finish. Check your internet connection and try again."
    if hashlib.sha256(data).hexdigest() != expected:
        return "The download didn't pass its safety check, so it wasn't installed. Please try again later."
    folder = tempfile.mkdtemp(prefix="jobdesk-update-")
    setup = os.path.join(folder, f"JobDesk-Setup-{info['latest']}.exe")
    with open(setup, "wb") as f:
        f.write(data)
    pythonw = os.path.join(INSTALL_DIR, "python", "pythonw.exe")
    app = os.path.join(CODE, "app.py")
    script = os.path.join(folder, "update.cmd")
    with open(script, "w", encoding="utf-8") as f:
        f.write("@echo off\r\n"
                "ping -n 4 127.0.0.1 >nul\r\n"  # let the page server close first
                f'"{setup}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS\r\n'
                f'start "" "{pythonw}" "{app}" --home "{home}" --no-browser\r\n')  # the open page reloads itself
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(["cmd.exe", "/c", script], creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return None
