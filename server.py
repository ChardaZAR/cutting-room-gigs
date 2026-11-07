import datetime
import email.message
import http.server
import json
import os
import re
import smtplib
import socketserver
import subprocess
import sys
import threading
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_PATH = os.path.join(BASE_DIR, "jobs.json")
STATE_PATH = os.path.join(BASE_DIR, "user-state.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Requests run on separate threads, so a slow sweep doesn't freeze the board.
# STATE_LOCK guards user-state.json read-modify-write; SWEEP_LOCK keeps sweeps (which rewrite jobs.json) one at a time.
STATE_LOCK = threading.Lock()
SWEEP_LOCK = threading.Lock()


def fetch_html(url, timeout=10):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "status": {},
        "appliedMeta": {},
        "alertRules": [
            {
                "id": "default-pod",
                "keyword": "Podcast Editor",
                "niche": "podcast",
                "type": "any",
                "world": "any",
            }
        ],
        "disabledSources": [],
        "notifyCfg": {
            "desktop": True,
            "emailEnabled": False,
            "emailTo": "",
            "smtpUser": "",
            "smtpPass": "",
        },
    }


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def match_rules(job, rules):
    hay = " ".join(
        [
            job.get("title", ""),
            job.get("company", ""),
            job.get("notes", ""),
            job.get("pay", ""),
            " ".join(job.get("niche", [])),
        ]
    ).lower()
    matched = []
    for r in rules or []:
        if r.get("niche") and r["niche"] != "any" and r["niche"] not in job.get("niche", []):
            continue
        if r.get("type") and r["type"] != "any" and job.get("type") != r["type"]:
            continue
        if r.get("world") == "world" and job.get("region") != "world":
            continue
        kw = (r.get("keyword") or "").strip().lower()
        if kw:
            words = [w for w in kw.split() if w]
            if not all(w in hay for w in words):
                continue
        matched.append(r)
    return matched


def send_windows_notification(title, message):
    ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true
$notify.ShowBalloonTip(6000, {json.dumps(title)}, {json.dumps(message)}, [System.Windows.Forms.ToolTipIcon]::Info)
Start-Sleep -Seconds 2
$notify.Dispose()
"""
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            cwd=BASE_DIR,
        )
    except Exception as e:
        print(f"Notification warning: {e}")


def send_email_alert(notify_cfg, matched_jobs):
    to_addr = (notify_cfg.get("emailTo") or "").strip()
    smtp_user = (notify_cfg.get("smtpUser") or "").strip()
    smtp_pass = (notify_cfg.get("smtpPass") or "").strip()
    if not (to_addr and smtp_user and smtp_pass):
        return False, "Missing Recipient Email, SMTP User, or SMTP App Password"

    msg = email.message.EmailMessage()
    msg["Subject"] = f"Cutting Room Gigs Alert: {len(matched_jobs)} matching role(s)"
    msg["From"] = smtp_user
    msg["To"] = to_addr

    lines = ["New remote video editing jobs matching your Cutting Room Gigs alert rules:\n"]
    for j in matched_jobs:
        lines.append(f"• {j.get('title')} — {j.get('company')} ({j.get('pay') or 'Pay not listed'})")
        lines.append(f"  Niche: {', '.join(j.get('niche', []))} | Region: {j.get('region')}")
        lines.append(f"  Link: {j.get('url')}\n")
    msg.set_content("\n".join(lines))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as smtp:
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
        return True, "Sent"
    except Exception as e:
        return False, str(e)


def run_live_sweep(override_disabled=None):
    from sweep import scrape_all_sources

    with STATE_LOCK:
        state = load_state()
        if isinstance(override_disabled, list):
            state["disabledSources"] = override_disabled
            save_state(state)
    disabled_sources = set(state.get("disabledSources") or [])

    with SWEEP_LOCK:
        res = scrape_all_sources(disabled_sources=disabled_sources)
    data = res["data"]
    added_jobs = res["added"]
    removed_jobs = res["removed"]

    # Check alerts for newly added jobs (excluding disabled sources)
    rules = state.get("alertRules", [])
    notify_cfg = state.get("notifyCfg", {})
    matched_new = [
        j
        for j in added_jobs
        if j.get("source") not in disabled_sources and match_rules(j, rules)
    ]
    if matched_new:
        if notify_cfg.get("desktop", True):
            send_windows_notification(
                f"Cutting Room Gigs: {len(matched_new)} New Match(es)!",
                ", ".join(f"{j['title']} ({j['company']})" for j in matched_new[:3]),
            )
        if notify_cfg.get("emailEnabled"):
            send_email_alert(notify_cfg, matched_new)

    return {"data": data, "added": added_jobs, "removed": removed_jobs, "matchedAlerts": matched_new}


class BoardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        # Make the browser re-check index.html / jobs.js each load so updates show up without a hard refresh
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, obj, code=200):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/state"):
            self._send_json(load_state())
            return
        super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(length).decode("utf-8", "ignore") if length else "{}"
        try:
            body = json.loads(body_raw) if body_raw else {}
        except Exception:
            body = {}

        if self.path.startswith("/api/state"):
            with STATE_LOCK:
                state = load_state()
                for dict_key in ("status", "statusBySig", "appliedMeta", "notifyCfg"):
                    if isinstance(body.get(dict_key), dict):
                        state[dict_key] = body[dict_key]
                for list_key in ("alertRules", "disabledSources"):
                    if isinstance(body.get(list_key), list):
                        state[list_key] = body[list_key]
                if "updatedAt" in body:
                    state["updatedAt"] = body["updatedAt"]
                save_state(state)
            # If a sweep is running, skip this: the sweep rewrites the bundles (with this state) when it finishes
            if SWEEP_LOCK.acquire(blocking=False):
                try:
                    from sweep import sync_static_bundles
                    if os.path.exists(JOBS_PATH):
                        with open(JOBS_PATH, encoding="utf-8") as f:
                            jdata = json.load(f)
                        sync_static_bundles(jdata)
                except Exception:
                    pass
                finally:
                    SWEEP_LOCK.release()
            self._send_json({"ok": True})
            return

        if self.path.startswith("/api/sweep"):
            res = run_live_sweep(override_disabled=body.get("disabledSources"))
            self._send_json(res)
            return

        if self.path.startswith("/api/notify-test"):
            ntype = body.get("type", "desktop")
            if ntype == "desktop":
                msg = body.get("message") or "Your Cutting Room Gigs desktop notifications are active!"
                send_windows_notification("Cutting Room Gigs Alert", msg)
                self._send_json({"ok": True})
                return
            elif ntype == "email":
                cfg = body.get("notifyCfg") or load_state().get("notifyCfg", {})
                matched = body.get("matched") or []
                ok, err = send_email_alert(cfg, matched)
                self._send_json({"ok": ok, "error": err})
                return

        self._send_json({"error": "Not found"}, 404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), BoardHandler) as httpd:
        print(f"Cutting Room Gigs server running at http://localhost:{port}")
        httpd.serve_forever()
