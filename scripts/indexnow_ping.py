#!/usr/bin/env python3
"""IndexNow bulk URL ping — runs after each successful production deployment."""
import json
import os
import re
import sys

import requests

SITE_URL = os.environ.get("SITE_URL", "https://www.catalinaskitchen.com")
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY", "")
INDEXNOW_API = "https://api.indexnow.org/indexnow"

if not INDEXNOW_KEY:
    print("WARN: INDEXNOW_KEY secret not set — skipping IndexNow ping")
    sys.exit(0)

host = SITE_URL.removeprefix("https://").removeprefix("http://").rstrip("/")
key_location = f"{SITE_URL}/{INDEXNOW_KEY}.txt"


def fetch_urls(sitemap_url: str) -> list[str]:
    urls: list[str] = []
    try:
        r = requests.get(sitemap_url, timeout=15)
        r.raise_for_status()
        if "<sitemapindex" in r.text:
            for child in re.findall(r"<loc>(https?://[^<]+)</loc>", r.text):
                urls.extend(fetch_urls(child))
        else:
            urls.extend(re.findall(r"<loc>(https?://[^<]+)</loc>", r.text))
    except Exception as exc:
        print(f"WARN: Could not fetch {sitemap_url}: {exc}")
    return urls


sitemap_index = f"{SITE_URL}/sitemap-index.xml"
print(f"Fetching URLs from {sitemap_index} ...")
all_urls = fetch_urls(sitemap_index)

if not all_urls:
    print("WARN: No URLs found in sitemap — skipping ping")
    sys.exit(0)

print(f"Submitting {len(all_urls)} URLs to IndexNow ...")

payload = {
    "host": host,
    "key": INDEXNOW_KEY,
    "keyLocation": key_location,
    "urlList": all_urls[:10_000],
}

try:
    resp = requests.post(
        INDEXNOW_API,
        headers={"Content-Type": "application/json; charset=utf-8"},
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=30,
    )
    if resp.status_code in (200, 202):
        print(f"PASS — IndexNow accepted {len(all_urls)} URLs (HTTP {resp.status_code})")
    elif resp.status_code == 422:
        print(f"WARN — IndexNow 422: key file not found at {key_location}")
        print("       Ensure public/{INDEXNOW_KEY}.txt is deployed to production.")
    else:
        print(f"WARN — IndexNow returned HTTP {resp.status_code}: {resp.text[:300]}")
except Exception as exc:
    print(f"WARN: IndexNow ping failed: {exc}")
