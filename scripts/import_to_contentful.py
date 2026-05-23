#!/usr/bin/env python3
"""
Import scraped content into Contentful via the Management API.

Creates content types, uploads images, and publishes entries for:
  - author
  - recipe
  - mealPlan
  - blogPost

Prerequisites:
  pip install contentful-management python-slugify
  export CONTENTFUL_SPACE_ID=...
  export CONTENTFUL_MANAGEMENT_TOKEN=...   (Settings → API keys → Content management tokens)
  export CONTENTFUL_ENVIRONMENT=master

Run AFTER scrape.py and download_images.sh:
  python3 scripts/import_to_contentful.py

The script is idempotent — re-running will skip entries whose slug already exists.
"""

import html as html_lib
import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

# Load .env from repo root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import contentful_management
except ImportError:
    print("Missing deps. Run: pip install contentful-management")
    sys.exit(1)

try:
    from slugify import slugify
except ImportError:
    def slugify(text: str) -> str:
        text = re.sub(r"[^\w\s-]", "", text.lower())
        return re.sub(r"[-\s]+", "-", text).strip("-")

# ── Config ────────────────────────────────────────────────────────────────────

SPACE_ID = os.environ.get("CONTENTFUL_SPACE_ID", "")
MGMT_TOKEN = os.environ.get("CONTENTFUL_MANAGEMENT_TOKEN", "")
ENVIRONMENT = os.environ.get("CONTENTFUL_ENVIRONMENT", "master")
SCRAPED_FILE = Path("scraped/content.json")
IMAGES_DIR = Path("public/images")

if not SPACE_ID or not MGMT_TOKEN:
    print("ERROR: Set CONTENTFUL_SPACE_ID and CONTENTFUL_MANAGEMENT_TOKEN env vars.")
    sys.exit(1)

client = contentful_management.Client(MGMT_TOKEN)
space = client.spaces().find(SPACE_ID)
env = space.environments().find(ENVIRONMENT)

# ── Helpers ───────────────────────────────────────────────────────────────────

def entry_exists(content_type: str, slug: str) -> bool:
    items = env.entries().all({"content_type": content_type, "fields.slug": slug})
    return len(items) > 0


def create_asset_from_url(url: str, title: str) -> str | None:
    """Create a Contentful asset from a CDN URL and return its asset ID."""
    if not url:
        return None
    filename = url.rstrip("/").split("/")[-1].split("?")[0]
    mime, _ = mimetypes.guess_type(filename)
    mime = mime or "image/jpeg"
    try:
        asset_attrs = {
            "fields": {
                "title": {"en-US": title},
                "file": {
                    "en-US": {
                        "fileName": filename,
                        "contentType": mime,
                        "upload": url,
                    }
                },
            }
        }
        asset = env.assets().create(None, asset_attrs)
        asset.process()
        time.sleep(3)
        asset = env.assets().find(asset.id)
        asset.publish()
        print(f"    Asset: {filename} → {asset.id}")
        return asset.id
    except Exception as e:
        print(f"    WARN: failed to create asset from {url}: {e}")
        return None


