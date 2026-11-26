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

LOCATION = "Hyderabad, Telangana, India"
JOBS_FILE = "jobs.json"
COMPANIES_FILE = "companies.json"
BATCH_FILE = "batch_index.txt"
START_DATE_CUTOFF = "2026-11-01"

# Process 25 companies per run so GitHub Actions stays fast and avoids IP bans
BATCH_SIZE = 25

# Role keywords to filter relevant openings from each company
ROLE_KEYWORDS = (
    "finance", "audit", "payable", "receivable", "analyst", "accounting",
    "accountant", "equity", "tax", "risk", "treasury", "controller",
    "reconciliation", "billing", "payroll", "fp&a", "compliance", "operations"
)

def clean_company(name):
    name = str(name).lower()
    name = re.sub(r"\([^)]*\)", " ", name)
    name = re.sub(
        r"\b(pvt|ltd|private|limited|india|inc|llc|llp|corp|services|solutions|technologies|technology|group|global|gds|usi|acceleration|centers|centre|center|hospital|hospitals|pharmaceuticals|pharma)\b",
        " ",
        name,
    )
    return re.sub(r"[^a-z0-9]", "", name)

# 1. Load all 541 GCC & MNC companies from companies.xlsx
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

total_companies = len(unique_companies)
print(f"Loaded {total_companies} unique GCC & MNC companies.")

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

def matches_role(title):
    t = str(title).lower()
    return any(k in t for k in ROLE_KEYWORDS)

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

# 2. Determine which batch of 25 companies to scan in this run
start_idx = 0
if os.path.exists(BATCH_FILE):
    try:
        with open(BATCH_FILE, "r") as bf:
            start_idx = int(bf.read().strip())
    except Exception:
        start_idx = 0

if start_idx >= total_companies:
    start_idx = 0

end_idx = min(start_idx + BATCH_SIZE, total_companies)
batch = unique_companies[start_idx:end_idx]
next_idx = 0 if end_idx >= total_companies else end_idx

print(f"Scanning batch {start_idx + 1} to {end_idx} of {total_companies} companies...")

if os.path.exists(JOBS_FILE):
    with open(JOBS_FILE, "r", encoding="utf-8") as f:
        existing_jobs = json.load(f)
else:
    existing_jobs = []

seen_urls = {job["job_url"] for job in existing_jobs}
new_jobs = []

# 3. Scrape LinkedIn, Naukri, and Google Jobs (direct career portals) for each company in batch
for comp_info in batch:
    comp_name = comp_info["name"]
    short_name = re.sub(r"\([^)]*\)", "", comp_name).strip()
    query = f"{short_name} Finance Audit Analyst"
    google_query = f"{short_name} jobs Hyderabad Finance Audit Analyst"

    print(f"Checking: {short_name}...")
    try:
        df = scrape_jobs(
            site_name=["linkedin", "naukri", "google"],
            search_term=query,
            google_search_term=google_query,
            location=LOCATION,
            results_wanted=10,
            hours_old=624,  # Captures all active openings from Nov 1 onward
        )
    except Exception as e:
        print(f"Error for {short_name}: {e}")
        time.sleep(4)
        continue

    if not df.empty:
        for _, row in df.iterrows():
            job_url = str(row.get("job_url", "")).strip()
            if not job_url or job_url == "None" or job_url in seen_urls:
                continue

            scraped_comp = str(row.get("company", "")).strip()
            title = str(row.get("title", "N/A")).strip()

            # Verify company matches our GCC/MNC list and role matches Finance/Audit/Analyst
            match = match_gcc_mnc(scraped_comp) or comp_info
            if not match_gcc_mnc(scraped_comp) and clean_company(short_name) not in clean_company(scraped_comp):
                continue
            if not matches_role(title):
                continue

            date_posted = str(row.get("date_posted", "")).strip()
            if date_posted and date_posted != "None" and date_posted < START_DATE_CUTOFF:
                continue

            seen_urls.add(job_url)
            site_label = str(row.get("site", "N/A")).capitalize()
            if site_label.lower() == "Google":
                site_label = "Career Page (Google)"

            job_entry = {
                "id": job_url,
                "title": title,
                "company": match["name"],
                "raw_company": scraped_comp,
                "category": match["category"],
                "sector": match["sector"],
                "location": str(row.get("location", "Hyderabad")),
                "site": site_label,
                "job_url": job_url,
                "date_posted": date_posted if date_posted != "None" else time.strftime("%Y-%m-%d"),
                "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            new_jobs.append(job_entry)

    time.sleep(3)  # Gentle delay between companies

# 4. Save updated jobs.json and advance batch_index.txt
with open(BATCH_FILE, "w") as bf:
    bf.write(str(next_idx))

if new_jobs:
    new_jobs.sort(key=lambda x: x.get("date_posted", ""), reverse=True)
    updated_jobs = (new_jobs + existing_jobs)[:3000]
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_jobs, f, indent=2, ensure_ascii=False)
    print(f"Added {len(new_jobs)} new jobs! Total stored: {len(updated_jobs)}. Next batch starts at index {next_idx}.")

    if len(new_jobs) <= 8:
        for j in new_jobs:
            msg = (
                f"🆕 <b>[{j['category']}] {j['site']}</b>\n\n"
                f"💼 <b>{j['title']}</b>\n"
                f"🏢 {j['company']}\n"
                f"📍 {j['location']}\n"
                f"🔗 <a href='{j['job_url']}'>Apply Now</a>"
            )
            send_telegram(msg)
            time.sleep(1.5)
    else:
        send_telegram(
            f"🔄 <b>Batch {start_idx + 1}–{end_idx} / {total_companies} Complete!</b>\n\n"
            f"Found <b>{len(new_jobs)}</b> new openings across LinkedIn, Naukri & Career Pages (Total stored: <b>{len(updated_jobs)}</b>)."
        )
else:
    print(f"No new jobs in batch {start_idx + 1}–{end_idx}. Next batch starts at index {next_idx}.")
    
