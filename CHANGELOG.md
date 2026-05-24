# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] — 2026-05-24

### Added
- `scripts/fix_recipe_fields.py` — one-shot Contentful repair script: splits every recipe entry's combined `ingredients`/`instructions` rich-text blob into separate fields, then sentence-splits instruction paragraphs into discrete ordered-list steps; idempotent and safe to re-run
- Gradient hero section (`from-[#e7d9cb] to-white`) with category pill badge, back-link, and author/date strip on all three detail page types (recipe, blog, meal plan)
- Author card (initial avatar + bio) and "Hungry for more?" CTA block on blog detail pages
- "Browse Recipes / Meal Plans" navigation footer on meal-plan detail pages

### Changed
- `RecipeLayout.astro` — removed `grid md:grid-cols-2` two-column layout (caused all content to appear doubled); ingredients now render in a warm `#f2ece4` card with custom dot bullets; instructions render as numbered step circles via CSS counter on `ordered-list` items
- `blog/[slug].astro` and `meal-plans/[slug].astro` — redesigned with gradient hero matching recipe pages; replaced plain `← Back` text link with styled nav
- `global.css` `.prose-catalina` — removed invalid `:global()` wrappers (selectors were silently dropped by the browser, meaning no rich-text styles ever applied); expanded coverage to `h2`–`h4`, `p`, `a`, `ul`/`ol`/`li`, `strong`, `em`, `blockquote`, `hr`, `img`, `table`/`th`/`td`, `code`, `pre`
- `prose-catalina h2` — bumped to `1.75rem`, added `2px solid` bottom border for section-break clarity
- `prose-catalina h3`/`h4` — bumped to `1.375rem`/`1.125rem`, `font-weight: 700`
- `prose-catalina p` — `margin-bottom` increased from `1.25rem` to `1.75rem` for clear paragraph separation
- `scripts/import_to_contentful.py` — fixed `import_recipes()` to properly split `ingredients` (unordered-list) and `instructions` (ordered-list with sentence-boundary step splitting) instead of writing the same document to both fields

### Fixed
- Recipe pages: all content was rendered twice due to both the two-column grid layout and identical Contentful field data — both root causes resolved
- `prose-catalina` typography styles were never applied due to `:global()` being invalid CSS outside Astro `<style>` blocks
- 23 of 24 published recipe entries in Contentful had instruction steps collapsed into single paragraphs; all split into discrete numbered steps

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
