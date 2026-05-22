#!/usr/bin/env python3
"""Sync organic queries from GSC Search Analytics into Serposcope.

Pulls the top 200 queries (by impression count) from the last 90 days,
then inserts any that don't already exist in Serposcope's rt_project_search
table. Existing keywords are never removed.

Requires kubectl in PATH with cluster access to the serposcope namespace.

Auth (first match wins — same precedence as gsc_check.py):
  GSC_CLIENT_ID / GSC_CLIENT_SECRET / GSC_REFRESH_TOKEN  (OAuth2)
  GSC_SERVICE_ACCOUNT_KEY                                 (service account JSON)

Optional env:
  SERPO_NS          Kubernetes namespace for Serposcope (default: serposcope)
  SERPO_DEPLOY      Deployment name (default: serposcope)
  SERPO_DB_POD_PATH Path to DB inside pod (default: /usr/share/serposcope/db/database.sqlite3.db)
  GSC_DAYS          Look-back window in days (default: 90)
  GSC_MIN_IMPR      Minimum impressions to include a query (default: 1)
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import date, timedelta

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ── Config ───────────────────────────────────────────────────────────────────

SCOPES      = ["https://www.googleapis.com/auth/webmasters.readonly"]
DOMAIN      = "catalinaskitchen.com"
SITE_URL    = os.environ.get("SITE_URL", f"https://www.{DOMAIN}/")
NS          = os.environ.get("SERPO_NS", "serposcope")
DEPLOY      = os.environ.get("SERPO_DEPLOY", "serposcope")
DB_POD_PATH = os.environ.get("SERPO_DB_POD_PATH", "/usr/share/serposcope/db/database.sqlite3.db")
GSC_DAYS    = int(os.environ.get("GSC_DAYS", "90"))
GSC_MIN_IMPR = int(os.environ.get("GSC_MIN_IMPR", "1"))
PROJECT_NAME = "catalinaskitchen"


# ── Auth ─────────────────────────────────────────────────────────────────────

def _build_creds():
    cid = os.environ.get("GSC_CLIENT_ID", "")
    cs  = os.environ.get("GSC_CLIENT_SECRET", "")
    rt  = os.environ.get("GSC_REFRESH_TOKEN", "")
    if cid and cs and rt:
        creds = Credentials(
            token=None, refresh_token=rt,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cid, client_secret=cs, scopes=SCOPES,
        )
        creds.refresh(Request())
        return creds
    key_json = os.environ.get("GSC_SERVICE_ACCOUNT_KEY", "")
    if key_json:
        return service_account.Credentials.from_service_account_info(
            json.loads(key_json), scopes=SCOPES
        )
    return None

try:
    creds = _build_creds()
except Exception as exc:
    print(f"WARN: GSC auth failed: {exc} — cannot sync")
    sys.exit(0)

if creds is None:
    print("WARN: No GSC credentials — set GSC_CLIENT_ID/SECRET/REFRESH_TOKEN or GSC_SERVICE_ACCOUNT_KEY")
    sys.exit(0)

wmt = build("webmasters", "v3", credentials=creds)
sc  = build("searchconsole", "v1", credentials=creds)


# ── Resolve GSC property URL ─────────────────────────────────────────────────

try:
    _sites = wmt.sites().list().execute().get("siteEntry", [])
    _match = next((s["siteUrl"] for s in _sites if DOMAIN in s.get("siteUrl", "")), None)
    if _match:
        SITE_URL = _match
        print(f"  GSC property: {SITE_URL}")
    else:
        print(f"  WARN: no property found for {DOMAIN} — using {SITE_URL}")
except Exception as exc:
    print(f"  WARN: could not list GSC properties: {exc}")


# ── Pull GSC Search Analytics ─────────────────────────────────────────────────

end_date   = date.today().isoformat()
start_date = (date.today() - timedelta(days=GSC_DAYS)).isoformat()

print()
print(f"── GSC Search Analytics ({start_date} → {end_date}) ────────────────────")

try:
    resp = sc.searchanalytics().query(
        siteUrl=SITE_URL,
        body={
            "startDate": start_date,
            "endDate":   end_date,
            "dimensions": ["query"],
            "rowLimit":   200,
            "dataState":  "all",
        },
    ).execute()
    rows = resp.get("rows", [])
except HttpError as exc:
    if exc.resp.status == 403:
        print("  WARN: Search Analytics API unavailable (HTTP 403)")
        print("        Enable searchconsole.googleapis.com in GCP project.")
    else:
        print(f"  WARN: API error HTTP {exc.resp.status} — skipping sync")
    sys.exit(0)
except Exception as exc:
    print(f"  WARN: {exc} — skipping sync")
    sys.exit(0)

# Filter by minimum impressions
gsc_queries = []
for row in rows:
    impressions = int(row.get("impressions", 0))
    if impressions >= GSC_MIN_IMPR:
        kw = row["keys"][0].strip().lower()
        gsc_queries.append((kw, impressions, round(row.get("position", 0), 1)))

print(f"  {len(rows)} queries returned, {len(gsc_queries)} with ≥{GSC_MIN_IMPR} impression(s)")
if not gsc_queries:
    print("  Nothing to sync.")
    sys.exit(0)


# ── Fetch Serposcope DB ───────────────────────────────────────────────────────

print()
print("── Fetching Serposcope DB ───────────────────────────────────────────────")

def _run(cmd, check=True):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  ERROR: {' '.join(cmd)}\n  {result.stderr.strip()}")
        sys.exit(1)
    return result

# Get pod name
pod_result = _run(["kubectl", "get", "pod", "-n", NS, "-l", f"app={DEPLOY}",
                   "-o", "jsonpath={.items[0].metadata.name}"])
pod_name = pod_result.stdout.strip()
if not pod_name:
    print(f"  WARN: no running {DEPLOY} pod in namespace {NS} — skipping")
    sys.exit(0)
print(f"  Pod: {pod_name}")

tmpdir = tempfile.mkdtemp()
local_db = os.path.join(tmpdir, "database.sqlite3.db")

_run(["kubectl", "cp", f"{NS}/{pod_name}:{DB_POD_PATH}", local_db])
print(f"  DB copied to {local_db} ({os.path.getsize(local_db)} bytes)")


# ── Read existing keywords and project info ───────────────────────────────────

conn = sqlite3.connect(local_db)

# Find or create the project
cur = conn.execute(
    f"SELECT id FROM project WHERE json_extract(jdoc, '$.name') = ?",
    [PROJECT_NAME]
)
row = cur.fetchone()
if row:
    project_id = row[0]
    print(f"  Project '{PROJECT_NAME}' found: {project_id}")
else:
    project_id = str(uuid.uuid4())
    jdoc = {
        "id": project_id, "_v": 0, "name": PROJECT_NAME,
        "cron": {"enabled": False, "time": "00:00"},
        "search": {"lang": "EN", "country": None},
    }
    conn.execute("INSERT INTO project VALUES (?, ?)", [project_id, json.dumps(jdoc).encode()])
    print(f"  Project '{PROJECT_NAME}' created: {project_id}")

# Find or create the website
cur = conn.execute(
    "SELECT id FROM rt_website WHERE json_extract(jdoc, '$.projectId') = ?",
    [project_id]
)
row = cur.fetchone()
if row:
    website_id = row[0]
    print(f"  Website found: {website_id}")
else:
    website_id = str(uuid.uuid4())
    # Website schema (only 5 recognized fields; url/checkInterval are not part of the model)
    wjdoc = {
        "id": website_id, "_v": 0,
        "name": DOMAIN,
        "projectId": project_id,
        "pattern": {"@": "SubdomainsWebsitePattern", "domain": DOMAIN},
    }
    conn.execute("INSERT INTO rt_website VALUES (?, ?)", [website_id, json.dumps(wjdoc).encode()])
    print(f"  Website created: {website_id}")

# Existing keywords
cur = conn.execute(
    "SELECT json_extract(jdoc, '$.search.keyword') FROM rt_project_search WHERE json_extract(jdoc, '$.projectId') = ?",
    [project_id]
)
existing = {r[0].strip().lower() for r in cur.fetchall() if r[0]}
print(f"  Existing keywords: {len(existing)}")


# ── Insert new keywords ───────────────────────────────────────────────────────

print()
print("── Inserting new keywords ───────────────────────────────────────────────")

new_count = 0
skipped   = 0

for kw, impr, pos in gsc_queries:
    if kw in existing:
        skipped += 1
        continue
    ps_id = str(uuid.uuid4())
    ps_jdoc = {
        "id": ps_id, "_v": 0,
        "projectId": project_id,
        "search": {
            "keyword":     kw,
            "device":      "DESKTOP",
            "engine":      "GOOGLE_ORGANIC",
            "lang":        "EN",
            "location":    {"@": "NoLocation"},
            "queryParams": None,
            "hash":        None,
        },
    }
    conn.execute("INSERT INTO rt_project_search VALUES (?, ?)", [ps_id, json.dumps(ps_jdoc).encode()])
    print(f"  + {kw:<52} ({impr} impr, pos {pos})")
    new_count += 1

conn.commit()

# Checkpoint WAL so data lands in main file
conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
conn.close()

print()
print(f"  Added: {new_count}  Already present: {skipped}")

if new_count == 0:
    print("  Nothing new to push — done.")
    shutil.rmtree(tmpdir, ignore_errors=True)
    sys.exit(0)


# ── Push DB back and restart pod ─────────────────────────────────────────────

print()
print("── Pushing DB back to pod ───────────────────────────────────────────────")
_run(["kubectl", "cp", local_db, f"{NS}/{pod_name}:{DB_POD_PATH}"])
print(f"  DB pushed to {NS}/{pod_name}")

print("  Restarting Serposcope pod to reload DB …")
_run(["kubectl", "delete", "pod", "-n", NS, pod_name], check=False)
time.sleep(3)

# Wait for new pod
for _ in range(30):
    r = _run(["kubectl", "get", "pod", "-n", NS, "-l", f"app={DEPLOY}",
              "--field-selector=status.phase=Running",
              "-o", "jsonpath={.items[0].metadata.name}"], check=False)
    if r.stdout.strip() and r.stdout.strip() != pod_name:
        print(f"  New pod: {r.stdout.strip()}")
        break
    time.sleep(5)
else:
    print("  WARN: timed out waiting for new pod — Serposcope may need manual restart")

shutil.rmtree(tmpdir, ignore_errors=True)

print()
print("── GSC → Serposcope sync complete ──────────────────────────────────────")
print(f"   {new_count} keyword(s) added from GSC organic queries")
print(f"   Serposcope will rank-check them on the next scheduled crawl (04:00 UTC)")
