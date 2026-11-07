import datetime
import email.utils
import html as html_lib
import json
import os
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_PATH = os.path.join(BASE_DIR, "jobs.json")
JS_PATH = os.path.join(BASE_DIR, "jobs.js")
STATE_PATH = os.path.join(BASE_DIR, "user-state.json")
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
STANDALONE_PATH = os.path.join(BASE_DIR, "cutting-room-gigs-standalone.html")

MAX_AGE_DAYS = 14

# Only these user-state keys are embedded in jobs.js / standalone HTML (which get committed and published).
# notifyCfg holds the alert email address and SMTP app password, so it must never leave user-state.json.
PUBLIC_STATE_KEYS = ("status", "statusBySig", "appliedMeta", "alertRules", "disabledSources", "updatedAt")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/json,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

ASHBY_BOARDS = [
    ("aidigest", "AI Digest"),
    ("newform", "Newform"),
    ("dreamthree", "Dream Three"),
    ("revstone", "RevStone"),
    ("acquisition", "Acquisition.com"),
    ("hirehangar", "Hire Hangar"),
    ("superpower", "Superpower"),
    ("rehire", "Rehire"),
    ("stemwave", "StemWave"),
    ("cge", "Content Growth Engine"),
    ("whop", "Whop"),
]

WORKABLE_BOARDS = [
    ("virtuhire", "VirtuHire"),
    ("pavago", "Pavago"),
    ("crewbloom", "CrewBloom"),
    ("reworkssolutions", "ReWorks Solutions"),
    ("hirehawk", "HireHawk"),
    ("huzzle", "Huzzle"),
]


def clean_str(s):
    if not s:
        return ""
    text = html_lib.unescape(html_lib.unescape(str(s)))
    text = re.sub(r"\s+", " ", text).strip()
    return text


_prefetched = {}


def prefetch(urls, timeout=10, workers=8):
    """Fetch many pages in parallel; fetch_text() then serves them from memory instead of waiting on each in turn."""
    todo = [u for u in dict.fromkeys(urls) if u not in _prefetched]

    def one(u):
        try:
            return u, _fetch_live(u, timeout)
        except Exception as e:
            return u, e

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for u, result in ex.map(one, todo):
            _prefetched[u] = result


def fetch_text(url, timeout=12):
    if url in _prefetched:
        result = _prefetched.pop(url)
        if isinstance(result, Exception):
            raise result
        return result
    return _fetch_live(url, timeout)


def _fetch_live(url, timeout=12):
    """Fetch URL content using curl (avoids TLS fingerprint 403s) with urllib fallback."""
    curl_bin = "curl.exe" if os.name == "nt" else "curl"
    try:
        res = subprocess.run(
            [
                curl_bin,
                "-sfL",
                "--max-time",
                str(timeout),
                "-H",
                f"Accept: {HEADERS['Accept']}",
                "-H",
                f"Accept-Language: {HEADERS['Accept-Language']}",
                "-A",
                UA,
                url,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout + 3,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout
    except Exception:
        pass

    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def parse_iso_or_date(val):
    if not val:
        return None
    val = str(val).strip()
    try:
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        pass
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", val)
    if m:
        return datetime.datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, 0, tzinfo=datetime.timezone.utc
        )
    return None


def parse_relative_age_to_dt(text):
    """Convert phrases like '9 hours ago', '1 day ago', '4 days ago', 'Updated October 19, 2026' to UTC datetime."""
    if not text:
        return None
    t = text.lower()
    now = now_utc()

    if "just now" in t or "minutes ago" in t or "minute ago" in t:
        m = re.search(r"(\d+)\s*minute", t)
        mins = int(m.group(1)) if m else 15
        return now - datetime.timedelta(minutes=mins)

    m_hr = re.search(r"(\d+)\s*hour", t)
    if m_hr:
        return now - datetime.timedelta(hours=int(m_hr.group(1)))

    if "posted today" in t or "opened today" in t or t.strip() == "today":
        return now - datetime.timedelta(hours=3)

    if "posted yesterday" in t or "opened yesterday" in t or "1 day ago" in t or "a day ago" in t or t.strip() == "yesterday":
        return now - datetime.timedelta(days=1)

    m_day = re.search(r"(?:posted|opened|🕒)?\s*~?(\d+)\s*days?\s*ago", t)
    if m_day:
        return now - datetime.timedelta(days=int(m_day.group(1)))

    if "month ago" in t or "months ago" in t:
        m_mo = re.search(r"(\d+)\s*months?\s*ago", t)
        months = int(m_mo.group(1)) if m_mo else 1
        return now - datetime.timedelta(days=30 * months)

    months_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    m_mdy = re.search(
        r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:,\s*(\d{4}))?",
        t,
    )
    if m_mdy:
        mo = months_map[m_mdy.group(1)[:3]]
        day = int(m_mdy.group(2))
        yr = int(m_mdy.group(3)) if m_mdy.group(3) else now.year
        try:
            return datetime.datetime(yr, mo, day, 12, 0, tzinfo=datetime.timezone.utc)
        except Exception:
            pass

    m_dmy = re.search(
        r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*(?:\s+(\d{4}))?",
        t,
    )
    if m_dmy:
        day = int(m_dmy.group(1))
        mo = months_map[m_dmy.group(2)[:3]]
        yr = int(m_dmy.group(3)) if m_dmy.group(3) else now.year
        try:
            return datetime.datetime(yr, mo, day, 12, 0, tzinfo=datetime.timezone.utc)
        except Exception:
            pass

    return None


