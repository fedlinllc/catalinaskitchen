# Catalina's Kitchen

Rebuild of [catalinaskitchen.com](https://www.catalinaskitchen.com) — migrated from Squarespace to a modern stack and redeployed on Vercel.

## Stack

| Layer | Choice |
|---|---|
| Framework | [Astro 6](https://astro.build) — static SSG |
| UI | [Tailwind CSS v4](https://tailwindcss.com) + [DaisyUI v5](https://daisyui.com) |
| Interactivity | React islands (`@astrojs/react`) |
| CMS | [Contentful](https://contentful.com) v11 |
| Package manager | pnpm |
| Deployment | Vercel (`@astrojs/vercel`) |

## Local Development

```bash
cp .env.example .env   # fill in Contentful credentials
pnpm install
pnpm dev               # http://localhost:4321
```

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CONTENTFUL_SPACE_ID` | Yes | Contentful space ID |
| `CONTENTFUL_ACCESS_TOKEN` | Yes | Delivery API token (read-only) |
| `CONTENTFUL_ENVIRONMENT` | No | Defaults to `master` |
| `CONTENTFUL_PREVIEW_TOKEN` | No | Preview API token (draft content in dev) |
| `PUBLIC_GA_MEASUREMENT_ID` | No | Google Analytics 4 measurement ID |

## Content Migration

The Squarespace XML export was empty. All content is scraped from the live site and imported into Contentful.

**Run once, in order:**

```bash
# 1. Scrape all recipes, meal plans, blog posts, and image URLs
python3 scripts/scrape.py

# 2. Download images from Squarespace CDN into public/images/
bash scripts/download_images.sh

# 3. Import content into Contentful (idempotent — safe to re-run)
export CONTENTFUL_SPACE_ID=...
export CONTENTFUL_MANAGEMENT_TOKEN=...   # Settings → API keys → Content management tokens
python3 scripts/import_to_contentful.py
```

The import script creates all Contentful content types on first run, then upserts entries by slug.

## Contentful Content Model

| Content Type | Key Fields |
|---|---|
| `recipe` | title, slug, category, publishedDate, ingredients (RichText), instructions (RichText), featuredImage, tags |
| `mealPlan` | title, slug, weekOf, isCurrent (bool), content (RichText), featuredImage |
| `blogPost` | title, slug, publishedDate, content (RichText), featuredImage, tags |
| `author` | name, bio, photo |

## Project Structure

```
src/
  components/
    Nav.astro
    Footer.astro
    RecipeCard.astro
    CategoryFilter.tsx      # React island — client-side category filter
    NewsletterSignup.tsx    # React island — email subscribe form
  layouts/
    BaseLayout.astro        # OG/Twitter meta, canonical URL, GA4, fonts
    RecipeLayout.astro      # Recipe schema JSON-LD + two-column layout
  lib/
    contentful.ts           # Typed skeletons + query helpers
  pages/
    index.astro
    recipes/[slug].astro
    meal-plans/[slug].astro
    blog/[slug].astro
    contact.astro
    privacy-policy.astro
  styles/
    global.css              # Tailwind @theme + DaisyUI + prose-catalina
scripts/
  scrape.py                 # Site crawler → scraped/content.json
  download_images.sh        # Squarespace CDN → public/images/
  import_to_contentful.py   # Contentful Management API import
  ci/
    pre-commit              # Gitleaks staged-file scan
    pre-push               # Gitleaks + astro check + Trivy SCA
    install-hooks.sh        # Wire hooks into .git/hooks/
  seo-crawl.sh             # Local SEO + CVE gate (pre-push)
  seo_prometheus_gate.sh   # Serposcope + LHCI post-deploy check
  indexnow_ping.py         # IndexNow bulk URL submission
  gsc_check.py             # GSC URL inspection + sitemap resubmit
  gsc_serposcope_sync.py   # Weekly GSC → Serposcope query sync
public/
  images/                  # Migrated Squarespace images (gitignored during import)
  robots.txt
```

## Building

```bash
pnpm build      # astro check && astro build → dist/
pnpm preview    # serve dist/ locally
```

## Deployment

Connected to Vercel. Merges to `main` deploy to production; `preview` branch deploys to a preview URL.

```json
// vercel.json
{ "buildCommand": "pnpm build", "installCommand": "pnpm install" }
```

Set all environment variables under **Vercel → Project → Settings → Environment Variables**.

## CI/CD Gates

Five GitHub Actions workflows run on every push/PR:

| Workflow | Trigger | Gates |
|---|---|---|
| `ci.yml` | push/PR to `main`, `preview` | Build + type check, Gitleaks, Trivy SCA (CRITICAL/HIGH), CodeQL SAST |
| `security.yml` | push/PR to `main` | Gitleaks, Trivy, CodeQL (secondary pipeline) |
| `dast.yml` | nightly 03:45 UTC | OWASP ZAP baseline scan |
| `seo-gate.yml` | post-deployment | SEO crawler, Lighthouse (SEO ≥ 0.90, Perf ≥ 0.90, LCP ≤ 2500ms, CLS ≤ 0.10), Serposcope rank-drop detection, IndexNow ping, GSC sitemap resubmit |
| `gsc-serposcope-sync.yml` | Sunday 05:00 UTC | GSC → Serposcope query sync |

### Local Hooks

Install once per clone:

```bash
bash scripts/ci/install-hooks.sh
```

- **pre-commit** — Gitleaks scans staged files
- **pre-push** — Gitleaks (full history) + `astro check` + Trivy SCA
