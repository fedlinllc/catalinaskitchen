#!/usr/bin/env python3
"""
Scrape catalinaskitchen.com and extract all content + image URLs.

Output:
  scraped/content.json     — structured recipes, meal plans, blog posts, pages
  scraped/image_urls.txt   — deduplicated list of CDN image URLs to download

Usage:
  pip install playwright beautifulsoup4
  playwright install chromium
  python3 scripts/scrape.py
"""

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup
    from playwright.sync_api import sync_playwright, Page
except ImportError:
    print("Missing deps. Run: pip install playwright beautifulsoup4 && playwright install chromium")
    sys.exit(1)

BASE_URL = "https://www.catalinaskitchen.com"
OUTPUT_DIR = Path("scraped")
OUTPUT_DIR.mkdir(exist_ok=True)

image_urls: set[str] = set()

content: dict = {
    "recipes": [],
    "meal_plans": [],
    "blog_posts": [],
    "pages": [],
}

_playwright = None
_browser = None
_page: Page | None = None


def get_page() -> Page:
    global _playwright, _browser, _page
    if _page is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=True)
        _page = _browser.new_page(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
    return _page


def fetch(url: str) -> BeautifulSoup | None:
    page = get_page()
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
        # Extra wait for JS-rendered content
        page.wait_for_timeout(1500)
        html = page.content()
        return BeautifulSoup(html, "html.parser")
    except Exception as e:
        print(f"  WARN: failed to fetch {url}: {e}")
        return None


def close_browser() -> None:
    global _playwright, _browser, _page
    if _browser:
        _browser.close()
    if _playwright:
        _playwright.stop()
    _page = None
    _browser = None
    _playwright = None


def collect_images(soup: BeautifulSoup) -> None:
    cdn_hosts = ("images.squarespace-cdn.com", "static1.squarespace.com")

    for tag in soup.find_all("img"):
        for attr in ("src", "data-src", "data-image"):
            val = tag.get(attr, "")
            if any(h in val for h in cdn_hosts):
                clean = val.split("?")[0]
                if clean:
                    image_urls.add(clean)

        for attr in ("srcset", "data-srcset"):
            srcset = tag.get(attr, "")
            for part in srcset.split(","):
                parts = part.strip().split()
                if not parts:
                    continue
                val = parts[0]
                if any(h in val for h in cdn_hosts):
                    clean = val.split("?")[0]
                    if clean:
                        image_urls.add(clean)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def get_jsonld(soup: BeautifulSoup) -> dict:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, dict) and "datePublished" in data:
                return data
        except Exception:
            pass
    return {}


def extract_hero_image(soup: BeautifulSoup) -> str | None:
    cdn_host = "images.squarespace-cdn.com"
    space_prefix = re.compile(r"images\.squarespace-cdn\.com/content/v1/[^/]+/[^/]+/")

    for tag in soup.find_all("img"):
        for attr in ("data-src", "data-image", "src"):
            val = tag.get(attr, "")
            if cdn_host in val and "Logo" not in val and space_prefix.search(val):
                return val.split("?")[0]
    return None


def extract_category(soup: BeautifulSoup) -> str | None:
    el = soup.select_one(".blog-meta-item--categories, .blog-item-category-wrapper")
    if el:
        return clean_text(el.get_text())
    return None


def extract_tags(soup: BeautifulSoup) -> list[str]:
    tags = []
    for el in soup.select(".blog-item-tag"):
        t = clean_text(el.get_text())
        if t:
            tags.append(t)
    return tags


def extract_full_date(soup: BeautifulSoup) -> str:
    ld = get_jsonld(soup)
    if ld.get("datePublished"):
        return ld["datePublished"][:10]
    el = soup.select_one(".dt-published, time")
    if el:
        dt = el.get("datetime") or el.get_text(strip=True)
        if re.match(r"\d{4}-\d{2}-\d{2}", dt):
            return dt[:10]
    return ""


def extract_excerpt(soup: BeautifulSoup, jsonld: dict) -> str:
    og = soup.find("meta", property="og:description")
    if og and og.get("content"):
        return clean_text(og["content"])
    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        return clean_text(desc["content"])
    return ""


def scrape_post(url: str) -> dict | None:
    soup = fetch(url)
    if not soup:
        return None
    collect_images(soup)

    jsonld = get_jsonld(soup)

    title = clean_text(jsonld.get("headline") or "")
    if not title:
        h1 = soup.find("h1")
        title = clean_text(h1.get_text()) if h1 else ""

    date_str = extract_full_date(soup)
    category = extract_category(soup)
    tags = extract_tags(soup)
    hero_image = extract_hero_image(soup)
    excerpt = extract_excerpt(soup, jsonld)

    content_el = soup.select_one(".blog-item-content")
    body_html = str(content_el) if content_el else ""
    body_text = clean_text(content_el.get_text(" ")) if content_el else ""

    slug = urlparse(url).path.rstrip("/").split("/")[-1]

    return {
        "url": url,
        "slug": slug,
        "title": title,
        "published_date": date_str,
        "category": category,
        "tags": tags,
        "hero_image_url": hero_image,
        "excerpt": excerpt,
        "body_html": body_html,
        "body_text": body_text,
    }


def scrape_static_page(url: str, page_id: str) -> dict | None:
    soup = fetch(url)
    if not soup:
        return None
    collect_images(soup)

    h1 = soup.find("h1")
    title = clean_text(h1.get_text()) if h1 else page_id

    main = soup.select_one("main, #page, .page-section")
    body_html = str(main) if main else ""
    body_text = clean_text(main.get_text(" ")) if main else ""

    return {
        "url": url,
        "page_id": page_id,
        "title": title,
        "body_html": body_html,
        "body_text": body_text,
    }