def html_to_contentful_richtext(raw_html: str) -> dict:
    """Convert raw HTML to a Contentful RichText document, stripping Squarespace junk."""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    HEADING_MAP = {
        "h1": "heading-1", "h2": "heading-2", "h3": "heading-3",
        "h4": "heading-4", "h5": "heading-5", "h6": "heading-6",
    }
    CONTAINERS = {"div", "section", "article", "main", "header", "footer",
                  "figure", "blockquote", "form", "nav", "aside"}

    def text_node(value: str) -> dict:
        return {"nodeType": "text", "value": value.strip(), "marks": [], "data": {}}

    def para(text: str) -> dict:
        return {"nodeType": "paragraph", "data": {}, "content": [text_node(text)]}

    nodes: list[dict] = []

    def process(el) -> None:
        for child in el.children:
            if not hasattr(child, "name") or child.name is None:
                continue
            name = child.name.lower()
            if name in HEADING_MAP:
                text = child.get_text(" ", strip=True)
                if text:
                    nodes.append({"nodeType": HEADING_MAP[name], "data": {},
                                  "content": [text_node(text)]})
            elif name == "p":
                text = child.get_text(" ", strip=True)
                if text:
                    nodes.append(para(text))
            elif name in ("ul", "ol"):
                list_type = "unordered-list" if name == "ul" else "ordered-list"
                items = []
                for li in child.find_all("li", recursive=False):
                    li_text = li.get_text(" ", strip=True)
                    if li_text:
                        items.append({"nodeType": "list-item", "data": {},
                                      "content": [para(li_text)]})
                if items:
                    nodes.append({"nodeType": list_type, "data": {}, "content": items})
            elif name in CONTAINERS:
                process(child)

    process(soup)

    return {
        "nodeType": "document",
        "data": {},
        "content": nodes or [para("")],
    }


def image_path_for_url(url: str) -> Path | None:
    if not url:
        return None
    raw_name = url.rstrip("/").split("/")[-1].split("?")[0]
    try:
        from urllib.parse import unquote
        name = unquote(raw_name)
        name = re.sub(r"[^A-Za-z0-9._-]", "-", name)
        name = re.sub(r"-{2,}", "-", name).strip("-").lower()
    except Exception:
        name = raw_name
    p = IMAGES_DIR / name
    return p if p.exists() else None


# ── Content-type creation ─────────────────────────────────────────────────────

CONTENT_TYPES = {
    "author": {
        "name": "Author",
        "fields": [
            {"id": "name",  "name": "Name",  "type": "Symbol",  "required": True},
            {"id": "bio",   "name": "Bio",   "type": "Text",    "required": False},
            {"id": "photo", "name": "Photo", "type": "Link",    "required": False, "linkType": "Asset"},
        ],
        "displayField": "name",
    },
    "recipe": {
        "name": "Recipe",
        "fields": [
            {"id": "title",         "name": "Title",          "type": "Symbol",   "required": True},
            {"id": "slug",          "name": "Slug",           "type": "Symbol",   "required": True},
            {"id": "excerpt",       "name": "Excerpt",        "type": "Text",     "required": False},
            {"id": "category",      "name": "Category",       "type": "Symbol",   "required": True},
            {"id": "publishedDate", "name": "Published Date", "type": "Date",     "required": True},
            {"id": "featuredImage", "name": "Featured Image", "type": "Link",     "required": False, "linkType": "Asset"},
            {"id": "ingredients",   "name": "Ingredients",    "type": "RichText", "required": True},
            {"id": "instructions",  "name": "Instructions",   "type": "RichText", "required": True},
            {"id": "tags",          "name": "Tags",           "type": "Array",    "required": False, "items": {"type": "Symbol"}},
        ],
        "displayField": "title",
    },
    "mealPlan": {
        "name": "Meal Plan",
        "fields": [
            {"id": "title",         "name": "Title",          "type": "Symbol",   "required": True},
            {"id": "slug",          "name": "Slug",           "type": "Symbol",   "required": True},
            {"id": "weekOf",        "name": "Week Of",        "type": "Date",     "required": True},
            {"id": "isCurrent",     "name": "Is Current",     "type": "Boolean",  "required": True},
            {"id": "content",       "name": "Content",        "type": "RichText", "required": True},
            {"id": "featuredImage", "name": "Featured Image", "type": "Link",     "required": False, "linkType": "Asset"},
        ],
        "displayField": "title",
    },
    "blogPost": {
        "name": "Blog Post",
        "fields": [
            {"id": "title",         "name": "Title",          "type": "Symbol",   "required": True},
            {"id": "slug",          "name": "Slug",           "type": "Symbol",   "required": True},
            {"id": "excerpt",       "name": "Excerpt",        "type": "Text",     "required": False},
            {"id": "publishedDate", "name": "Published Date", "type": "Date",     "required": True},
            {"id": "featuredImage", "name": "Featured Image", "type": "Link",     "required": False, "linkType": "Asset"},
            {"id": "content",       "name": "Content",        "type": "RichText", "required": True},
            {"id": "tags",          "name": "Tags",           "type": "Array",    "required": False, "items": {"type": "Symbol"}},
        ],
        "displayField": "title",
    },
}


