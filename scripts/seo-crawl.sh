#!/usr/bin/env bash
# scripts/seo-crawl.sh — pre-push gate: CVE scan + SEO crawl against built output.
# Runs Trivy (HIGH/CRITICAL CVEs), then `astro build` + `python3 -m http.server`
# so the SEO crawl targets the same static output Vercel deploys.
# Prerequisites: python3, pnpm; trivy for CVE scan; kubectl for SEO crawl.
# Exits 1 on failures; exits 0 if clean or if kubectl unavailable (SEO crawl skips).
# Pass --no-verify to git push/pre-push to bypass entirely.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[seo-check] python3 not found — skipping." >&2; exit 0
fi

if ! python3 -c "import requests, bs4" 2>/dev/null; then
    echo "[seo-check] Installing Python deps (requests, beautifulsoup4)..." >&2
    pip install -q requests beautifulsoup4
fi

# ── Trivy: dependency CVE scan ───────────────────────────────────────────────
TRIVY_BIN=$(command -v trivy 2>/dev/null || echo "${HOME}/.local/bin/trivy")
if [ -x "$TRIVY_BIN" ]; then
    echo "[seo-check] Trivy: scanning for HIGH/CRITICAL CVEs..."
    if ! "$TRIVY_BIN" fs . \
        --scanners vuln \
        --severity HIGH,CRITICAL \
        --exit-code 1 \
        --skip-dirs .git,node_modules \
        --quiet 2>&1; then
        echo "" >&2
        echo "[seo-check] HIGH or CRITICAL CVEs found — fix before pushing." >&2
        exit 1
    fi
    echo "[seo-check] Trivy: clean."
else
    echo "[seo-check] Trivy not found — skipping CVE scan." >&2
fi

if ! command -v kubectl >/dev/null 2>&1 \
   || ! kubectl get configmap site-audit-crawler-script -n site-audit >/dev/null 2>&1; then
    echo "[seo-check] kubectl unavailable or ConfigMap not found — skipping." >&2
    echo "  (Requires cluster access to VISION to enable.)" >&2
    exit 0
fi

CRAWLER_PY=$(mktemp "/tmp/seo-crawler-XXXXXX.py")
DATA_DIR=$(mktemp -d "/tmp/seo-check-local-XXXXXX")
SERVER_PID=""

cleanup() {
    [ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null || true
    rm -f "$CRAWLER_PY"
    rm -rf "$DATA_DIR"
}
trap cleanup EXIT

kubectl get configmap site-audit-crawler-script -n site-audit \
    -o jsonpath='{.data.crawler\.py}' > "$CRAWLER_PY"

echo "[seo-check] Building site (astro build)..."
if ! pnpm build 2>&1; then
    echo "[seo-check] Build failed — fix build errors before pushing." >&2
    exit 1
fi

STATIC_DIR=".vercel/output/static"
if [ ! -d "$STATIC_DIR" ]; then
    echo "[seo-check] Build output not found at ${STATIC_DIR}." >&2
    exit 1
fi

PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('',0)); p=s.getsockname()[1]; s.close(); print(p)")
echo "[seo-check] Serving build output on :${PORT}..."
python3 -m http.server "$PORT" --directory "$STATIC_DIR" >/dev/null 2>&1 &
SERVER_PID=$!

echo -n "[seo-check] Waiting for server"
for i in $(seq 1 15); do
    if curl -sf "http://localhost:${PORT}" >/dev/null 2>&1; then echo " ready."; break; fi
    echo -n "."; sleep 1
done

if ! curl -sf "http://localhost:${PORT}" >/dev/null 2>&1; then
    echo "" >&2
    echo "[seo-check] Static server failed to start in 15s." >&2
    exit 1
fi

echo "[seo-check] Crawling http://localhost:${PORT} ..."
SITE_URL="http://localhost:${PORT}" DATA_DIR="$DATA_DIR" python3 "$CRAWLER_PY"

export SEO_DATA_DIR="$DATA_DIR"
python3 - <<'PYEOF'
import json, sys, os, glob

data_dir = os.environ["SEO_DATA_DIR"]
files = glob.glob(f"{data_dir}/*.json")
if not files:
    print("ERROR: no crawler output found")
    sys.exit(1)

with open(files[0]) as f:
    result = json.load(f)

# canonical_mismatch: canonicals point to prod domain, not localhost
# redirect_links: python3 -m http.server sends 301s for missing trailing slashes;
#   Vercel's routing handles these transparently — CI catches real redirect issues.
SKIP = {"canonical_mismatch", "redirect_links"}

# Non-blocking: tracked in output but do not fail the gate.
# images_missing_dimensions: 210 existing images lack width/height — fix requires
#   Astro <Image> component work across templates; tracked until count reaches 0.
WARN_ONLY = {"images_missing_dimensions"}

# Domains that block bots with non-200 responses (not actual broken links)
BOT_BLOCKED_DOMAINS = {"www.linkedin.com", "linkedin.com"}

def _is_bot_blocked(item):
    url = item if isinstance(item, str) else (item.get("url") or item.get("link") or str(item))
    return any(d in url for d in BOT_BLOCKED_DOMAINS)

counts = {}
for k, v in result["issues"].items():
    if k == "external_4xx":
        v = [item for item in v if not _is_bot_blocked(item)]
    counts[k] = len(v)
failures = []

print(f"\n{'Issue type':<35} {'Count':>8} {'':>10}")
print("-" * 55)
for issue_type, count in sorted(counts.items()):
    if issue_type in SKIP:
        continue
    if count > 0:
        if issue_type in WARN_ONLY:
            status = "WARN"
        else:
            status = "FAIL"
            failures.append((issue_type, count))
    else:
        status = "pass"
    print(f"{issue_type:<35} {count:>8} {status:>10}")

print()
if failures:
    print(f"FAIL — {len(failures)} issue type(s) with errors:")
    for t, c in failures:
        print(f"  {t}: {c}")
        items = result["issues"].get(t, [])
        for item in items[:5]:
            url = item if isinstance(item, str) else (item.get("url") or item.get("page") or str(item))
            detail = "" if isinstance(item, str) else (f" — {item.get('title') or item.get('value') or ''}")
            print(f"    {url}{detail}")
    sys.exit(1)
else:
    print(f"PASS — zero SEO issues. ({result['pages_crawled']} pages crawled)")
PYEOF

echo ""
echo "[seo-check] Indexing health (Serposcope ranks + LHCI scores) runs post-deploy via CI."
echo "            Check the 'prometheus-gate' job in GitHub Actions after pushing to preview → main."
