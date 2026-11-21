---
name: switcher
description: Link a Shopify store's separate products that are really shades, sizes or scents of one item (e.g. "Lipstick - Ruby", "Lipstick - Nude", "Serum 30ml", "Serum 50ml") with a shade/size switcher on the product page, instead of merging them into Shopify variants. Use when the user wants a shade selector, size selector, "other shades", "switch variation", or wants related variants shown without changing URLs, SKUs, inventory or SEO. Installs a theme snippet, creates product metafields, groups products automatically, and writes the links via the Admin GraphQL API.
---

# Switcher

Each shade or size stays its own product (own URL, SKU, stock, reviews, rankings). Switcher only links them: a row of buttons near the price, sold-out ones crossed out, and on a sold-out page "2 other shades in stock — tap one above".

Prefer this over converting to real variants when the products already rank in search, sync stock with another system, or have separate SKUs/barcodes. Merging into variants changes URLs and breaks those.

## What you need

- Admin GraphQL access (a Shopify MCP/connector or a custom app token) with `read_products`, `write_products`, and for the theme step `write_themes`.
- Python 3 (standard library only) for `scripts/switcher.py`.
- The owner's approval before every write. Show the plan and the review CSV first.

## Workflow

1. **Theme (on an unpublished copy, never the live theme).** Duplicate the live theme (`themeDuplicate`, or Online Store → Themes → Duplicate). Copy `theme/snippets/switcher.liquid` into it and add `{% render 'switcher', product: product %}` to the product section, near the price / stock line, outside the add-to-cart `<form>`. Upload with `themeFilesUpsert` or `shopify theme push --unpublished`. Pages look unchanged until products are linked.
2. **Fields.** Check `metafieldDefinitions(ownerType: PRODUCT, namespace: "switcher")` first; create only the missing ones with `references/definitions.graphql`.
3. **Find families.** `python scripts/switcher.py fetch <store-domain>` (public `/products.json`; or build `products.json` from the Admin API with fields `id` (numeric), `title`, `handle`, `vendor`, `available`). Then `python scripts/switcher.py group products.json [manual.txt]`.
   - Auto grouping: same vendor + same title once sizes, brackets and the part after ` - ` / `|` / "shade" are removed. Labels are the words that differ.
   - It misses titles where the shade sits after the size ("Lip Liner 1.4g 01 Lusty Pink"). Add those to `manual.txt` as `Title prefix | Shade` (see `references/manual.example.txt`); manual families win.
   - Read `families-review.csv` yourself, fix odd labels in `families.json`, and give the CSV to the owner. Families joining different products are the main risk.
4. **Write.** After the owner approves: `python scripts/switcher.py writes families.json`, then send each `writes/batchN.graphql` with `writes/batchN.json` as its variables (8 × 25 `metafieldsSet` per request). Stop on any `userErrors`. If bulk operations are allowed, `bulkOperationRunMutation` is a fine alternative.
5. **Verify.** `python scripts/switcher.py verify-js families.json`, open the store (add `?preview_theme_id=<id>` while unpublished) and paste `verify.js` into the browser console. Expect "all good". Scripted fetches from a terminal often get HTTP 429 from the storefront; the browser does not.
6. **Publish.** The owner previews and publishes the theme themselves.

## Gotchas

- Shopify caches product pages: a page can show the old version for ~1 minute after a write.
- A product belongs to one family. Re-linking it overwrites its old family, so re-write every member of both families.
- New products are not linked automatically: set "Other shades / sizes" (`switcher.siblings`) on each member in admin, or rerun steps 3–5.
- Keep labels short (≤ 40 characters). `group` is the heading: Shade, Size, Scent, Type or Set.
- `swatch` (colour) is optional; leave it empty rather than guess a colour.
- Undo: delete the `switcher.*` metafields (`metafieldsDelete`) and the render line. Products are never modified otherwise.
