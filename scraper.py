import glob
import json
import os
import re
import time
import pandas as pd
import requests
from jobspy import scrape_jobs

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

# Broad queries to capture Finance, Audit, AP/AR & Analyst openings across your 550 GCC & MNCs
SEARCH_QUERIES = [
    "Finance",
    "Audit",
    "Accounts Payable",
    "Accounts Receivable",
    "Financial Analyst",
    "Accounting",
    "Equity Research",
]
LOCATION = "Hyderabad, Telangana, India"
JOBS_FILE = "jobs.json"
COMPANIES_FILE = "companies.json"
START_DATE_CUTOFF = "2026-11-01"

# Automatically uses 624 hours (Nov 1 - Nov 26) if jobs.json is empty, then 48 hours for daily runs
if os.path.exists(JOBS_FILE):
    with open(JOBS_FILE, "r", encoding="utf-8") as f:
        existing_jobs = json.load(f)
else:
    existing_jobs = []

IS_BACKFILL = len(existing_jobs) == 0
HOURS_OLD = 624 if IS_BACKFILL else 48
RESULTS_WANTED = 40 if IS_BACKFILL else 25

def clean_company(name):
    name = str(name).lower()
    name = re.sub(r"\([^)]*\)", " ", name)
    name = re.sub(
        r"\b(pvt|ltd|private|limited|india|inc|llc|llp|corp|services|solutions|technologies|technology|group|global|gds|usi|acceleration|centers|centre|center|hospital|hospitals|pharmaceuticals|pharma)\b",
        " ",
        name,
    )
    return re.sub(r"[^a-z0-9]", "", name)

# 1. Load 550 GCC & MNC companies from companies.xlsx and export companies.json
gcc_mnc_map = {}
xlsx_files = glob.glob("*.xlsx") + glob.glob("*.XLSX")

for xlsx_path in xlsx_files:
    excel_sheets = pd.read_excel(xlsx_path, sheet_name=None, header=None)
    for _, sheet_df in excel_sheets.items():
        for _, row in sheet_df.iterrows():
            vals = [str(v).strip() for v in row.tolist() if pd.notna(v)]
            if len(vals) < 2:
                continue
            cat = vals.pop(0).upper()
            comp = vals.pop(0)
            sector = vals.pop(0) if vals else ""
            desc = vals.pop(0) if vals else ""

            if cat in ("GCC", "MNC") and comp:
                aliases = [re.sub(r"\([^)]*\)", "", comp).strip()]
                aliases.extend(re.findall(r"\(([^)]*)\)", comp))
                for alias in aliases:
                    key = clean_company(alias)
                    if len(key) >= 3:
                        gcc_mnc_map[key] = {
                            "category": cat,
                            "sector": sector,
                            "name": comp,
                            "description": desc,
                        }

unique_companies = []
seen_comp_names = set()
for info in gcc_mnc_map.values():
    if info["name"] not in seen_comp_names:
        seen_comp_names.add(info["name"])
        unique_companies.append({
            "name": info["name"],
            "category": info["category"],
            "sector": info["sector"],
            "description": info["description"],
        })
unique_companies.sort(key=lambda x: x["name"].lower())
with open(COMPANIES_FILE, "w", encoding="utf-8") as cf:
    json.dump(unique_companies, cf, indent=2, ensure_ascii=False)
print(f"Exported {len(unique_companies)} GCC & MNC companies to {COMPANIES_FILE}.")

def match_gcc_mnc(scraped_company):
    cleaned = clean_company(scraped_company)
    if len(cleaned) < 3:
        return None
    if cleaned in gcc_mnc_map:
        return gcc_mnc_map[cleaned]
    for key, info in gcc_mnc_map.items():
        if len(key) >= 4 and (key in cleaned or cleaned in key):
            return info
    return None

def send_telegram(msg):
    s = chr(47)
    url = f"https:{s}{s}api.telegram.org{s}bot{BOT_TOKEN}{s}sendMessage"
    requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )

# 2. Scrape LinkedIn & Naukri and keep all matches from Nov 1, 2026 onward
seen_urls = {job["job_url"] for job in existing_jobs}
new_jobs = []

print(f"Mode: {'BACKFILL (Nov 1 - Today)' if IS_BACKFILL else 'DAILY UPDATE'} | hours_old={HOURS_OLD}")

for term in SEARCH_QUERIES:
    print(f"Scraping LinkedIn & Naukri for: {term}...")
    try:
        df = scrape_jobs(
            site_name=["linkedin", "naukri"],
            search_term=term,
            location=LOCATION,
            results_wanted=RESULTS_WANTED,
            hours_old=HOURS_OLD,
        )
    except Exception as e:
        print(f"Error scraping {term}: {e}")
        time.sleep(8)
        continue

    if not df.empty:
        for _, row in df.iterrows():
            job_url = str(row.get("job_url", "")).strip()
            if not job_url or job_url == "None" or job_url in seen_urls:
                continue

            company = str(row.get("company", "N/A")).strip()
            match = match_gcc_mnc(company)
            if not match:
                continue

            date_posted = str(row.get("date_posted", "")).strip()
            if date_posted and date_posted != "None" and date_posted < START_DATE_CUTOFF:
                continue

            seen_urls.add(job_url)
            job_entry = {
                "id": job_url,
                "title": str(row.get("title", "N/A")),
                "company": match["name"],
                "raw_company": company,
                "category": match["category"],
                "sector": match["sector"],
                "location": str(row.get("location", "Hyderabad")),
                "site": str(row.get("site", "N/A")).capitalize(),
                "job_url": job_url,
                "date_posted": date_posted if date_posted != "None" else time.strftime("%Y-%m-%d"),
                "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            new_jobs.append(job_entry)

    time.sleep(8)

if new_jobs:
    new_jobs.sort(key=lambda x: x.get("date_posted", ""), reverse=True)
    # Keep up to 2,000 jobs so your entire November + ongoing history stays intact
    updated_jobs = (new_jobs + existing_jobs)[:2000]
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_jobs, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(new_jobs)} new GCC/MNC jobs. Total stored: {len(updated_jobs)}.")

    if len(new_jobs) <= 10:
        for j in new_jobs:
            msg = (
                f"🆕 <b>[{j['category']}] New {j['site']} Job</b>\n\n"
                f"💼 <b>{j['title']}</b>\n"
                f"🏢 {j['company']}\n"
                f"📍 {j['location']}\n"
                f"🔗 <a href='{j['job_url']}'>Apply Now</a>"
            )
            send_telegram(msg)
            time.sleep(1.5)
    else:
        send_telegram(
            f"📊 <b>Daily GCC & MNC Job Sync Complete!</b>\n\n"
            f"Added <b>{len(new_jobs)}</b> new openings (Total tracked: <b>{len(updated_jobs)}</b> since Nov 1) across your 550 GCC & MNC companies."
        )
else:
    print("No new GCC/MNC jobs found in this run.")
    
