# Cutting Room Gigs: move-over guide

A private board of open, public, remote video editor jobs. It covers social and paid ads, YouTube long-form, and podcasts. This guide explains how to rebuild it in your own Claude account, or run it without Claude at all.

Last sweep in this package: **18 Oct 2026** (50 listings across 12 public sources).

---

## 1. What's in the package

| File | What it is | When to use it |
|---|---|---|
| `index.html` | The main board UI (Open Bin, Applied Tracker, Sources & Alerts). | Opening locally or via `start-board.bat`. |
| `jobs.json` | All 50 listings as plain data, plus the sweep date. | Seeding the database or backing up listings. |
| `jobs.js` | Browser-ready script wrapper (`window.CRG_DATA`) for `file://` mode. | Automatically loaded by `index.html`. |
| `cutting-room-gigs-standalone.html` | Single-file version with all 50 listings embedded inline. | Quick single-file use or static hosting. |
| `server.py` / `start-board.bat` | Local server supporting live sweeps, source toggles, and desktop/email alerts. | Running locally at `http://localhost:8080`. |
| `README.md` | This guide. | — |

### Tracked Job Sources (with On / Off Controls)
You can turn any individual job source **ON** or **OFF** from either:
- The **Sources** chip row directly inside the **Open Bin** filter bar
- The **Sources & Alerts** tab (`Active Job Sources (Turn On / Off)` panel, including a one-click **Toggle Reddit** button)
- The **Mute [Source]** button on any individual job card

Currently tracked sources (50 listings total):
1. **Ashby** (`jobs.ashbyhq.com`) — Direct agency & creator startup ATS boards (Acquisition.com, AI Digest, Hire Hangar, Newform, Superpower)
2. **Workable** (`apply.workable.com`) — Direct DTC brand & agency ATS boards (HireHawk, ReWorks Solutions, Creative Chaos)
3. **Somewhere / Hirezar** (`somewhere.com` / `hirezar.co.za`) — South Africa & global remote placement agencies with USD/ZAR pay
4. **Himalayas** (`himalayas.app`) — Global remote job board (Seen.tv, Paired)
5. **Dynamite Jobs** (`dynamitejobs.com`) — 100% remote-first companies with transparent pay
6. **YT Jobs** (`ytjobs.co`) — YouTube creator & channel editing marketplace
7. **Twine** (`twine.net`) — Freelance creative marketplace for YouTube, documentary & CapCut gigs
8. **Reddit** (`r/CreatorServices`, `r/forhire`) — Direct creator hiring posts (can be toggled off with 1 click)
9. **YT.Careers** (`yt.careers`) — Curated YouTube channel & media studio job board
10. **Remote Rocketship** (`remoterocketship.com`) — Worldwide remote video editor aggregator
11. **RemoteSource** (`remotesource.com`) — Remote creative & agency matching platform
12. **Podnews** (`podnews.net/jobs`) — Podcast industry job board for video podcast editors

---

## 2. Option A: Rebuild it as an artifact in your own Claude account (recommended)

This gives you the same setup as now: a private page, marks that sync across devices, and Claude adding new listings on request.

1. Sign in to your personal Claude account and start a new chat.
2. Attach `index.html` and `jobs.json`.
3. Paste this prompt:

```
I've attached index.html and jobs.json for a personal job board called "Cutting Room Gigs".
Please:
1. Publish index.html as a private artifact with the `db` capability. Keep the page as it is.
2. Seed its database from jobs.json:
   - each item in "jobs" becomes a document in the "jobs" collection, using its "id" as the doc id
     (store every other field as-is)
   - write { "date": <sweepDate> } to the document meta/sweep
3. Leave the "status" collection empty. The page writes my Saved/Applied/Hidden marks there.
Then tell me when it's live.
```

4. Open the page and check that 50 listings appear, and that the "Last sweep" date reads 18 Oct 2026.
5. Optional: pin it to your sidebar. You can ask Claude to do that.

### Asking for a fresh sweep in the new account

Your new account won't know how this board works, so the first time, paste the full brief below. After that, a reminder in the same chat is enough.

