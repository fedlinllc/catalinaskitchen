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

import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path

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
    items = env.entries().all({"content_type": content_type, "fields.slug[en-US]": slug})
    return len(items) > 0


def upload_image(image_path: Path, title: str) -> str | None:
    """Upload a local image and return its asset ID, or None on failure."""
    if not image_path.exists():
        return None
    mime, _ = mimetypes.guess_type(str(image_path))
    mime = mime or "image/jpeg"
    try:
        with open(image_path, "rb") as f:
            upload = env.uploads().create(f)
        asset_attrs = {
            "fields": {
                "title": {"en-US": title},
                "file": {
                    "en-US": {
                        "fileName": image_path.name,
                        "contentType": mime,
                        "uploadFrom": {
                            "sys": {"type": "Link", "linkType": "Upload", "id": upload.id}
                        },
                    }
                },
            }
        }
        asset = env.assets().create(None, asset_attrs)
        asset.process()
        time.sleep(2)
        asset = env.assets().find(asset.id)
        asset.publish()
        print(f"    Uploaded asset: {image_path.name} → {asset.id}")
        return asset.id
    except Exception as e:
        print(f"    WARN: failed to upload {image_path}: {e}")
        return None


def html_to_contentful_richtext(html: str) -> dict:
    """Convert raw HTML to a minimal Contentful RichText document."""
    from html.parser import HTMLParser

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.nodes: list[dict] = []
            self._current_text: list[str] = []
            self._in_block = False

        def _flush(self):
            text = "".join(self._current_text).strip()
            if text:
                self.nodes.append({
                    "nodeType": "paragraph",
                    "data": {},
                    "content": [{"nodeType": "text", "value": text, "marks": [], "data": {}}],
                })
            self._current_text = []

        def handle_data(self, data):
            self._current_text.append(data)

        def handle_endtag(self, tag):
            if tag in ("p", "li", "h2", "h3", "br"):
                self._flush()

        def get_document(self):
            self._flush()
            return {
                "nodeType": "document",
                "data": {},
                "content": self.nodes or [{
                    "nodeType": "paragraph",
                    "data": {},
                    "content": [{"nodeType": "text", "value": "", "marks": [], "data": {}}],
                }],
            }

    parser = _Parser()
    parser.feed(html)
    return parser.get_document()


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

def ensure_author(name: str = "Jaime Esquivel") -> str:
    items = env.entries().all({"content_type": "author", "fields.name[en-US]": name})
    if items:
        return items[0].id
    entry = env.entries().create(None, {
        "content_type_id": "author",
        "fields": {"name": {"en-US": name}},
    })
    entry.publish()
    print(f"  + Author created: {name} → {entry.id}")
    return entry.id


def import_recipes(recipes: list, author_id: str) -> None:
    print(f"\nImporting {len(recipes)} recipes...")
    for item in recipes:
        slug = slugify(item.get("slug") or item.get("title", "untitled"))
        if entry_exists("recipe", slug):
            print(f"  ✓ skip (exists): {slug}")
            continue

        img_path = image_path_for_url(item.get("hero_image_url", ""))
        asset_id = upload_image(img_path, item.get("title", slug)) if img_path else None

        body_html = item.get("body_html", "")
        ingredients_doc = html_to_contentful_richtext(body_html)
        instructions_doc = html_to_contentful_richtext(body_html)

        category = (item.get("category") or "").lower()
        if category not in ("dinner", "sides", "sauces", "breakfast", "dessert"):
            category = "dinner"

        date_str = item.get("published_date", "")
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            date_str = "2024-01-01"
        else:
            date_str = date_str[:10]

        fields: dict = {
            "title":         {"en-US": item.get("title", slug)},
            "slug":          {"en-US": slug},
            "excerpt":       {"en-US": item.get("excerpt", "")},
            "category":      {"en-US": category},
            "publishedDate": {"en-US": date_str},
            "ingredients":   {"en-US": ingredients_doc},
            "instructions":  {"en-US": instructions_doc},
            "tags":          {"en-US": item.get("tags", [])},
        }
        if asset_id:
            fields["featuredImage"] = {"en-US": {"sys": {"type": "Link", "linkType": "Asset", "id": asset_id}}}
        if author_id:
            fields["author"] = {"en-US": {"sys": {"type": "Link", "linkType": "Entry", "id": author_id}}}

        try:
            entry = env.entries().create(None, {"content_type_id": "recipe", "fields": fields})
            entry.publish()
            print(f"  + {slug}")
        except Exception as e:
            print(f"  WARN: failed to create recipe {slug}: {e}")
        time.sleep(0.5)


def import_meal_plans(plans: list) -> None:
    print(f"\nImporting {len(plans)} meal plans...")
    for item in plans:
        slug = slugify(item.get("slug") or item.get("title", "meal-plan"))
        if entry_exists("mealPlan", slug):
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
            "title":    {"en-US": item.get("title", slug)},
            "slug":     {"en-US": slug},
            "weekOf":   {"en-US": date_str},
            "isCurrent": {"en-US": False},
            "content":  {"en-US": content_doc},
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

    author_id = ensure_author("Jaime Esquivel")

    import_recipes(scraped.get("recipes", []), author_id)
    import_meal_plans(scraped.get("meal_plans", []))
    import_blog_posts(scraped.get("blog_posts", []))

    print("\n=== Import complete ===")


if __name__ == "__main__":
    main()