def ensure_content_types() -> None:
    print("Ensuring content types exist...")
    existing = {ct.id for ct in env.content_types().all()}
    for ct_id, ct_def in CONTENT_TYPES.items():
        if ct_id in existing:
            print(f"  ✓ {ct_id} (exists)")
            continue
        fields = []
        for f in ct_def["fields"]:
            field: dict = {"id": f["id"], "name": f["name"], "type": f["type"], "required": f.get("required", False), "localized": False}
            if f["type"] == "Link":
                field["linkType"] = f.get("linkType", "Entry")
            if f["type"] == "Array":
                field["items"] = f.get("items", {"type": "Symbol"})
            fields.append(field)
        ct = env.content_types().create(ct_id, {"name": ct_def["name"], "fields": fields, "displayField": ct_def["displayField"]})
        ct.publish()
        print(f"  + {ct_id} created")
        time.sleep(0.5)


# ── Import ────────────────────────────────────────────────────────────────────

def ensure_author(name: str = "Katelyn Esquivel") -> str:
    items = env.entries().all({"content_type": "author", "fields.name": name})
    if items:
        return items[0].id
    entry = env.entries().create(None, {
        "content_type_id": "author",
        "fields": {"name": {"en-US": name}},
    })
    entry.publish()
    print(f"  + Author created: {name} → {entry.id}")
    return entry.id


def category_from_tags(tags: list[str]) -> str:
    tl = [t.lower() for t in tags]
    if any(t in tl for t in ("sauces", "salsas", "sauce", "salsa")):
        return "sauces"
    if "breakfast" in tl:
        return "breakfast"
    if "dessert" in tl:
        return "dessert"
    if any(t in tl for t in ("sides", "side")):
        return "sides"
    return "dinner"


def floor_date(date_str: str, minimum: str = "2024-01-01") -> str:
    if not re.match(r"\d{4}-\d{2}-\d{2}", date_str or ""):
        return minimum
    return date_str[:10] if date_str[:10] >= minimum else minimum


def delete_all_of_type(content_type: str) -> None:
    print(f"  Deleting existing {content_type} entries...")
    try:
        items = env.entries().all({"content_type": content_type, "limit": 1000})
    except Exception:
        return
    for item in items:
        try:
            try:
                item.unpublish()
            except Exception:
                pass
            item.delete()
        except Exception as e:
            print(f"    WARN: could not delete {item.id}: {e}")


def import_recipes(recipes: list, author_id: str) -> None:
    delete_all_of_type("recipe")
    print(f"\nImporting {len(recipes)} recipes...")
    for item in recipes:
        slug = slugify(item.get("slug") or item.get("title", "untitled"))

        hero_url = item.get("hero_image_url", "")
        asset_id = create_asset_from_url(hero_url, item.get("title", slug)) if hero_url else None

        body_html = item.get("body_html", "")
        ingredients_doc = html_to_contentful_richtext(body_html)
        instructions_doc = html_to_contentful_richtext(body_html)

        category = category_from_tags(item.get("tags", []))
        date_str = floor_date(item.get("published_date", ""))
        title = html_lib.unescape(item.get("title") or slug)
        excerpt = html_lib.unescape(item.get("excerpt") or "")
        # Strip excerpts that are just the ingredient list dumped by Squarespace meta
        if excerpt.lower().startswith("ingredients"):
            excerpt = ""

        fields: dict = {
            "title":         {"en-US": title},
            "slug":          {"en-US": slug},
            "excerpt":       {"en-US": excerpt},
            "category":      {"en-US": category},
            "publishedDate": {"en-US": date_str},
            "ingredients":   {"en-US": ingredients_doc},
            "instructions":  {"en-US": instructions_doc},
            "tags":          {"en-US": item.get("tags", [])},
        }
        if asset_id:
            fields["featuredImage"] = {"en-US": {"sys": {"type": "Link", "linkType": "Asset", "id": asset_id}}}

        try:
            entry = env.entries().create(None, {"content_type_id": "recipe", "fields": fields})
            entry.publish()
            print(f"  + {slug} [{category}]")
        except Exception as e:
            print(f"  WARN: failed to create recipe {slug}: {e}")
        time.sleep(0.5)


