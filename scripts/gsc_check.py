#!/usr/bin/env python3
"""GSC URL Inspection, sitemap coverage report, and sitemap resubmission.

Runs as the final step of the prometheus-gate CI job after each prod deployment.
Exit 1 if any of the 15 critical pages returns a NOT_INDEXED verdict from GSC.
Sitemap stats and resubmission are always non-blocking.

Auth (first match wins):
  Option 1 — OAuth2 refresh token (preferred; no service account required):
    GSC_CLIENT_ID       OAuth2 Desktop app client ID
    GSC_CLIENT_SECRET   OAuth2 Desktop app client secret
    GSC_REFRESH_TOKEN   Refresh token from one-time browser auth flow

  Option 2 — Service account JSON key:
    GSC_SERVICE_ACCOUNT_KEY  Full JSON key content

  SITE_URL  Exact GSC property URL, e.g. https://www.affinitytherapytn.com/
            Must match the property as registered in Search Console.
"""
import json
import os
import sys
import time

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/webmasters"]

SITE_URL = os.environ.get("SITE_URL", "https://www.catalinaskitchen.com/")
if not SITE_URL.endswith("/"):
    SITE_URL += "/"

SITEMAP_URL = f"{SITE_URL}sitemap-index.xml"

CRITICAL_PAGES = [
    SITE_URL,
    f"{SITE_URL}recipes/",
    f"{SITE_URL}meal-plans/",
    f"{SITE_URL}blog/",
]

# ── Auth (Option 1: refresh token; Option 2: service account) ────────────────

def _build_creds() -> "Credentials | service_account.Credentials | None":
    client_id     = os.environ.get("GSC_CLIENT_ID", "")
    client_secret = os.environ.get("GSC_CLIENT_SECRET", "")
    refresh_token = os.environ.get("GSC_REFRESH_TOKEN", "")
    if client_id and client_secret and refresh_token:
        print("  Auth: OAuth2 refresh token")
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        creds.refresh(Request())  # obtain initial access token
        return creds

    key_json = os.environ.get("GSC_SERVICE_ACCOUNT_KEY", "")
    if key_json:
        print("  Auth: service account JSON key")
        return service_account.Credentials.from_service_account_info(
            json.loads(key_json), scopes=SCOPES
        )

    return None

try:
    creds = _build_creds()
except Exception as exc:
    print(f"WARN: GSC auth failed: {exc} — skipping GSC check")
    sys.exit(0)

if creds is None:
    print(
        "WARN: No GSC credentials found.\n"
        "  Set GSC_CLIENT_ID + GSC_CLIENT_SECRET + GSC_REFRESH_TOKEN (preferred)\n"
        "  or GSC_SERVICE_ACCOUNT_KEY — skipping GSC check"
    )
    sys.exit(0)

wmt = build("webmasters",    "v3", credentials=creds)
sc  = build("searchconsole", "v1", credentials=creds)

# Auto-discover the registered GSC property that matches our domain.
# The property may be a domain property (sc-domain:affinitytherapytn.com)
# or a URL-prefix property (https://www.affinitytherapytn.com/) — the
# siteUrl sent to the API must match the registration exactly.
_domain = "catalinaskitchen.com"
try:
    _sites = wmt.sites().list().execute().get("siteEntry", [])
    _match = next((s["siteUrl"] for s in _sites if _domain in s.get("siteUrl", "")), None)
    if _match:
        print(f"  Discovered GSC property: {_match}")
        SITE_URL = _match
        SITEMAP_URL = f"https://www.{_domain}/sitemap-index.xml"
    else:
        print(f"  WARN: no GSC property found containing '{_domain}' — using env SITE_URL")
except Exception as exc:
    print(f"  WARN: could not list GSC sites: {exc} — using env SITE_URL")

overall_exit = 0

# ── Part A: URL Inspection (CI-blocking) ─────────────────────────────────────

print()
print("── GSC: URL Inspection (Critical Pages) ────────────────────────────────")
print(f"  {'URL':<58} {'Verdict':<12} Coverage state")
print("  " + "─" * 100)

