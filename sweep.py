import datetime
import json
import os
import re
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_PATH = os.path.join(BASE_DIR, "jobs.json")
JS_PATH = os.path.join(BASE_DIR, "jobs.js")
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
STANDALONE_PATH = os.path.join(BASE_DIR, "cutting-room-gigs-standalone.html")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
}

ASHBY_BOARDS = [
    ("aidigest", "AI Digest"),
    ("newform", "Newform"),
    ("dreamthree", "Dream Three"),
    ("revstone", "RevStone"),
    ("acquisition", "Acquisition.com"),
    ("hirehangar", "Hangar"),
    ("superpower", "Superpower"),
    ("whop", "Whop"),
    ("beehiiv", "beehiiv"),
    ("stan", "Stan"),
    ("riverside", "Riverside.fm"),
    ("descript", "Descript"),
    ("patreon", "Patreon"),
    ("kajabi", "Kajabi"),
]

WORKABLE_BOARDS = [
    ("reworkssolutions", "Reworks Solutions"),
    ("hirehawk", "HireHawk"),
]


def fetch_text(url, timeout=10):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def infer_niche(title, extra=""):
    text = f"{title} {extra}".lower()
    niches = []
    if any(k in text for k in ["short", "tiktok", "reel", "ugc", "social", "clipper", "ad creative"]):
        niches.append("social")
    if any(k in text for k in ["podcast", "vodcast", "audio"]):
        niches.append("podcast")
    if any(k in text for k in ["youtube", "longform", "long-form", "creator", "retention", "documentary"]):
        niches.append("youtube")
    if any(k in text for k in ["promo", "trailer", "commercial", "brand", "agency", "course"]):
        niches.append("promo")
    if not niches:
        niches.append("youtube")
    return niches[:2]


def is_editing_role(title):
    t = (title or "").lower()
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
            "reel editor",
            "tiktok editor",
            "clipper",
            "post-production",
        ]
    )


def sync_static_bundles(data):
    """Sync jobs.json -> jobs.js and cutting-room-gigs-standalone.html (cross-platform)."""
    with open(JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    minified = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    with open(JS_PATH, "w", encoding="utf-8") as f:
        f.write(f"window.CRG_DATA = {minified};\n")

    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, encoding="utf-8") as f:
            html = f.read()
        inline_script = f"<script>window.CRG_DATA = {minified};</script>"
        standalone_html = html.replace('<script src="jobs.js"></script>', inline_script)
        with open(STANDALONE_PATH, "w", encoding="utf-8") as f:
            f.write(standalone_html)