```
Run a fresh sweep for my Cutting Room Gigs artifact.
Find open, public job listings for a freelance/remote video editor:
- Location: remote, open to someone based in South Africa (worldwide). Skip US-only or other
  country-locked roles; if eligibility isn't stated, include it and mark region "unknown".
- Niches: social & paid ads (UGC, Meta/TikTok, DTC), YouTube long-form, podcasts.
- Types: freelance/per project, part-time, or full-time contractor.
- Good sources: Ashby (jobs.ashbyhq.com), Workable (apply.workable.com), Somewhere/Hirezar,
  Himalayas, YT Jobs (ytjobs.co), YT.Careers, Remote Rocketship, Dynamite Jobs, Podnews,
  Twine, and Reddit (r/CreatorServices) if enabled.
- Open each listing to confirm details. Never invent pay, dates or eligibility.
Then:
- Add new listings to the "jobs" collection (fields below). Don't touch the "status" collection.
- Delete listings that are closed or past their deadline.
- Update meta/sweep with today's date.
Tell me what was added and removed.
```

---

## 3. Option B: Use it without Claude

Open `cutting-room-gigs-standalone.html` in any browser. That's it.

- Filters and Saved / Applied / Hidden all work. Marks are stored in that browser on that device.
- To host it at a URL, drag the file onto [Netlify Drop](https://app.netlify.com/drop), or upload it to a GitHub Pages repo as `index.html`. Anyone with that link can see it, so keep the link to yourself.
- To add listings, open the file in a text editor and find the line starting `const DATA=` near the bottom. Each listing is one `{ … }` object in the `jobs` array, using the fields in section 4. You can ask any Claude chat to run the sweep brief above and "return the new listings as JSON objects in this format", then paste them in.

---

## 4. Listing format

Each listing in `jobs.json` (and in the database) looks like this:

```json
{
  "id": "ytc-303",
  "title": "Short-Form Video Editor for Podcasts & Social Media",
  "company": "Ray Sinlao",
  "source": "YT.Careers",
  "url": "https://yt.careers/youtube-jobs/303",
  "niche": ["podcast", "social"],
  "type": "parttime",
  "region": "world",
  "regionNote": "",
  "pay": "$25–$65 per video or $1,500/month",
  "posted": "Posted ~1 day ago",
  "order": 1,
  "notes": "Clipping podcast episodes into short-form social content."
}
```

| Field | Required | Allowed values / notes |
|---|---|---|
| `id` | yes | Short unique slug, letters/digits/dashes. It's also the database doc id. |
| `title`, `company`, `source`, `url` | yes | `url` links to the original post. |
| `niche` | yes | Array of any of `social`, `youtube`, `podcast`. The first one sets the card's colour strip. |
| `type` | yes | `freelance`, `parttime` or `fulltime` (full-time contractor). |
| `region` | yes | `world` (worldwide), `limited` (region or time-zone limits), `unknown` (not stated). "Worldwide only" shows just `world`. |
| `regionNote` | no | Shown under the listing when region isn't `world`. |
| `pay` | no | Leave empty and the page shows "Pay not listed". |
| `posted` | yes | Free text, e.g. "Posted 13 Oct" or "Posted ~5 days ago". |
| `order` | yes | Sort position, lowest first. Use it to keep newest at the top. |
| `notes` | no | One or two lines of detail. |

The database also uses:
- `status/<job id>` → `{ "s": "saved" | "applied" | "hidden" }`, written by the page when you click a mark.
- `meta/sweep` → `{ "date": "18 Oct 2026" }`, shown as "Last sweep" in the header.

Marks are stored apart from listings on purpose. A new sweep can overwrite or delete listings without wiping your marks.

---

## 5. How the page works

- **Look:** an editor's bin. The header has a timeline ruler with a playhead. Each listing is a "clip" with a colour strip: blue for social/ads, red for YouTube, purple for podcast. It adapts to light and dark mode and works on a phone.
- **Filters:** niche, type, worldwide only, saved, include hidden, and text search. Your filter choices are remembered in your browser.
- **Fonts:** Bricolage Grotesque, Figtree and JetBrains Mono, loaded from Google Fonts. It falls back to system fonts when offline.
- **No outside calls:** apart from the fonts, the page loads nothing external. The board links at the bottom simply open those job sites in a new tab.

---

## 6. Limits to know

- **It doesn't search the web itself.** A Claude artifact can't fetch other sites, and neither can a plain HTML file without a backend, because job boards block cross-site requests. New listings come from asking Claude for a sweep, or from the "Search the boards yourself" links.
- **Check the original post before you apply.** Listings were open when collected on 18 Oct 2026. A few of the YT.Careers posts were already around two months old.
- **Notes on specific listings from this sweep:**
  - Afford Anything closes 23 Oct 2026.
  - CHASR requires French.
  - OnHires is Europe-based and needs CET overlap.
  - Right Side Up, Afford Anything and BlueTuskr don't state where applicants can be based.
- **Clean up afterwards.** Once the new version works, you can delete the old artifact from the original account, or ask Claude there to delete it.
