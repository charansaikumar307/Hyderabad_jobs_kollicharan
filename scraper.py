import csv
import glob
import io
import json
import os
import re
import time
import requests
from jobspy import scrape_jobs

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

SEARCH_QUERIES = [
    "Finance Audit",
    "Accounts Payable",
    "Financial Analyst",
    "Equity Research",
]
LOCATION = "Hyderabad, Telangana, India"
JOBS_FILE = "jobs.json"
STRICT_GCC_MNC_ONLY = True

def clean_company(name):
    name = name.lower()
    name = re.sub(r"\([^)]*\)", " ", name)
    name = re.sub(
        r"\b(pvt|ltd|private|limited|india|inc|llc|llp|corp|services|solutions|technologies|technology|group|global|gds|usi|acceleration|centers|centre|center|hospital|hospitals|pharmaceuticals|pharma)\b",
        " ",
        name,
    )
    return re.sub(r"[^a-z0-9]", "", name)

gcc_mnc_map = {}
csv_files = glob.glob("*.csv") + glob.glob("*.CSV")
print(f"Found CSV files: {csv_files}")

for csv_path in csv_files:
    with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        lines = f.readlines()

    # Find the exact header line containing 'category' and 'company'
    start_idx = 0
    for i, line in enumerate(lines):
        low = line.lower()
        if "category" in low and "company" in low:
            start_idx = i
            break

    reader = csv.DictReader(io.StringIO("".join(lines[start_idx:])))
    for row in reader:
        row_lower = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        cat = row_lower.get("category", "").upper()
        comp = row_lower.get("company", "")
        sector = row_lower.get("domain / sector", "")
        if cat in ("GCC", "MNC") and comp:
            aliases = [re.sub(r"\([^)]*\)", "", comp).strip()]
            aliases.extend(re.findall(r"\(([^)]*)\)", comp))
            for alias in aliases:
                key = clean_company(alias)
                if len(key) >= 3:
                    gcc_mnc_map[key] = {"category": cat, "sector": sector}

print(f"Loaded {len(gcc_mnc_map)} normalized GCC & MNC keys.")

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

if os.path.exists(JOBS_FILE):
    with open(JOBS_FILE, "r", encoding="utf-8") as f:
        existing_jobs = json.load(f)
else:
    existing_jobs = []

seen_urls = {job["job_url"] for job in existing_jobs}
new_jobs = []

for term in SEARCH_QUERIES:
    print(f"Scraping LinkedIn & Naukri for: {term}...")
    try:
        df = scrape_jobs(
            site_name=["linkedin", "naukri"],
            search_term=term,
            location=LOCATION,
            results_wanted=15,
            hours_old=24,
        )
    except Exception as e:
        print(f"Error scraping {term}: {e}")
        time.sleep(5)
        continue

    if not df.empty:
        for _, row in df.iterrows():
            job_url = str(row.get("job_url", "")).strip()
            if not job_url or job_url == "None" or job_url in seen_urls:
                continue

            company = str(row.get("company", "N/A")).strip()
            match = match_gcc_mnc(company)

            if STRICT_GCC_MNC_ONLY and not match:
                continue

            seen_urls.add(job_url)
            category_tag = match["category"] if match else "Other"
            sector_tag = match["sector"] if match else ""

            job_entry = {
                "id": job_url,
                "title": str(row.get("title", "N/A")),
                "company": company,
                "category": category_tag,
                "sector": sector_tag,
                "location": str(row.get("location", "Hyderabad")),
                "site": str(row.get("site", "N/A")).capitalize(),
                "job_url": job_url,
                "date_posted": str(row.get("date_posted", "")),
                "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            new_jobs.append(job_entry)

            msg = (
                f"🆕 <b>[{category_tag}] New {job_entry['site']} Job</b>\n\n"
                f"💼 <b>{job_entry['title']}</b>\n"
                f"🏢 {company}\n"
                f"📍 {job_entry['location']}\n"
                f"🔗 <a href='{job_url}'>Apply Now</a>"
            )
            send_telegram(msg)
            time.sleep(1.5)

    time.sleep(5)

if new_jobs:
    updated_jobs = (new_jobs + existing_jobs)[:500]
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_jobs, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(new_jobs)} new GCC/MNC jobs to {JOBS_FILE}.")
else:
    print("No new matching GCC/MNC jobs found.")
    