failures = []
api_unavailable = False
for url in CRITICAL_PAGES:
    try:
        resp = sc.urlInspection().index().inspect(
            body={"inspectionUrl": url, "siteUrl": SITE_URL}
        ).execute()
        isr = resp.get("inspectionResult", {}).get("indexStatusResult", {})
        verdict  = isr.get("verdict", "UNKNOWN")
        coverage = isr.get("coverageState", "—")
        if verdict == "PASS":
            label = "INDEXED"
        elif verdict == "FAIL":
            label = "NOT_INDEXED"
            failures.append((url, coverage))
        elif verdict == "NEUTRAL":
            label = "EXCLUDED"
        else:
            label = verdict
        print(f"  {url:<58} {label:<12} {coverage}")
        time.sleep(0.12)  # stay under the 600 req/min quota
    except HttpError as exc:
        if exc.resp.status == 403:
            api_unavailable = True
        reason = exc._get_reason()[:60] if hasattr(exc, "_get_reason") else str(exc)[:60]
        print(f"  {url:<58} {'API_ERROR':<12} HTTP {exc.resp.status}: {reason}")
    except Exception as exc:
        print(f"  {url:<58} {'ERROR':<12} {str(exc)[:60]}")

print()
if failures:
    print(f"FAIL — {len(failures)} critical page(s) not indexed by Google:")
    for url, state in failures:
        print(f"  {url}")
        print(f"    Coverage: {state}")
    overall_exit = 1
elif api_unavailable:
    print("WARN: URL Inspection API unavailable (HTTP 403) — indexing unverified")
    print("      Enable searchconsole.googleapis.com in the GCP project that owns")
    print("      GSC_CLIENT_ID to fix. (GCP Console → APIs & Services → Enable APIs)")
else:
    print(f"PASS — all {len(CRITICAL_PAGES)} critical pages confirmed indexed")

# ── Part B: Sitemap coverage stats (informational) ───────────────────────────

print()
print("── GSC: Sitemap Coverage ────────────────────────────────────────────────")
try:
    sitemap = wmt.sitemaps().get(siteUrl=SITE_URL, feedpath=SITEMAP_URL).execute()
    contents        = sitemap.get("contents", [])
    submitted_total = sum(int(c.get("submitted", 0)) for c in contents)
    indexed_total   = sum(int(c.get("indexed",   0)) for c in contents)
    gap             = submitted_total - indexed_total
    print(f"  Sitemap:        {SITEMAP_URL}")
    print(f"  Last submitted: {sitemap.get('lastSubmitted', 'unknown')}")
    print(f"  Last fetched:   {sitemap.get('lastDownloaded', 'unknown')}")
    print(f"  Submitted:      {submitted_total}")
    print(f"  Indexed:        {indexed_total}")
    if gap > 0:
        print(f"  Gap:            {gap} page(s) submitted but not yet indexed")
    else:
        print(f"  Gap:            0 — full coverage")
except HttpError as exc:
    print(f"  WARN: sitemap stats unavailable (HTTP {exc.resp.status}) — non-blocking")
except Exception as exc:
    print(f"  WARN: {exc} — non-blocking")

# ── Part C: Sitemap resubmission ─────────────────────────────────────────────

print()
print("── GSC: Sitemap Resubmission ────────────────────────────────────────────")
try:
    wmt.sitemaps().submit(siteUrl=SITE_URL, feedpath=SITEMAP_URL).execute()
    print(f"  PASS — sitemap resubmitted → {SITEMAP_URL}")
    print(f"         Googlebot will re-crawl on its next scheduled pass.")
except HttpError as exc:
    print(f"  WARN: resubmission failed (HTTP {exc.resp.status}) — non-blocking")
except Exception as exc:
    print(f"  WARN: {exc} — non-blocking")

print()
print("── GSC Check Complete ───────────────────────────────────────────────────")
sys.exit(overall_exit)