def is_within_max_age(dt, max_days=MAX_AGE_DAYS):
    if not dt:
        return False
    age = now_utc() - dt
    return age.total_seconds() <= (max_days + 0.25) * 86400


def format_posted_label(dt):
    if not dt:
        return "Posted recently"
    diff = now_utc() - dt
    secs = max(0, diff.total_seconds())
    date_part = dt.strftime("%d %b").lstrip("0")
    if secs < 3600:
        mins = max(1, int(secs // 60))
        return f"Posted {mins}m ago · {date_part}"
    if secs < 86400:
        hrs = max(1, int(secs // 3600))
        return f"Posted {hrs}h ago · {date_part}"
    days = int(secs // 86400)
    if days == 1:
        return f"Posted 1d ago · {date_part}"
    return f"Posted {days}d ago · {date_part}"


def infer_niche(title, extra=""):
    text = f"{title} {extra}".lower()
    niches = []
    if any(k in text for k in ["short", "tiktok", "reel", "ugc", "social", "clipper", "ad creative", "meta", "dtc", "performance", "facebook ad"]):
        niches.append("social")
    if any(k in text for k in ["podcast", "vodcast", "audio", "interview"]):
        niches.append("podcast")
    if any(k in text for k in ["youtube", "longform", "long-form", "creator", "retention", "documentary", "vlog", "reaction"]):
        niches.append("youtube")
    if not niches:
        niches.append("youtube")
    return niches[:2]


def is_editing_role(title):
    t = (title or "").lower()
    if any(bad in t for bad in ["wordpress", "website editor", "copy editor", "text editor", "book editor", "videographer", "on-site", "onsite", "in-person", "internship"]):
        return False
    return any(
        kw in t
        for kw in [
            "video editor",
            "video editing",
            "shortform video",
            "short-form video",
            "longform video",
            "long-form video",
            "youtube editor",
            "podcast editor",
            "podcast & video editor",
            "reels editor",
            "reel editor",
            "tiktok editor",
            "ugc editor",
            "vsl editor",
            "documentary editor",
            "creative lead - video",
            "editor for",
            "looking for an editor",
            "looking for a video editor",
            "clipper",
        ]
    )


def is_eligible_for_sa(location_str, title_str=""):
    """Skip roles locked exclusively to US, UK, EU, LATAM-only, or Philippines-only unless Africa/SA/Worldwide is included."""
    combined = f"{location_str} {title_str}".lower()
    if any(k in combined for k in ["south africa", "africa", "worldwide", "anywhere", "global", "emea", "cet"]):
        return True, "world"
    if any(
        locked in combined
        for locked in [
            "argentina",
            "buenos aires",
            "costa rica",
            "mexico",
            "colombia",
            "brazil",
            "el salvador",
            "honduras",
            "nicaragua",
            "philippines",
            "latam only",
            "| latam",
            "- latam",
            "(latam)",
            "-latam",
            "southeast asia",
            "united states only",
            "us only",
            "u.s. only",
            "uk only",
            "dublin",
            "miami",
            "new york",
            "austin, tx",
        ]
    ):
        return False, "limited"
    if "remote" in combined:
        return True, "world"
    return True, "unknown"


def sync_static_bundles(data):
    """Sync jobs.json -> jobs.js and cutting-room-gigs-standalone.html (including user-state.json if present)."""
    with open(JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    minified = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    state_obj = {}
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as sf:
                state_obj = json.load(sf)
        except Exception:
            state_obj = {}
    state_obj = {k: v for k, v in state_obj.items() if k in PUBLIC_STATE_KEYS}
    minified_state = json.dumps(state_obj, separators=(",", ":"), ensure_ascii=False)

    with open(JS_PATH, "w", encoding="utf-8") as f:
        f.write(f"window.CRG_DATA = {minified};\nwindow.CRG_STATE = {minified_state};\n")

    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, encoding="utf-8") as f:
            html = f.read()
        inline_script = f"<script>window.CRG_DATA = {minified};\nwindow.CRG_STATE = {minified_state};</script>"
        standalone_html = html.replace('<script src="jobs.js"></script>', inline_script)
        with open(STANDALONE_PATH, "w", encoding="utf-8") as f:
            f.write(standalone_html)


REDDIT_RSS_URL = "https://www.reddit.com/r/YouTubeEditorsForHire+CreatorServices+VideoEditors_forhire+HireAnEditor/new/.rss?limit=60"
INDEX_URLS = {
    "Reddit": [REDDIT_RSS_URL],
    "Twine": ["https://www.twine.net/jobs/video-editors"],
    "YT.Careers": ["https://yt.careers/youtube-jobs"],
    "Dynamite Jobs": ["https://dynamitejobs.com/skill/remote-video-editing-jobs"],
    "Ashby": [f"https://api.ashbyhq.com/posting-api/job-board/{slug}" for slug, _ in ASHBY_BOARDS],
    "Workable": [f"https://apply.workable.com/api/v1/widget/accounts/{slug}" for slug, _ in WORKABLE_BOARDS],
    "Podnews": ["https://podnews.net/prebuilt/rss-jobs.xml"],
    "Remote Rocketship": ["https://www.remoterocketship.com/country/worldwide/jobs/video-editor/"],
    "Somewhere / Hirezar": ["https://hirezar.co.za/jobs/?q=video+editor"],
}


def scrape_all_sources(disabled_sources=None):
    disabled = set(disabled_sources or [])
    _prefetched.clear()
    prefetch([u for src, urls in INDEX_URLS.items() if src not in disabled for u in urls], timeout=12)
    collected = []
    seen_urls = set()
    seen_sigs = set()
    existing_jobs = []
    if os.path.exists(JOBS_PATH):
        try:
            with open(JOBS_PATH, encoding="utf-8") as ef:
                existing_jobs = json.load(ef).get("jobs", [])
        except Exception:
            existing_jobs = []

    def add_job(job, dt, dedup_key=None):
        if not dt or not is_within_max_age(dt, MAX_AGE_DAYS):
            return False
        url = (job.get("url") or "").strip()
        if not url:
            return False
        norm_url = url.rstrip("/").lower()
        sig = dedup_key or f"{job.get('title','').strip().lower()}::{job.get('company','').strip().lower()}"
        if norm_url in seen_urls or sig in seen_sigs:
            return False
        seen_urls.add(norm_url)
        seen_sigs.add(sig)
        job["title"] = clean_str(job.get("title", ""))
        job["company"] = clean_str(job.get("company", ""))
        job["notes"] = clean_str(job.get("notes", ""))
        job["pay"] = clean_str(job.get("pay", ""))
        job["publishedAt"] = dt.isoformat()
        job["posted"] = format_posted_label(dt)
        collected.append((dt, job))
        return True

    def keep_existing(match, max_days=MAX_AGE_DAYS):
        """Carry over still-fresh jobs from the last sweep when a source (or one listing) can't be fetched."""
        for ej in existing_jobs:
            if not match(ej):
                continue
            dt = parse_iso_or_date(ej.get("publishedAt"))
            if dt and is_within_max_age(dt, max_days):
                add_job(dict(ej), dt, dedup_key=f"kept::{ej.get('id')}")

    def from_source(name):
        return lambda ej: ej.get("source") == name

    def with_url(url):
        return lambda ej: (ej.get("url") or "").rstrip("/").lower() == url.rstrip("/").lower()

    def with_id_prefix(prefix):
        return lambda ej: (ej.get("id") or "").startswith(prefix)

    # 1. Reddit Live RSS (r/YouTubeEditorsForHire + r/CreatorServices + r/VideoEditors_forhire + r/HireAnEditor)
    if "Reddit" not in disabled:
        try:
            rss = fetch_text(REDDIT_RSS_URL, timeout=12)
            entries = re.findall(r"<entry>(.*?)</entry>", rss, re.S)
            if not entries:
                raise ValueError("feed returned no entries (blocked or rate-limited)")
            for entry in entries:
                t_m = re.search(r"<title>(.*?)</title>", entry)
                l_m = re.search(r'<link href="([^"]+)"', entry)
                u_m = re.search(r"<updated>(.*?)</updated>", entry)
                a_m = re.search(r"<name>(.*?)</name>", entry)
                c_m = re.search(r"<content[^>]*>(.*?)</content>", entry, re.S)
                if not (t_m and l_m and u_m):
                    continue
                raw_title = clean_str(t_m.group(1))
                if not re.search(r"\[\s*hiring\s*\]", raw_title, re.I):
                    continue
                if "for hire" in raw_title.lower():
                    continue
                clean_title = re.sub(r"^\s*\[\s*hiring\s*\]\s*[-–—:]?\s*", "", raw_title, flags=re.I).strip()
                if not is_editing_role(clean_title) and "editor" not in clean_title.lower():
                    continue
                link = l_m.group(1).strip()
                if "/comments/" not in link:
                    continue
                dt = parse_iso_or_date(u_m.group(1))
                if not dt or not is_within_max_age(dt, 7):
                    continue
                author = clean_str(a_m.group(1)) if a_m else "Creator"
                sub_m = re.search(r"/r/([^/]+)/", link)
                sub_name = f"r/{sub_m.group(1)}" if sub_m else "Reddit"
                body_txt = ""
                if c_m:
                    body_raw = html_lib.unescape(html_lib.unescape(c_m.group(1)))
                    body_txt = re.sub(r"<[^>]+>", " ", body_raw)
                    body_txt = re.sub(r"submitted by.*", "", body_txt, flags=re.I)
                    body_txt = clean_str(body_txt)
                pay_m = re.search(r"(\$\d[\d,]*(?:\s*[-–to]+\s*\$?\s*\d[\d,kK]*)?(?:\s*(?:per|\/)\s*(?:hr|hour|video|min|minute|month|mo|project|short|reel))?)", f"{raw_title} {body_txt}", re.I)
                pay = pay_m.group(1) if pay_m else ""
                post_id_m = re.search(r"/comments/([a-z0-9]+)/", link)
                pid = post_id_m.group(1) if post_id_m else re.sub(r"[^a-z0-9]+", "", clean_title.lower())[:12]
                add_job(
                    {
                        "id": f"reddit-{pid}",
                        "title": clean_title,
                        "company": f"{sub_name} ({author})",
                        "source": "Reddit",
                        "url": link,
                        "niche": infer_niche(clean_title, body_txt[:400]),
                        "type": "freelance",
                        "region": "world",
                        "pay": pay,
                        "notes": (body_txt[:190] + "…") if len(body_txt) > 190 else (body_txt or f"Direct creator hiring post on {sub_name}."),
                    },
                    dt,
                    dedup_key=f"reddit::{clean_title.lower()}::{author.lower()}",
                )
        except Exception as e:
            print(f"[Reddit warn] {e} — keeping existing <=7d Reddit jobs")
            keep_existing(from_source("Reddit"), max_days=7)

    # 2. Twine Direct Project Listings
    if "Twine" not in disabled:
        try:
            tw_index = fetch_text("https://www.twine.net/jobs/video-editors", timeout=12)
            tw_paths = list(dict.fromkeys(re.findall(r"(?:https://www\.twine\.net)?(/projects/[a-z0-9-]+)", tw_index)))
            if not tw_paths:
                raise ValueError("index page had no project links (blocked or layout changed)")
            prefetch(f"https://www.twine.net{p}" for p in tw_paths[:12])
            for path in tw_paths[:12]:
                if "-in-" in path and "-remote-job" not in path:
                    continue
                url = f"https://www.twine.net{path}"
                try:
                    phtml = fetch_text(url, timeout=10)
                    ptext = re.sub(r"<script.*?</script>|<style.*?</style>", " ", phtml, flags=re.S)
                    ptext = clean_str(re.sub(r"<[^>]+>", " ", ptext))
                    if "Job details" not in ptext:
                        continue
                    after_details = ptext.split("Job details", 1)[1][:1200]
                    posted_m = re.search(r"(Posted today|Posted yesterday|Posted \d+ days? ago)", after_details, re.I)
                    if not posted_m:
                        continue
                    dt = parse_relative_age_to_dt(posted_m.group(1))
                    if not dt or not is_within_max_age(dt, MAX_AGE_DAYS):
                        continue
                    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", phtml, re.S)
                    t_tag = re.search(r"<title>(.*?)</title>", phtml, re.S)
                    if h1_m:
                        h1_clean = re.sub(r"<span[^>]*>.*?</span>", "", h1_m.group(1), flags=re.S)
                        title = clean_str(re.sub(r"<[^>]+>", " ", h1_clean))
                    elif t_tag:
                        title = re.sub(r"^\[.*?\]\s*|\s*freelance job\s*\|\s*Twine.*$", "", clean_str(t_tag.group(1)), flags=re.I).strip()
                    else:
                        title = "Remote Video Editor"
                    if not title or title == "Remote Video Editor":
                        slug_words = path.split("/projects/")[1].split("-")[1:]
                        if slug_words:
                            title = " ".join(slug_words).replace("remote job", "").strip().title() or "Remote Video Editor"
                    pay_m = re.search(r"Video Editor\s+(?:Searching|Urgent|Mentorship)?\s*(\$[\d,]+(?:\s*[–\-]\s*\$[\d,]+)?|Open to offers)", after_details)
                    pay = pay_m.group(1).strip() if pay_m else "Open to offers"
                    desc_m = re.search(r"Contact via Twine\s+(.*?)(?:In what capacity|What type of|Similar jobs|$)", after_details)
                    notes = desc_m.group(1).strip()[:200] if desc_m else "Remote freelance video editing brief on Twine."
                    slug_id = path.split("/projects/")[1].split("-")[0]
                    add_job(
                        {
                            "id": f"twine-{slug_id}",
                            "title": title,
                            "company": "Twine Client",
                            "source": "Twine",
                            "url": url,
                            "niche": infer_niche(title, notes),
                            "type": "freelance",
                            "region": "world",
                            "pay": pay,
                            "notes": notes,
                        },
                        dt,
                    )
                except Exception:
                    keep_existing(with_url(url))
        except Exception as e:
            print(f"[Twine warn] {e} — keeping existing Twine jobs")
            keep_existing(from_source("Twine"))

    # 3. YT.Careers Direct Job Posts
    if "YT.Careers" not in disabled:
        try:
            html = fetch_text("https://yt.careers/youtube-jobs", timeout=12)
            ids = list(dict.fromkeys(re.findall(r"/youtube-jobs/(\d+)", html)))
            if not ids:
                raise ValueError("index page had no job links (blocked or layout changed)")
            prefetch(f"https://yt.careers/youtube-jobs/{jid}" for jid in ids[:14])
            for jid in ids[:14]:
                url = f"https://yt.careers/youtube-jobs/{jid}"
                try:
                    jhtml = fetch_text(url, timeout=10)
                    cleaned = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", " ", jhtml, flags=re.S)
                    text = clean_str(re.sub(r"<[^>]+>", " ", cleaned))
                    if "Back to all job posts" not in text:
                        continue
                    body = text.split("Back to all job posts", 1)[1][:1500]
                    if "Onsite" in body[:300]:
                        continue
                    age_m = re.search(r"-->\s*(About \d+ hours? ago|\d+ hours? ago|1 day ago|\d+ days? ago|About \d+ months? ago|\d+ months? ago)\s*Apply", body, re.I)
                    if not age_m:
                        continue
                    age_str = age_m.group(1)
                    if "month" in age_str.lower():
                        continue
                    dt = parse_relative_age_to_dt(age_str)
                    if not dt or not is_within_max_age(dt, MAX_AGE_DAYS):
                        continue
                    title_m = re.search(r"<title>(.*?)</title>", jhtml, re.S)
                    if not title_m:
                        continue
                    raw_title = clean_str(title_m.group(1)).replace("· YT.Careers", "").strip()
                    parts = raw_title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    company = parts[1].strip() if len(parts) > 1 else "YouTube Creator"
                    if not is_editing_role(title):
                        continue
                    eligible, reg = is_eligible_for_sa(body[:350], title)
                    if not eligible:
                        continue
                    pay_m = re.search(r"Worldwide remote\s+(.*?)\s+(?:ASAP|Within a month)", body)
                    pay = pay_m.group(1).strip() if pay_m else ""
                    desc = body.split("Apply ->", 1)[1].strip()[:200] if "Apply ->" in body else ""
                    add_job(
                        {
                            "id": f"ytc-{jid}",
                            "title": title,
                            "company": company,
                            "source": "YT.Careers",
                            "url": url,
                            "niche": infer_niche(title, desc),
                            "type": "fulltime" if "Full-time" in body[:250] else ("parttime" if "Part-time" in body[:250] else "freelance"),
                            "region": reg,
                            "pay": pay,
                            "notes": desc,
                        },
                        dt,
                    )
                except Exception:
                    keep_existing(with_url(url))
        except Exception as e:
            print(f"[YT.Careers warn] {e} — keeping existing YT.Careers jobs")
            keep_existing(from_source("YT.Careers"))

    # 4. Dynamite Jobs Direct Verified Listings
    if "Dynamite Jobs" not in disabled:
        try:
            dj_index = fetch_text("https://dynamitejobs.com/skill/remote-video-editing-jobs", timeout=12)
            dj_paths = list(dict.fromkeys(re.findall(r'href=["\'](/company/[^"\']+/remote-job/[^"\']+)["\']', dj_index)))
            if not dj_paths:
                raise ValueError("index page had no job links (blocked or layout changed)")
            prefetch(f"https://dynamitejobs.com{p}" for p in dj_paths[:22])
            for path in dj_paths[:22]:
                url = f"https://dynamitejobs.com{path}"
                try:
                    jhtml = fetch_text(url, timeout=10)
                    t_m = re.search(r"<title>(.*?)</title>", jhtml, re.S)
                    page_title = clean_str(t_m.group(1)) if t_m else ""
                    if not page_title or "Dynamite Jobs: The Best Remote Jobs" in page_title or "Page Not Found" in page_title:
                        continue
                    cleaned = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", " ", jhtml, flags=re.S)
                    text = clean_str(re.sub(r"<[^>]+>", " ", cleaned))
                    header_text = text[:950]
                    if "Closes tomorrow" in header_text or "Job Closed" in header_text:
                        continue
                    upd_m = re.search(r"Updated\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", header_text)
                    open_m = re.search(r"Opened\s+(\d+\s+days?\s+ago|today|yesterday)", header_text, re.I)
                    dt_upd = parse_relative_age_to_dt(upd_m.group(1)) if upd_m else None
                    dt_open = parse_relative_age_to_dt(open_m.group(0)) if open_m else None
                    dt = dt_upd or dt_open
                    if dt_upd and dt_open and dt_upd > dt_open:
                        dt = dt_upd
                    if not dt or not is_within_max_age(dt, MAX_AGE_DAYS):
                        continue
                    title_clean = re.sub(r"^🧨\s*|\s*,\s*Remote Job.*$", "", page_title).strip()
                    if not is_editing_role(title_clean):
                        continue
                    eligible, reg = is_eligible_for_sa(path, title_clean)
                    if not eligible:
                        continue
                    slug_co = path.split("/company/")[1].split("/")[0]
                    company = slug_co.replace("-", " ").title()
                    pay_m = re.search(r"(Full Time|Part Time|Short-Term Project|Contract)\s+(\$[\d.,kK]+\s*(?:-\s*\$[\d.,kK]+)?\s*per\s*(?:year|month|hour))", header_text, re.I)
                    emp = pay_m.group(1) if pay_m else ("Part Time" if "Part Time" in header_text else "Full Time")
                    pay = pay_m.group(2) if pay_m else ""
                    desc_m = re.search(r"Apply Now\s+(.*?)(?:Requirements|Qualifications|Benefits|$)", text)
                    notes = desc_m.group(1).strip()[:200] if desc_m else "Verified remote video editing role on Dynamite Jobs."
                    add_job(
                        {
                            "id": f"dj-{slug_co}-{re.sub(r'[^a-z0-9]+', '-', title_clean.lower()).strip('-')[:18]}",
                            "title": title_clean,
                            "company": company,
                            "source": "Dynamite Jobs",
                            "url": url,
                            "niche": infer_niche(title_clean, notes),
                            "type": "parttime" if "Part" in emp else ("freelance" if "Project" in emp or "Contract" in emp else "fulltime"),
                            "region": reg,
                            "pay": pay,
                            "notes": notes,
                        },
                        dt,
                    )
                except Exception:
                    keep_existing(with_url(url))
        except Exception as e:
            print(f"[Dynamite Jobs warn] {e} — keeping existing Dynamite Jobs jobs")
            keep_existing(from_source("Dynamite Jobs"))

    # 5. Ashby Public Job Board API (with strict deep jobUrl + publishedAt <= 14 days)
    if "Ashby" not in disabled:
        for slug, company_name in ASHBY_BOARDS:
            try:
                raw = fetch_text(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=10)
                board = json.loads(raw)
                if not isinstance(board.get("jobs"), list):
                    raise ValueError("response had no jobs list")
                for job in board["jobs"]:
                    if job.get("isListed") is False:
                        continue
                    title = (job.get("title") or "").strip()
                    if not is_editing_role(title):
                        continue
                    job_url = (job.get("jobUrl") or "").strip()
                    if not job_url or job_url.rstrip("/").count("/") < 4:
                        continue
                    dt = parse_iso_or_date(job.get("publishedAt"))
                    if not dt or not is_within_max_age(dt, MAX_AGE_DAYS):
                        continue
                    loc = (job.get("location") or "Remote").strip()
                    eligible, reg = is_eligible_for_sa(loc, title)
                    if not eligible:
                        continue
                    comp = job.get("compensationTierSummary") or ""
                    emp_type = (job.get("employmentType") or "").lower()
                    jtype = "fulltime" if "full" in emp_type else ("parttime" if "part" in emp_type else "freelance")
                    uuid_short = job_url.rstrip("/").split("/")[-1][:8]
                    add_job(
                        {
                            "id": f"ashby-{slug}-{uuid_short}",
                            "title": title,
                            "company": company_name,
                            "source": "Ashby",
                            "url": job_url,
                            "niche": infer_niche(title),
                            "type": jtype,
                            "region": reg,
                            "regionNote": loc if reg != "world" else "",
                            "pay": comp,
                            "notes": f"Verified active opening on {company_name}'s Ashby ATS ({loc}).",
                        },
                        dt,
                    )
            except Exception as e:
                print(f"[Ashby warn] {slug}: {e} — keeping existing jobs from this board")
                keep_existing(with_id_prefix(f"ashby-{slug}-"))

    # 6. Workable Widget API (with strict /j/<shortcode> deep link + published_on <= 14 days)
    if "Workable" not in disabled:
        for slug, company_name in WORKABLE_BOARDS:
            try:
                raw = fetch_text(f"https://apply.workable.com/api/v1/widget/accounts/{slug}", timeout=10)
                wdata = json.loads(raw)
                if not isinstance(wdata.get("jobs"), list):
                    raise ValueError("response had no jobs list")
                for job in wdata["jobs"]:
                    title = (job.get("title") or "").strip()
                    if not is_editing_role(title):
                        continue
                    shortcode = (job.get("shortcode") or "").strip()
                    job_url = (job.get("url") or "").strip()
                    if not shortcode or not job_url or "/j/" not in job_url:
                        continue
                    dt = parse_iso_or_date(job.get("published_on") or job.get("created_at"))
                    if not dt or not is_within_max_age(dt, MAX_AGE_DAYS):
                        continue
                    loc_parts = [job.get("country") or "", job.get("city") or ""]
                    loc = ", ".join([p for p in loc_parts if p]).strip() or "Remote"
                    eligible, reg = is_eligible_for_sa(loc, title)
                    if not eligible:
                        continue
                    add_job(
                        {
                            "id": f"wk-{slug}-{shortcode.lower()}",
                            "title": title,
                            "company": company_name,
                            "source": "Workable",
                            "url": job_url,
                            "niche": infer_niche(title),
                            "type": "parttime" if "part-time" in title.lower() or "part time" in title.lower() else "fulltime",
                            "region": reg,
                            "regionNote": loc if reg != "world" else "",
                            "pay": "",
                            "notes": f"Verified active opening on {company_name}'s Workable ATS ({loc}).",
                        },
                        dt,
                    )
            except Exception as e:
                print(f"[Workable warn] {slug}: {e} — keeping existing jobs from this board")
                keep_existing(with_id_prefix(f"wk-{slug}-"))

    # 7. Podnews RSS (with strict pubDate <= 14 days & deep link verification)
    if "Podnews" not in disabled:
        try:
            rss = fetch_text("https://podnews.net/prebuilt/rss-jobs.xml", timeout=12)
            items = re.findall(r"<item>(.*?)</item>", rss, re.S)
            if not items:
                raise ValueError("feed returned no items (blocked or empty feed)")
            for item in items:
                t_m = re.search(r"<title>(.*?)</title>", item)
                l_m = re.search(r"<link>(https://podnews\.net/job/[^<]+)</link>", item)
                d_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
                desc_m = re.search(r"<description>(.*?)</description>", item, re.S)
                if not (t_m and l_m and d_m):
                    continue
                raw_title = clean_str(t_m.group(1))
                if not is_editing_role(raw_title) and "podcast producer" not in raw_title.lower():
                    continue
                dt = parse_iso_or_date(d_m.group(1))
                if not dt or not is_within_max_age(dt, MAX_AGE_DAYS):
                    continue
                url = l_m.group(1).strip()
                try:
                    phtml = fetch_text(url, timeout=10)
                except Exception:
                    keep_existing(with_url(url))
                    continue
                ptext = clean_str(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", phtml, flags=re.S)))
                if "remote" not in ptext.lower():
                    continue
                desc_raw = clean_str(re.sub(r"<[^>]+>", " ", desc_m.group(1))) if desc_m else ""
                co_slug = url.split("/job/")[1].split("/")[0].replace("-", " ").title()
                add_job(
                    {
                        "id": f"pod-{re.sub(r'[^a-z0-9]+', '-', url.split('/job/')[1].lower()).strip('-')[:36]}",
                        "title": raw_title,
                        "company": co_slug,
                        "source": "Podnews",
                        "url": url,
                        "niche": ["podcast", "youtube"],
                        "type": "parttime" if "part time" in ptext.lower() or "part-time" in ptext.lower() else "fulltime",
                        "region": "world",
                        "pay": "",
                        "notes": desc_raw[:190] or f"Remote podcast role at {co_slug}.",
                    },
                    dt,
                )
        except Exception as e:
            print(f"[Podnews warn] {e} — keeping existing Podnews jobs")
            keep_existing(from_source("Podnews"))

    # 8. Remote Rocketship (Worldwide Video Editor board with HTTP 200 + age verification)
    if "Remote Rocketship" not in disabled:
        try:
            rr_html = fetch_text("https://www.remoterocketship.com/country/worldwide/jobs/video-editor/", timeout=12)
            rr_paths = list(dict.fromkeys(re.findall(r'href=["\'](/us/company/[^"\']+/jobs/[^"\']+)["\']', rr_html)))
            if not rr_paths:
                raise ValueError("index page had no job links (blocked or layout changed)")
            prefetch(f"https://www.remoterocketship.com{p}" for p in rr_paths[:10])
            for path in rr_paths[:10]:
                url = f"https://www.remoterocketship.com{path}"
                try:
                    jhtml = fetch_text(url, timeout=10)
                    if "Page not found" in jhtml or "<title>404" in jhtml:
                        continue
                    cleaned = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", " ", jhtml, flags=re.S)
                    text = clean_str(re.sub(r"<[^>]+>", " ", cleaned))
                    age_m = re.search(r"(?:🕒|🔥)\s*([A-Za-z]+\s+\d{1,2}(?:,\s*\d{4})?|\d+\s+(?:hours?|days?|minutes?)\s+ago|today|yesterday)", text, re.I)
                    if not age_m:
                        continue
                    dt = parse_relative_age_to_dt(age_m.group(1))
                    if not dt or not is_within_max_age(dt, MAX_AGE_DAYS):
                        continue
                    t_m = re.search(r"<title[^>]*>(.*?)</title>", jhtml, re.S)
                    if not t_m:
                        continue
                    raw_t = clean_str(t_m.group(1))
                    m_tc = re.match(r"^(.*?)\s+at\s+(.*?)\s+-\s+", raw_t)
                    if not m_tc:
                        continue
                    title, company = m_tc.group(1).strip(), m_tc.group(2).strip()
                    if not is_editing_role(title):
                        continue
                    slug_id = path.strip("/").split("/")[-1][:24]
                    desc_m = re.search(r"📋 Description\s*(.*?)(?:🎯 Requirements|$)", text)
                    notes = desc_m.group(1).strip()[:190] if desc_m else f"Worldwide remote opening at {company}."
                    if "French Required" in text:
                        notes = "Requires French. " + notes
                    add_job(
                        {
                            "id": f"rr-{slug_id}",
                            "title": title,
                            "company": company,
                            "source": "Remote Rocketship",
                            "url": url,
                            "niche": infer_niche(title, notes),
                            "type": "freelance" if "Contract" in text[:1200] or "Freelance" in title else "fulltime",
                            "region": "world",
                            "pay": "",
                            "notes": notes,
                        },
                        dt,
                    )
                except Exception:
                    keep_existing(with_url(url))
        except Exception as e:
            print(f"[Remote Rocketship warn] {e} — keeping existing Remote Rocketship jobs")
            keep_existing(from_source("Remote Rocketship"))

    # 9. Somewhere / Hirezar (South Africa & global remote placement board with JSON-LD datePosted)
    if "Somewhere / Hirezar" not in disabled:
        try:
            hz_html = fetch_text("https://hirezar.co.za/jobs/?q=video+editor", timeout=12)
            hz_paths = [p for p in dict.fromkeys(re.findall(r'href=["\'](/jobs/[^"\'?]+)["\']', hz_html)) if p not in ("/jobs/", "/jobs")]
            if not hz_paths:
                raise ValueError("search page had no job links (blocked or layout changed)")
            prefetch(f"https://hirezar.co.za{p}" for p in hz_paths[:10])
            for path in hz_paths[:10]:
                url = f"https://hirezar.co.za{path}"
                try:
                    jhtml = fetch_text(url, timeout=10)
                    ld_blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', jhtml, re.S)
                    if not ld_blocks:
                        continue
                    ld_obj = json.loads(ld_blocks[0])
                    dt = parse_iso_or_date(ld_obj.get("datePosted"))
                    if not dt or not is_within_max_age(dt, MAX_AGE_DAYS):
                        continue
                    title = clean_str(ld_obj.get("title") or "")
                    if not is_editing_role(title):
                        continue
                    company = clean_str((ld_obj.get("hiringOrganization") or {}).get("name") or "Somewhere")
                    desc_raw = clean_str(re.sub(r"<[^>]+>", " ", ld_obj.get("description") or ""))
                    pay_m = re.search(
                        r"(\$\s*\d[\d,]*(?:\s*[-–to]+\s*\$?\s*\d[\d,]*)?\s*(?:USD)?\s*(?:/\s*month|per\s*month|/mo|/hr|per\s*hour|/video|per\s*video|k|K)?|\b\d[\d,]*(?:\s*[-–to]+\s*\d[\d,]*)?\s*USD\s*(?:/\s*month|per\s*month|/mo|/hr|per\s*hour)?|R\s*\d[\d,]*(?:\s*[-–to]+\s*R?\s*\d[\d,]*)?\s*(?:/\s*month|per\s*month|/mo|/hr|per\s*hour|pm)?)",
                        desc_raw,
                        re.I,
                    )
                    pay = pay_m.group(1).strip() if pay_m else ""
                    slug_id = path.strip("/").split("-")[-1][:12]
                    add_job(
                        {
                            "id": f"hz-{slug_id}",
                            "title": title,
                            "company": company,
                            "source": "Somewhere / Hirezar",
                            "url": url,
                            "niche": infer_niche(title, desc_raw),
                            "type": "parttime" if "P/T" in title or "part-time" in desc_raw.lower() else "fulltime",
                            "region": "world",
                            "pay": pay,
                            "notes": desc_raw[:195] or f"South Africa & global remote video editor opening via {company}.",
                        },
                        dt,
                        dedup_key=f"{title.lower()}::{company.lower()}::{slug_id}",
                    )
                except Exception:
                    keep_existing(with_url(url))
        except Exception as e:
            print(f"[Somewhere / Hirezar warn] {e} — keeping existing Somewhere / Hirezar jobs")
            keep_existing(from_source("Somewhere / Hirezar"))

    # Sort all verified jobs newest-first by actual publish timestamp
    collected.sort(key=lambda item: item[0], reverse=True)
    final_jobs = []
    for idx, (_, j) in enumerate(collected, 1):
        j["order"] = idx
        final_jobs.append(j)

    today_str = datetime.date.today().strftime("%d %b %Y").lstrip("0")
    data = {
        "sweepDate": today_str,
        "jobs": final_jobs,
    }

    # Diff against the previous sweep so alerts only fire for jobs that weren't on the board before
    prev_ids = {ej.get("id") for ej in existing_jobs}
    new_ids = {j.get("id") for j in final_jobs}
    added = [j for j in final_jobs if j.get("id") not in prev_ids]
    removed = [ej for ej in existing_jobs if ej.get("id") not in new_ids]

    sync_static_bundles(data)
    return {"data": data, "added": added, "removed": removed}


if __name__ == "__main__":
    result = scrape_all_sources()
    print(
        f"Verified sweep complete: {len(result['data']['jobs'])} live, deep-linked listings (all <= {MAX_AGE_DAYS} days old). "
        f"{len(result['added'])} new, {len(result['removed'])} removed."
    )
