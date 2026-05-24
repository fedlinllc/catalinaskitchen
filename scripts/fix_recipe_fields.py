#!/usr/bin/env python3
"""
Fix recipes in Contentful where `ingredients` and `instructions` both contain
the full recipe body (same document), and/or where instruction steps are not
split into individual ordered-list items.

Split strategy:
  ingredients  → unordered-list nodes only
  instructions → ordered-list, one item per sentence/step
                 (enables the numbered-step CSS in RecipeLayout.astro)

Safe to re-run — already-correct entries are skipped.
"""

import os
import re
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("Missing dep: pip install requests")
    sys.exit(1)

SPACE_ID    = os.environ.get("CONTENTFUL_SPACE_ID", "")
MGMT_TOKEN  = os.environ.get("CONTENTFUL_MANAGEMENT_TOKEN", "")
ENVIRONMENT = os.environ.get("CONTENTFUL_ENVIRONMENT", "master")

if not SPACE_ID or not MGMT_TOKEN:
    print("ERROR: set CONTENTFUL_SPACE_ID and CONTENTFUL_MANAGEMENT_TOKEN")
    sys.exit(1)

BASE = f"https://api.contentful.com/spaces/{SPACE_ID}/environments/{ENVIRONMENT}"
HEADERS = {
    "Authorization": f"Bearer {MGMT_TOKEN}",
    "Content-Type": "application/vnd.contentful.management.v1+json",
}