def import_meal_plans(plans: list) -> None:
    delete_all_of_type("mealPlan")
    print(f"\nImporting {len(plans)} meal plans...")
    for item in plans:
        slug = slugify(item.get("slug") or item.get("title", "meal-plan"))

        hero_url = item.get("hero_image_url", "")
        asset_id = create_asset_from_url(hero_url, item.get("title", slug)) if hero_url else None

        content_doc = html_to_contentful_richtext(item.get("body_html", ""))

        date_str = floor_date(item.get("published_date", ""))
        title = html_lib.unescape(item.get("title") or slug)

        fields: dict = {
            "title":     {"en-US": title},
            "slug":      {"en-US": slug},
            "weekOf":    {"en-US": date_str},
            "isCurrent": {"en-US": False},
            "content":   {"en-US": content_doc},
        }
        if asset_id:
            fields["featuredImage"] = {"en-US": {"sys": {"type": "Link", "linkType": "Asset", "id": asset_id}}}

        try:
            entry = env.entries().create(None, {"content_type_id": "mealPlan", "fields": fields})
            entry.publish()
            print(f"  + {slug}")
        except Exception as e:
            print(f"  WARN: failed to create meal plan {slug}: {e}")
        time.sleep(0.5)


def import_blog_posts(posts: list) -> None:
    print(f"\nImporting {len(posts)} blog posts...")
    for item in posts:
        slug = slugify(item.get("slug") or item.get("title", "post"))
        if entry_exists("blogPost", slug):
            print(f"  ✓ skip (exists): {slug}")
            continue

        img_path = image_path_for_url(item.get("hero_image_url", ""))
        asset_id = upload_image(img_path, item.get("title", slug)) if img_path else None

        content_doc = html_to_contentful_richtext(item.get("body_html", ""))

        date_str = item.get("published_date", "2024-01-01")
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            date_str = "2024-01-01"
        else:
            date_str = date_str[:10]

        fields: dict = {
            "title":         {"en-US": item.get("title", slug)},
            "slug":          {"en-US": slug},
            "excerpt":       {"en-US": item.get("excerpt", "")},
            "publishedDate": {"en-US": date_str},
            "content":       {"en-US": content_doc},
            "tags":          {"en-US": item.get("tags", [])},
        }
        if asset_id:
            fields["featuredImage"] = {"en-US": {"sys": {"type": "Link", "linkType": "Asset", "id": asset_id}}}

        try:
            entry = env.entries().create(None, {"content_type_id": "blogPost", "fields": fields})
            entry.publish()
            print(f"  + {slug}")
        except Exception as e:
            print(f"  WARN: failed to create blog post {slug}: {e}")
        time.sleep(0.5)


def main() -> None:
    print("=== Contentful Import ===\n")

    if not SCRAPED_FILE.exists():
        print(f"ERROR: {SCRAPED_FILE} not found. Run scripts/scrape.py first.")
        sys.exit(1)

    with open(SCRAPED_FILE, encoding="utf-8") as f:
        scraped = json.load(f)

    ensure_content_types()

    author_id = ensure_author("Katelyn Esquivel")

    import_recipes(scraped.get("recipes", []), author_id)
    import_meal_plans(scraped.get("meal_plans", []))
    import_blog_posts(scraped.get("blog_posts", []))

    print("\n=== Import complete ===")


if __name__ == "__main__":
    main()
