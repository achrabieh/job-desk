"""Job Desk desktop launcher (what the installer's icon runs).

    pythonw app.py                    # start (or reuse) the page and open the browser
    pythonw app.py --search           # run today's search silently (used by the morning schedule)
    pythonw app.py --home DIR         # use a different data folder

Data lives in "Documents/Job Desk" by default, separate from the program, so
updating or reinstalling never touches a user's CV or history.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

CODE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODE)


def default_home():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    if sys.platform == "win32":
        try:  # the real Documents folder, even when OneDrive moved it
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                docs = buf.value
        except Exception:  # noqa: BLE001
            pass
    return os.path.join(docs, "Job Desk")


def ensure_home(home):
    for d in ("profile", "daily", "state", "logs"):
        os.makedirs(os.path.join(home, d), exist_ok=True)
    cfg = os.path.join(home, "config.json")
    if not os.path.exists(cfg):
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"owner": "", "port": 8765, "networks": []}, f, indent=2)
    for rel, default in (("state/seen.json", {"jobs": {}}), ("state/decisions.json", {})):
        p = os.path.join(home, rel)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                json.dump(default, f)


def port_of(home):
    try:
        with open(os.path.join(home, "config.json"), encoding="utf-8-sig") as f:
            return int(json.load(f).get("port", 8765))
    except (OSError, ValueError, json.JSONDecodeError):
        return 8765


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def serves_home(port, home):
    """Is the Job Desk on this port using this data folder? (Another one may be running, e.g. a developer's.)"""
    import setup_wizard
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/whoami", timeout=3) as r:
            return json.load(r).get("id") == setup_wizard.home_id(home)
    except Exception:  # noqa: BLE001 - older version or something else on the port
        return False


def free_port(start):
    for p in range(start, start + 50):
        if not port_open(p):
            return p
    return start


def set_port(home, port):
    cfg_path = os.path.join(home, "config.json")
    with open(cfg_path, encoding="utf-8-sig") as f:
        cfg = json.load(f)
    cfg["port"] = port
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=os.environ.get("JOB_DESK_HOME") or default_home())
    ap.add_argument("--search", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    home = os.path.abspath(a.home)
    ensure_home(home)

    if a.search:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.call([sys.executable, os.path.join(CODE, "cli.py"), "daily", "--home", home], creationflags=flags)

    port = port_of(home)
    url = f"http://127.0.0.1:{port}/"
    if port_open(port):
        if serves_home(port, home):  # already running: just show it
            if not a.no_browser:
                webbrowser.open(url)
            return 0
        port = free_port(port + 1)  # a different Job Desk has this port: use our own from now on
        set_port(home, port)
        url = f"http://127.0.0.1:{port}/"
    try:  # the previous update's installer is no longer needed
        import updater
        updater.cleanup_downloads()
    except Exception:  # noqa: BLE001
        pass
    os.environ["JOB_DESK_HOME"] = home
    os.environ["JOB_DESK_PORT"] = str(port)
    import server
    t = threading.Thread(target=server.main, daemon=True)
    t.start()
    for _ in range(40):
        if port_open(port):
            break
        time.sleep(0.25)
    if not a.no_browser:
        webbrowser.open(url)
    t.join()
    return 0


if __name__ == "__main__":
    sys.exit(main())