def api_get(path: str) -> dict:
    r = requests.get(f"{BASE}{path}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def api_put(path: str, body: dict, version: int) -> dict:
    h = {**HEADERS, "X-Contentful-Version": str(version)}
    r = requests.put(f"{BASE}{path}", json=body, headers=h)
    r.raise_for_status()
    return r.json()


def api_put_action(path: str, version: int) -> dict:
    h = {**HEADERS, "X-Contentful-Version": str(version)}
    r = requests.put(f"{BASE}{path}", headers=h)
    r.raise_for_status()
    return r.json()


# ── Step splitter ──────────────────────────────────────────────────────────────

def split_into_steps(text: str) -> list[str]:
    """
    Split a long instruction paragraph into individual steps.

    Splits on '. ' followed by a capital letter, using a lookbehind on
    lowercase/digit to avoid splitting on mid-sentence abbreviations like
    "add 1/2 c. Butter" (unlikely) while correctly splitting steps like
    "Grill 4 min. Remove from heat."
    """
    if len(text) < 60:
        return [text]

    # Split: period + space + uppercase, preceded by lowercase letter or digit
    parts = re.split(r'(?<=[a-z\d,\)])\. (?=[A-Z])', text)
    parts = [p.strip() for p in parts if p.strip()]

    # Re-attach the period lost to each part except the last
    result = []
    for i, p in enumerate(parts):
        if i < len(parts) - 1 and not p[-1] in ".!?":
            p += "."
        result.append(p)

    return result if len(result) > 1 else [text]


def make_para_node(text: str) -> dict:
    return {
        "nodeType": "paragraph", "data": {},
        "content": [{"nodeType": "text", "value": text, "marks": [], "data": {}}],
    }


def make_ol_from_texts(texts: list[str]) -> dict:
    return {
        "nodeType": "document", "data": {},
        "content": [{
            "nodeType": "ordered-list", "data": {},
            "content": [
                {"nodeType": "list-item", "data": {}, "content": [make_para_node(t)]}
                for t in texts
            ],
        }],
    }


def empty_doc() -> dict:
    return {"nodeType": "document", "data": {}, "content": [make_para_node("")]}


# ── Document analysis ──────────────────────────────────────────────────────────

def extract_ingredient_texts(doc: dict) -> list[str]:
    """Collect all text from unordered-list nodes."""
    out = []
    for node in doc.get("content", []):
        if node.get("nodeType") == "unordered-list":
            for item in node.get("content", []):
                text = "".join(
                    t.get("value", "")
                    for para in item.get("content", [])
                    for t in para.get("content", [])
                    if t.get("nodeType") == "text"
                ).strip()
                if text:
                    out.append(text)
    return out


def extract_instruction_texts(doc: dict) -> list[str]:
    """
    Collect all instruction text — from paragraph nodes OR existing ordered-list
    items — then split each at sentence boundaries.
    """
    raw: list[str] = []

    for node in doc.get("content", []):
        nt = node.get("nodeType", "")

        if nt == "paragraph":
            text = "".join(
                t.get("value", "")
                for t in node.get("content", [])
                if t.get("nodeType") == "text"
            ).strip()
            if text:
                raw.append(text)

        elif nt == "ordered-list":
            for item in node.get("content", []):
                text = "".join(
                    t.get("value", "")
                    for para in item.get("content", [])
                    for t in para.get("content", [])
                    if t.get("nodeType") == "text"
                ).strip()
                if text:
                    raw.append(text)

    # Expand each collected text into individual steps
    steps: list[str] = []
    for text in raw:
        steps.extend(split_into_steps(text))

    return steps


def needs_update(ing_doc: dict, inst_doc: dict) -> bool:
    """Return True if this entry still needs to be fixed or has long unsplit steps."""
    ing_types  = [n.get("nodeType") for n in ing_doc.get("content", [])]
    inst_types = [n.get("nodeType") for n in inst_doc.get("content", [])]

    # Still combined (original bug)
    if ing_types == inst_types:
        return True

    # Instructions exist but have items that could be further split
    for node in inst_doc.get("content", []):
        if node.get("nodeType") == "ordered-list":
            for item in node.get("content", []):
                text = "".join(
                    t.get("value", "")
                    for para in item.get("content", [])
                    for t in para.get("content", [])
                    if t.get("nodeType") == "text"
                ).strip()
                if len(split_into_steps(text)) > 1:
                    return True

    return False


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== fix_recipe_fields.py ===\n")

    entries = []
    skip, limit = 0, 100
    while True:
        data = api_get(f"/entries?content_type=recipe&limit={limit}&skip={skip}")
        entries.extend(data["items"])
        if skip + limit >= data["total"]:
            break
        skip += limit

    print(f"Found {len(entries)} recipe entries\n")

    fixed = skipped = errors = 0

    for entry in entries:
        entry_id = entry["sys"]["id"]
        version  = entry["sys"]["version"]
        fields   = entry.get("fields", {})
        title    = fields.get("title", {}).get("en-US", entry_id)

        ing_doc  = fields.get("ingredients",  {}).get("en-US", {})
        inst_doc = fields.get("instructions", {}).get("en-US", {})

        if not needs_update(ing_doc, inst_doc):
            print(f"  skip  {title!r}")
            skipped += 1
            continue

        # Rebuild from the combined doc (ingredients field has both if not yet split)
        source_doc = ing_doc  # still contains everything when combined
        ing_texts  = extract_ingredient_texts(source_doc)
        inst_texts = extract_instruction_texts(source_doc)

        # If already structurally split, use the inst_doc for steps
        ing_types = [n.get("nodeType") for n in ing_doc.get("content", [])]
        inst_types = [n.get("nodeType") for n in inst_doc.get("content", [])]
        if ing_types != inst_types:
            # Already split structurally — re-extract steps from inst_doc with splitting
            inst_texts = extract_instruction_texts(inst_doc)

        # Build new documents
        new_ing: dict
        if ing_texts:
            new_ing = {
                "nodeType": "document", "data": {},
                "content": [{
                    "nodeType": "unordered-list", "data": {},
                    "content": [
                        {"nodeType": "list-item", "data": {}, "content": [make_para_node(t)]}
                        for t in ing_texts
                    ],
                }],
            }
        else:
            new_ing = empty_doc()

        new_inst = make_ol_from_texts(inst_texts) if inst_texts else empty_doc()

        updated_fields = {
            k: v for k, v in fields.items()
            if k not in ("ingredients", "instructions")
        }
        updated_fields["ingredients"]  = {"en-US": new_ing}
        updated_fields["instructions"] = {"en-US": new_inst}

        try:
            result      = api_put(f"/entries/{entry_id}", {"fields": updated_fields}, version)
            new_version = result["sys"]["version"]
            api_put_action(f"/entries/{entry_id}/published", new_version)

            n_ing  = sum(len(n.get("content", [])) for n in new_ing["content"])
            n_inst = len(new_inst["content"][0].get("content", [])) if new_inst["content"] else 0
            print(f"  ✓  {title!r}  ({n_ing} ingredients, {n_inst} steps)")
            fixed += 1

        except Exception as e:
            print(f"  ✗  {title!r}: {e}")
            errors += 1

        time.sleep(0.3)

    print(f"\nDone — {fixed} fixed, {skipped} already OK, {errors} errors")


if __name__ == "__main__":
    main()