def discover_post_urls(soup: BeautifulSoup, base: str) -> list[str]:
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base, href)
        parsed = urlparse(full)
        if parsed.netloc not in ("www.catalinaskitchen.com", "catalinaskitchen.com"):
            continue
        path = parsed.path.rstrip("/")
        if re.match(r"^/blog/[^/]+$", path) and not path.startswith("/blog/category"):
            urls.append(full.split("?")[0].split("#")[0])
    return list(set(urls))


def discover_meal_plan_urls(soup: BeautifulSoup, base: str) -> list[str]:
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base, href)
        parsed = urlparse(full)
        if parsed.netloc not in ("www.catalinaskitchen.com", "catalinaskitchen.com"):
            continue
        path = parsed.path.rstrip("/")
        if re.match(r"^/meal-plans/[^/]+$", path):
            urls.append(full.split("?")[0].split("#")[0])
    return list(set(urls))


def get_next_page_url(soup: BeautifulSoup, current_url: str) -> str | None:
    for a in soup.find_all("a", href=True):
        text = clean_text(a.get_text()).lower()
        if text in ("older posts", "next", "next page"):
            return urljoin(current_url, a["href"])
    return None


def classify_post(item: dict) -> str:
    slug = item.get("slug", "").lower()
    tags = [t.lower() for t in item.get("tags", [])]
    category = (item.get("category") or "").lower()

    if "meal-plan" in slug or "mealplan" in slug or "meal plan" in " ".join(tags):
        return "meal_plans"
    if "recipe" in category or any(t in tags for t in ("dinner", "breakfast", "dessert", "sides", "sauce", "salsa", "lunch")):
        return "recipes"
    return "blog_posts"


def main() -> None:
    print("=== Catalina's Kitchen Scraper (Playwright) ===\n")

    try:
        # ── Static pages ──────────────────────────────────────────────────────
        static_pages = [
            ("https://www.catalinaskitchen.com", "home"),
            ("https://www.catalinaskitchen.com/recipes", "recipes-index"),
            ("https://www.catalinaskitchen.com/contact", "contact"),
            ("https://www.catalinaskitchen.com/privacy-policy", "privacy-policy"),
        ]
        print("[1/4] Scraping static pages...")
        for url, page_id in static_pages:
            print(f"  {url}")
            page = scrape_static_page(url, page_id)
            if page:
                content["pages"].append(page)

        # ── Discover blog post URLs ───────────────────────────────────────────
        print("\n[2/4] Discovering blog post URLs...")
        all_post_urls: set[str] = set()
        visited: set[str] = set()

        for index_url in [
            "https://www.catalinaskitchen.com/blog",
            "https://www.catalinaskitchen.com/blog-1",
        ]:
            current_url: str | None = index_url
            while current_url:
                if current_url in visited:
                    break
                visited.add(current_url)
                soup = fetch(current_url)
                if not soup:
                    break
                found = discover_post_urls(soup, current_url)
                new = set(found) - all_post_urls
                print(f"  {current_url} → {len(new)} new post URLs")
                all_post_urls.update(found)
                current_url = get_next_page_url(soup, current_url)

        print(f"  Total blog URLs: {len(all_post_urls)}")

        # ── Discover meal plan URLs ───────────────────────────────────────────
        print("\n[3/4] Discovering meal plan URLs...")
        meal_plan_urls: set[str] = set()
        for mp_url in [
            "https://www.catalinaskitchen.com/meal-plans",
            "https://www.catalinaskitchen.com/meal-plans/current",
            "https://www.catalinaskitchen.com/meal-plans/previous",
        ]:
            soup = fetch(mp_url)
            if soup:
                collect_images(soup)
                found = discover_meal_plan_urls(soup, mp_url)
                new = set(found) - meal_plan_urls
                print(f"  {mp_url} → {len(new)} meal plan URLs")
                meal_plan_urls.update(found)

        print(f"  Total meal plan URLs: {len(meal_plan_urls)}")

        # ── Scrape each post ──────────────────────────────────────────────────
        all_urls = sorted(all_post_urls | meal_plan_urls)
        print(f"\n[4/4] Scraping {len(all_urls)} posts...")
        for url in all_urls:
            print(f"  {url}")
            item = scrape_post(url)
            if not item:
                continue
            # Force meal plan classification for /meal-plans/ URLs
            if "/meal-plans/" in url:
                bucket = "meal_plans"
            else:
                bucket = classify_post(item)
            content[bucket].append(item)

    finally:
        close_browser()

    # ── Write outputs ─────────────────────────────────────────────────────────
    print("\nWriting output files...")

    content_file = OUTPUT_DIR / "content.json"
    with open(content_file, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in content.values())
    print(f"  {content_file}  ({total} total items)")

    image_file = OUTPUT_DIR / "image_urls.txt"
    with open(image_file, "w", encoding="utf-8") as f:
        for url in sorted(image_urls):
            f.write(url + "\n")
    print(f"  {image_file}  ({len(image_urls)} images)")

    print("\n=== Done ===")
    print(f"  Recipes:    {len(content['recipes'])}")
    print(f"  Meal plans: {len(content['meal_plans'])}")
    print(f"  Blog posts: {len(content['blog_posts'])}")
    print(f"  Pages:      {len(content['pages'])}")
    print(f"  Images:     {len(image_urls)}")


if __name__ == "__main__":
    main()
