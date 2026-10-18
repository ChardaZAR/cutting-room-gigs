import json
import os
import re
import sys
import urllib.request
from server import load_state, match_rules, send_email_alert, send_windows_notification

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_PATH = os.path.join(BASE_DIR, "jobs.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fetch(url, timeout=12):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", "ignore")


def check_existing_jobs(jobs_path=JOBS_PATH):
    with open(jobs_path, encoding="utf-8") as f:
        data = json.load(f)
    state = load_state()
    rules = state.get("alertRules", [])
    print(f"=== Checking {len(data.get('jobs', []))} existing listings in {jobs_path} ===")
    existing_urls = set()
    for j in data.get("jobs", []):
        url = j["url"]
        existing_urls.add(url.rstrip("/"))
        matched = match_rules(j, rules)
        match_tag = f" [MATCHES ALERT: {', '.join(r.get('keyword') or r.get('niche') for r in matched)}]" if matched else ""
        try:
            _, html = fetch(url)
            closed = re.findall(
                r"(Sorry, this job was removed|no longer accepting|job is closed|no longer available)",
                html,
                re.I,
            )
            flag = f"CLOSED ({closed[0]})" if closed else "OPEN"
            print(f"  [{flag}] {j['id']} ({j['source']}): {url}{match_tag}")
        except Exception as e:
            print(f"  [WARN: {e}] {j['id']} ({j['source']}): {url}{match_tag}")
    return existing_urls


def discover_candidates(existing_urls):
    sources = [
        ("YT.Careers", "https://yt.careers/youtube-jobs", r'href=["\'](/youtube-jobs/\d+)["\']', "https://yt.careers"),
        ("Remote Rocketship", "https://www.remoterocketship.com/country/worldwide/jobs/video-editor/", r'href=["\'](/us/company/[^"\']+/jobs/[^"\']*video-editor[^"\']*)["\']', "https://www.remoterocketship.com"),
        ("Dynamite Jobs", "https://dynamitejobs.com/skill/remote-video-editing-jobs", r'href=["\'](/company/[^"\']+/remote-job/[^"\']+)["\']', "https://dynamitejobs.com"),
        ("Twine", "https://www.twine.net/jobs/video-editors", r'href=["\'](https://www\.twine\.net/projects/[^"\']+|/projects/[^"\']+)["\']', "https://www.twine.net"),
        ("Podnews RSS", "https://podnews.net/prebuilt/rss-jobs.xml", r"<link>(https://podnews\.net/job/[^<]+)</link>", ""),
    ]
    print("\n=== Discovering New Candidate Links ===")
    for name, board_url, pattern, prefix in sources:
        try:
            _, html = fetch(board_url)
            matches = []
            for m in re.findall(pattern, html, re.I):
                full = m if m.startswith("http") else prefix + m
                norm = full.rstrip("/")
                if norm not in existing_urls and full not in matches:
                    matches.append(full)
            print(f"\n[{name}] ({len(matches)} new links not in jobs.json):")
            for link in matches[:15]:
                print(f"  - {link}")
        except Exception as e:
            print(f"\n[{name}] ERROR: {e}")


def notify_for_job_ids(job_ids):
    with open(JOBS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    state = load_state()
    rules = state.get("alertRules", [])
    notify_cfg = state.get("notifyCfg", {})
    new_jobs = [j for j in data.get("jobs", []) if j["id"] in job_ids]
    matched = [j for j in new_jobs if match_rules(j, rules)]
    if not matched:
        print("No new jobs matched custom alert rules.")
        return
    if notify_cfg.get("desktop", True):
        send_windows_notification(
            f"Cutting Room Gigs: {len(matched)} New Match(es)!",
            ", ".join(f"{j['title']} ({j['company']})" for j in matched[:3]),
        )
        print(f"Sent Windows desktop notification for {len(matched)} matching job(s).")
    if notify_cfg.get("emailEnabled"):
        ok, info = send_email_alert(notify_cfg, matched)
        print(f"Email notification status: {ok} ({info})")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--notify":
        ids = set(sys.argv[2].split(","))
        notify_for_job_ids(ids)
    else:
        existing = check_existing_jobs()
        discover_candidates(existing)
