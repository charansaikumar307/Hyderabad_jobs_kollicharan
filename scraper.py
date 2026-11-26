import json
import os
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

def send_telegram(msg):
    url = f"https://telegram.org{BOT_TOKEN}/sendMessage"
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

# Load existing jobs from GitHub repo file
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
        continue

    if df.empty:
        continue

    for _, row in df.iterrows():
        job_url = str(row.get("job_url", "")).strip()
        if not job_url or job_url == "None" or job_url in seen_urls:
            continue

        seen_urls.add(job_url)
        job_entry = {
            "id": job_url,
            "title": str(row.get("title", "N/A")),
            "company": str(row.get("company", "N/A")),
            "location": str(row.get("location", "Hyderabad")),
            "site": str(row.get("site", "N/A")).capitalize(),
            "job_url": job_url,
            "date_posted": str(row.get("date_posted", "")),
            "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        new_jobs.append(job_entry)

        msg = (
            f"🆕 <b>New {job_entry['site']} Job</b>\n\n"
            f"💼 <b>{job_entry['title']}</b>\n"
            f"🏢 {job_entry['company']}\n"
            f"📍 {job_entry['location']}\n"
            f"🔗 <a href='{job_url}'>Apply Now</a>"
        )
        send_telegram(msg)
        time.sleep(1.5)

if new_jobs:
    # Prepend newest jobs at the top and keep the latest 500
    updated_jobs = (new_jobs + existing_jobs)[:500]
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_jobs, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(new_jobs)} new jobs to {JOBS_FILE}.")
else:
    print("No new jobs found.")
  
