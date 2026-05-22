# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-22

### Added
- Initial site scaffold: Astro 6, Tailwind CSS v4, DaisyUI v5, `@astrojs/react` islands
- Contentful v11 integration with typed `EntrySkeletonType` skeletons for `recipe`, `mealPlan`, `blogPost`, `author`; graceful `null` fallback when credentials are absent so `pnpm dev` works without a Contentful space
- Full content migration from catalinaskitchen.com: `scripts/scrape.py` (24 recipes, meal plans, blog posts → `scraped/content.json`), `scripts/download_images.sh` (37 images → `public/images/`), `scripts/import_to_contentful.py` (Contentful Management API upsert, idempotent)
- Homepage with full-bleed 5-column category-grid hero (text overlaid), Nutrition Guidance section, Contentful-driven recipe grid, newsletter CTA
- Recipes index with category image tiles (Breakfast, Dinner, Sides, Sauces & Salsas, Dessert) and Contentful recipe card grid
- Meal Plans index as uniform card grid with current-week badge
- Blog index and `[slug]` detail pages
- Contact and Privacy Policy pages
- `BaseLayout.astro` with full SEO meta (OG, Twitter Card, canonical, GA4 — production only)
- `RecipeLayout.astro` with JSON-LD `Recipe` schema (improvement over original site)
- `CategoryFilter.tsx` React island for client-side recipe filtering
- `NewsletterSignup.tsx` React island
- Sitemap via `@astrojs/sitemap`; `public/robots.txt` (allows AI crawlers, disallows `/contact`)
- Logo-derived warm chocolate-brown color palette (`#3D2B0F` primary, `#A06820` amber accent)
- GitHub Actions: `ci.yml` (build + type-check, Gitleaks, Trivy SCA, CodeQL SAST), `security.yml`, `dast.yml` (OWASP ZAP nightly), `seo-gate.yml` (Lighthouse SEO ≥ 0.90 / Perf ≥ 0.90, CLS ≤ 0.10, LCP ≤ 2500ms), `gsc-serposcope-sync.yml`
- Pre-commit / pre-push hooks via `scripts/ci/install-hooks.sh`
- Vercel deployment config: `main` → production, `preview` → preview URL
