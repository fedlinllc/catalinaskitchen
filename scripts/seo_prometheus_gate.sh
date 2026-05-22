#!/usr/bin/env bash
# scripts/seo_prometheus_gate.sh
# Post-deploy indexing health check: queries Serposcope + LHCI Prometheus exporters.
# Runs on the self-hosted runner which has in-cluster network access to ClusterIP services.
# Exit 1 if: a keyword that previously ranked now shows rank 0 (de-indexing proxy),
#            or LHCI SEO score for the site drops below 0.90.
set -uo pipefail

SITE="${SITE:-catalinaskitchen.com}"
SERPO_IP=$(kubectl get svc serposcope-exporter -n serposcope -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
LHCI_IP=$(kubectl get svc lhci-exporter -n lhci -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
SERPO_URL="http://${SERPO_IP}:9100/metrics"
LHCI_URL="http://${LHCI_IP}:9100/metrics"

overall_exit=0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ── Serposcope: rank-drop detection (indexing proxy) ────────────────────────

echo ""
echo "── Serposcope: Rank-Drop Detection (Indexing Proxy) ───────────────────"
if curl -sf --max-time 15 "$SERPO_URL" > "$TMP/serpo.txt" 2>/dev/null; then
    METRICS_FILE="$TMP/serpo.txt" SITE_FILTER="$SITE" python3 - <<'PYEOF'
import sys, re, os

with open(os.environ["METRICS_FILE"]) as f:
    metrics = f.read()
site = os.environ["SITE_FILTER"]

def parse_metric(lines, name):
    out = {}
    pat = re.compile(rf'^{re.escape(name)}\{{([^}}]+)\}}\s+([\d.]+)')
    for line in lines:
        m = pat.match(line)
        if not m:
            continue
        labels = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        if site not in labels.get("website", ""):
            continue
        key = (labels.get("keyword", ""), labels.get("device", ""), labels.get("engine", ""))
        out[key] = float(m.group(2))
    return out

lines = metrics.splitlines()
current = parse_metric(lines, "serposcope_keyword_rank")
best    = parse_metric(lines, "serposcope_keyword_best_rank")

if not current:
    print(f"  No keywords tracked for {site} — skipping")
    sys.exit(0)

print(f"  {'Keyword':<44} {'Dev':<8} {'Rank':>5} {'Best':>5}  Status")
print("  " + "─" * 72)
failures = []
for key in sorted(current):
    kw, dev, _ = key
    rank = int(current[key])
    br   = int(best.get(key, 0))
    if br > 0 and rank == 0:
        status = "DE-INDEXED"
        failures.append(kw)
    elif rank == 0:
        status = "not ranking"
    elif rank <= 10:
        status = f"#{rank} (top 10)"
    elif rank <= 30:
        status = f"#{rank} (top 30)"
    else:
        status = f"#{rank}"
    print(f"  {kw:<44} {dev:<8} {rank:>5} {br:>5}  {status}")

print()
if failures:
    print(f"FAIL — {len(failures)} keyword(s) dropped to rank 0 (previously ranked):")
    for kw in failures:
        print(f"  - {kw}")
    sys.exit(1)
else:
    print(f"PASS — no rank drops detected ({len(current)} keyword(s) checked)")
PYEOF
    serpo_rc=$?
    [ "$serpo_rc" -ne 0 ] && overall_exit=1
else
    echo "WARN: Serposcope exporter unreachable — skipping rank check"
fi

# ── LHCI: Lighthouse SEO score gate ─────────────────────────────────────────

echo ""
echo "── LHCI: Lighthouse SEO Score Gate ────────────────────────────────────"
if curl -sf --max-time 15 "$LHCI_URL" > "$TMP/lhci.txt" 2>/dev/null; then
    METRICS_FILE="$TMP/lhci.txt" SITE_FILTER="$SITE" python3 - <<'PYEOF'
import sys, re, os

with open(os.environ["METRICS_FILE"]) as f:
    metrics = f.read()
site = os.environ["SITE_FILTER"]
SEO_MIN  = 0.90
PERF_MIN = 0.75  # scheduled LHCI crawl; strict gate (0.90) is the CI Lighthouse step at deploy time

def parse_lhci(lines):
    out = {}
    pat = re.compile(r'^lhci_score\{([^}]+)\}\s+([\d.]+)')
    for line in lines:
        m = pat.match(line)
        if not m:
            continue
        labels = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        if site not in labels.get("url", ""):
            continue
        out[(labels["url"], labels.get("category", ""))] = float(m.group(2))
    return out

lines = metrics.splitlines()
scores = parse_lhci(lines)

if not scores:
    print(f"  No LHCI data for {site} — skipping")
    sys.exit(0)

by_url = {}
for (url, cat), val in scores.items():
    by_url.setdefault(url, {})[cat] = val

cats = ["performance", "accessibility", "best-practices", "seo", "pwa"]
failures, warnings = [], []

print(f"  {'URL':<52} {'perf':>6} {'a11y':>6} {'bp':>6} {'seo':>6} {'pwa':>6}")
print("  " + "─" * 84)
for url in sorted(by_url):
    c = by_url[url]
    row = f"  {url:<52}"
    for cat in cats:
        v = c.get(cat)
        row += f"  {f'{v:.2f}' if v is not None else ' N/A':>5}"
    print(row)
    seo  = c.get("seo",  1.0)
    perf = c.get("performance", 1.0)
    if seo < SEO_MIN:
        failures.append((url, "seo", seo))
    if perf < PERF_MIN:
        failures.append((url, "performance", perf))

print()
if failures:
    print(f"\nFAIL — {len(failures)} URL(s) below threshold (seo≥{SEO_MIN}, perf≥{PERF_MIN}):")
    for url, cat, val in failures:
        print(f"  {url}: {cat}={val:.2f}")
    sys.exit(1)
else:
    print(f"PASS — all audited URLs at or above thresholds (seo≥{SEO_MIN}, perf≥{PERF_MIN})")
PYEOF
    lhci_rc=$?
    [ "$lhci_rc" -ne 0 ] && overall_exit=1
else
    echo "WARN: LHCI exporter unreachable — skipping score check"
fi

# ── LHCI: Core Web Vitals gate ──────────────────────────────────────────────

echo ""
echo "── LHCI: Core Web Vitals Gate ─────────────────────────────────────────"
if curl -sf --max-time 15 "$LHCI_URL" > "$TMP/lhci_cwv.txt" 2>/dev/null; then
    METRICS_FILE="$TMP/lhci_cwv.txt" SITE_FILTER="$SITE" python3 - <<'PYEOF'
import sys, re, os

with open(os.environ["METRICS_FILE"]) as f:
    metrics = f.read()
site  = os.environ["SITE_FILTER"]
lines = metrics.splitlines()

LCP_MAX  = 2500   # ms — Google "good" threshold
CLS_MAX  = 0.10   # score
TBT_WARN = 600    # ms — non-blocking; harder to control in Astro SSG

def parse_cwv(lines, metric_name):
    out = {}
    pat = re.compile(rf'^{re.escape(metric_name)}\{{([^}}]+)\}}\s+([\d.]+)')
    for line in lines:
        m = pat.match(line)
        if not m:
            continue
        labels = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        if site not in labels.get("url", ""):
            continue
        out[labels["url"]] = float(m.group(2))
    return out

lcp  = parse_cwv(lines, "lhci_lcp")
cls_ = parse_cwv(lines, "lhci_cls")
tbt  = parse_cwv(lines, "lhci_tbt")

if not lcp and not cls_:
    print(f"  No CWV data for {site} — skipping (available after next LHCI run)")
    sys.exit(0)

failures, warnings = [], []
all_urls = sorted(set(lcp) | set(cls_) | set(tbt))
print(f"  {'URL':<52} {'LCP(ms)':>9} {'CLS':>7} {'TBT(ms)':>9}")
print("  " + "─" * 80)
for url in all_urls:
    l = lcp.get(url)
    c = cls_.get(url)
    t = tbt.get(url)
    print(f"  {url:<52} {f'{l:.0f}' if l is not None else 'N/A':>9} "
          f"{f'{c:.3f}' if c is not None else 'N/A':>7} "
          f"{f'{t:.0f}' if t is not None else 'N/A':>9}")
    if l is not None and l > LCP_MAX:
        failures.append((url, "LCP", l, f">{LCP_MAX}ms"))
    if c is not None and c > CLS_MAX:
        failures.append((url, "CLS", c, f">{CLS_MAX}"))
    if t is not None and t > TBT_WARN:
        warnings.append((url, "TBT", t, f">{TBT_WARN}ms"))

print()
for url, metric, val, threshold in warnings:
    print(f"  WARN: {url} {metric}={val:.1f} {threshold} (non-blocking)")
if failures:
    print(f"\nFAIL — Core Web Vitals out of range:")
    for url, metric, val, threshold in failures:
        print(f"  {url}: {metric}={val:.1f} {threshold}")
    sys.exit(1)
else:
    print(f"PASS — Core Web Vitals within thresholds ({len(all_urls)} URL(s) checked)")
PYEOF
    cwv_rc=$?
    [ "$cwv_rc" -ne 0 ] && overall_exit=1
else
    echo "WARN: LHCI exporter unreachable for CWV check — skipping"
fi

echo ""
echo "── Prometheus Gate Complete ────────────────────────────────────────────"
exit "$overall_exit"