def scrape_all_sources(disabled_sources=None):
    disabled = set(disabled_sources or [])
    with open(JOBS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    existing_jobs = data.get("jobs", [])
    existing_urls = {j["url"].rstrip("/").lower() for j in existing_jobs if j.get("url")}
    existing_ids = {j["id"] for j in existing_jobs if j.get("id")}
    added_jobs = []

    # 1. YT.Careers
    if "YT.Careers" not in disabled:
        try:
            html = fetch_text("https://yt.careers/youtube-jobs")
            ids = []
            for m in re.findall(r"/youtube-jobs/(\d+)", html):
                if m not in ids:
                    ids.append(m)
            for jid in ids[:10]:
                url = f"https://yt.careers/youtube-jobs/{jid}"
                if url.rstrip("/").lower() in existing_urls or f"ytc-{jid}" in existing_ids:
                    continue
                try:
                    jhtml = fetch_text(url)
                    title_m = re.search(r"<title>(.*?)</title>", jhtml, re.S)
                    if not title_m:
                        continue
                    raw_title = re.sub(r"\s+", " ", title_m.group(1)).strip()
                    raw_title = raw_title.replace("· YT.Careers", "").strip()
                    if not is_editing_role(raw_title):
                        continue
                    parts = raw_title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    company = parts[1].strip() if len(parts) > 1 else "YouTube Creator"
                    new_job = {
                        "id": f"ytc-{jid}",
                        "title": title,
                        "company": company,
                        "source": "YT.Careers",
                        "url": url,
                        "niche": infer_niche(title, jhtml[:1500]),
                        "type": "parttime" if "Part-time" in jhtml else "freelance",
                        "region": "world" if "Worldwide" in jhtml else "unknown",
                        "pay": "",
                        "posted": "Posted recently",
                        "order": 1,
                        "notes": "Discovered via automated YT.Careers sweep.",
                    }
                    added_jobs.append(new_job)
                    existing_urls.add(url.rstrip("/").lower())
                    existing_ids.add(new_job["id"])
                except Exception:
                    pass
        except Exception:
            pass

    # 2. Ashby Public Job Board API
    if "Ashby" not in disabled:
        for slug, company_name in ASHBY_BOARDS:
            try:
                raw = fetch_text(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
                board = json.loads(raw)
                for job in board.get("jobs", []):
                    title = (job.get("title") or "").strip()
                    if not is_editing_role(title):
                        continue
                    board_url = f"https://jobs.ashbyhq.com/{slug}"
                    job_url = (job.get("jobUrl") or board_url).strip()
                    jid = f"ashby-{slug}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:24]}"
                    if job_url.rstrip("/").lower() in existing_urls or jid in existing_ids:
                        continue
                    comp = job.get("compensationTierSummary") or ""
                    loc = (job.get("location") or "Remote").strip()
                    emp_type = (job.get("employmentType") or "").lower()
                    jtype = "fulltime" if "full" in emp_type else ("parttime" if "part" in emp_type else "contract")
                    added_jobs.append(
                        {
                            "id": jid,
                            "title": title,
                            "company": company_name,
                            "source": "Ashby",
                            "url": job_url,
                            "niche": infer_niche(title),
                            "type": jtype,
                            "region": "world" if any(w in loc.lower() for w in ["remote", "world", "anywhere", "global"]) else "restricted",
                            "regionNote": loc,
                            "pay": comp,
                            "posted": "Active now (Ashby)",
                            "order": 1,
                            "notes": f"Live role on {company_name}'s Ashby board ({loc}).",
                        }
                    )
                    existing_urls.add(job_url.rstrip("/").lower())
                    existing_ids.add(jid)
            except Exception:
                pass

    # 3. Workable Widget API
    if "Workable" not in disabled:
        for slug, company_name in WORKABLE_BOARDS:
            try:
                raw = fetch_text(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
                wdata = json.loads(raw)
                for job in wdata.get("jobs", []):
                    title = (job.get("title") or "").strip()
                    if not is_editing_role(title):
                        continue
                    shortcode = job.get("shortcode") or ""
                    job_url = job.get("url") or f"https://apply.workable.com/{slug}/"
                    jid = f"workable-{slug}-{shortcode or re.sub(r'[^a-z0-9]+', '-', title.lower())[:20]}"
                    if job_url.rstrip("/").lower() in existing_urls or jid in existing_ids:
                        continue
                    added_jobs.append(
                        {
                            "id": jid,
                            "title": title,
                            "company": company_name,
                            "source": "Workable",
                            "url": job_url,
                            "niche": infer_niche(title),
                            "type": "fulltime",
                            "region": "world",
                            "pay": "",
                            "posted": "Active now (Workable)",
                            "order": 1,
                            "notes": f"Live remote video editing opening on {company_name}'s Workable portal.",
                        }
                    )
                    existing_urls.add(job_url.rstrip("/").lower())
                    existing_ids.add(jid)
            except Exception:
                pass

    # 4. Remotive Public API
    if "Remotive" not in disabled:
        try:
            raw = fetch_text("https://remotive.com/api/remote-jobs?search=video%20editor&limit=15")
            rdata = json.loads(raw)
            for job in rdata.get("jobs", []):
                title = (job.get("title") or "").strip()
                if not is_editing_role(title):
                    continue
                url = (job.get("url") or "").strip()
                jid = f"remotive-{job.get('id')}"
                if not url or url.rstrip("/").lower() in existing_urls or jid in existing_ids:
                    continue
                loc = (job.get("candidate_required_location") or "Worldwide").strip()
                is_world = "worldwide" in loc.lower() or "anywhere" in loc.lower()
                added_jobs.append(
                    {
                        "id": jid,
                        "title": title,
                        "company": (job.get("company_name") or "Remote Employer").strip(),
                        "source": "Remotive",
                        "url": url,
                        "niche": infer_niche(title, job.get("category") or ""),
                        "type": "contract" if "contract" in (job.get("job_type") or "").lower() else "fulltime",
                        "region": "world" if is_world else "restricted",
                        "regionNote": loc,
                        "pay": (job.get("salary") or "").strip(),
                        "posted": "Posted recently",
                        "order": 1,
                        "notes": f"Listed via Remotive public API ({loc}).",
                    }
                )
                existing_urls.add(url.rstrip("/").lower())
                existing_ids.add(jid)
        except Exception:
            pass

    # 5. Reddit JSON Feeds (r/CreatorServices & r/forhire)
    if "Reddit" not in disabled:
        reddit_feeds = [
            ("https://www.reddit.com/r/CreatorServices/new.json?limit=15", "r/CreatorServices"),
            ("https://www.reddit.com/r/forhire/search.json?q=flair%3Ahiring+video+editor&restrict_sr=1&sort=new&limit=10", "r/forhire"),
        ]
        for feed_url, sub_label in reddit_feeds:
            try:
                raw_json = fetch_text(feed_url)
                feed = json.loads(raw_json)
                children = feed.get("data", {}).get("children", [])
                for item in children:
                    post = item.get("data", {})
                    ptitle = (post.get("title") or "").strip()
                    flair = (post.get("link_flair_text") or "").lower()
                    if "[hiring]" not in ptitle.lower() and "hiring" not in flair:
                        continue
                    if "editor" not in ptitle.lower() and "editing" not in ptitle.lower() and "clipper" not in ptitle.lower():
                        continue
                    permalink = post.get("permalink") or ""
                    if not permalink:
                        continue
                    url = f"https://www.reddit.com{permalink}".rstrip("/")
                    pid = post.get("id") or ""
                    jid = f"reddit-{pid}"
                    if url.lower() in existing_urls or jid in existing_ids:
                        continue
                    author = post.get("author") or "Creator"
                    added_jobs.append(
                        {
                            "id": jid,
                            "title": ptitle,
                            "company": f"{sub_label} (u/{author})",
                            "source": "Reddit",
                            "url": url + "/",
                            "niche": infer_niche(ptitle),
                            "type": "freelance",
                            "region": "world",
                            "pay": "",
                            "posted": "Posted recently",
                            "order": 1,
                            "notes": f"Direct creator hiring post on {sub_label}.",
                        }
                    )
                    existing_urls.add(url.lower())
                    existing_ids.add(jid)
            except Exception:
                pass

    all_jobs = added_jobs + existing_jobs
    for idx, j in enumerate(all_jobs, 1):
        j["order"] = idx

    today_str = datetime.date.today().strftime("%d %b %Y").lstrip("0")
    data["sweepDate"] = today_str
    data["jobs"] = all_jobs

    sync_static_bundles(data)
    return {"data": data, "added": added_jobs, "removed": []}


if __name__ == "__main__":
    result = scrape_all_sources()
    print(
        f"Sweep complete: +{len(result['added'])} new listings ({len(result['data']['jobs'])} total)."
    )
