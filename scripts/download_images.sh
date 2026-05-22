#!/usr/bin/env bash
# Download all scraped Squarespace CDN images into public/images/.
#
# Prerequisites: curl
# Usage: bash scripts/download_images.sh
#
# Reads:  scraped/image_urls.txt
# Writes: public/images/{sanitized-filename}

set -euo pipefail

URLS_FILE="scraped/image_urls.txt"
DEST="public/images"

if [[ ! -f "$URLS_FILE" ]]; then
  echo "ERROR: $URLS_FILE not found. Run scripts/scrape.py first."
  exit 1
fi

mkdir -p "$DEST"

total=$(grep -c . "$URLS_FILE" 2>/dev/null || echo 0)
count=0
skipped=0
failed=0

echo "Downloading $total images to $DEST/ ..."
echo ""

while IFS= read -r url || [[ -n "$url" ]]; do
  [[ -z "$url" ]] && continue
  # Normalise protocol-relative URLs (//host/...) → https://host/...
  [[ "$url" == //* ]] && url="https:${url}"

  # Derive filename: take the last path segment, URL-decode, sanitize
  raw_name=$(basename "${url%%\?*}")
  # Decode common URL encoding (%20 → space, %27 → ', etc.) then replace non-safe chars
  filename=$(python3 -c "
import sys, urllib.parse, re
name = urllib.parse.unquote('$raw_name')
name = re.sub(r'[^A-Za-z0-9._-]', '-', name)
name = re.sub(r'-{2,}', '-', name).strip('-')
print(name.lower())
  " 2>/dev/null || echo "$raw_name")

  dest_path="$DEST/$filename"

  if [[ -f "$dest_path" ]]; then
    skipped=$((skipped + 1))
    count=$((count + 1))
    continue
  fi

  if curl --silent --show-error --location \
      --max-time 30 \
      --retry 2 \
      --retry-delay 2 \
      --output "$dest_path" \
      "$url"; then
    count=$((count + 1))
    echo "  [$count/$total] $filename"
  else
    echo "  WARN: failed to download $url"
    rm -f "$dest_path"
    failed=$((failed + 1))
    count=$((count + 1))
  fi

  sleep 0.3

done < "$URLS_FILE"

echo ""
echo "Done."
echo "  Downloaded: $((count - skipped - failed))"
echo "  Skipped (already existed): $skipped"
echo "  Failed: $failed"
