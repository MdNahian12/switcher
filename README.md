# Switcher

A Claude Code skill for Shopify stores that sell each shade, size or scent as its own product. Instead of merging them into variants, Switcher **links** them: a row of buttons on every product page lets shoppers switch between "Ruby Red / Nude Kiss / Berry" or "15ml / 50ml / 100ml".

- Every product keeps its URL, SKU, stock, reviews and search rankings. Nothing is merged or renamed.
- Sold-out options are crossed out but still clickable, and a sold-out page says "2 other shades in stock — tap one above".
- Products are grouped automatically from their titles, labelled ("30ml", "02 Ruby Red"), and you review a CSV before anything is written.
- One small theme snippet and four product metafields. Undo by deleting both.

## Why not variants?

Turning separate products into variants changes their URLs (lost rankings), and breaks anything keyed to the product: inventory sync with a spreadsheet or ERP, per-product SKUs and barcodes, reviews, ads. Switcher gives shoppers the same "pick a shade" experience without touching any of that.

## Install

```bash
git clone https://github.com/MdNahian12/switcher ~/.claude/skills/switcher
```

Then ask Claude Code something like: *"Use the switcher skill to link my shade and size products on my Shopify store."* Claude needs Admin API access to the store (a Shopify MCP connector or an app token).

## What's inside

| Path | What it is |
|---|---|
| `SKILL.md` | The workflow Claude follows: theme copy → fields → group → review → write → verify. |
| `theme/snippets/switcher.liquid` | The switcher. Render it in your product section: `{% render 'switcher', product: product %}`. Colours follow CSS variables (`--switcher-active-bg`, `--switcher-border`, …). |
| `scripts/switcher.py` | Fetches products, finds families, labels them, builds the GraphQL write batches and a browser check script. Python 3, standard library only. `python scripts/switcher.py selftest` runs its tests. |
| `references/definitions.graphql` | The four product metafield definitions (`switcher.siblings`, `label`, `group`, `swatch`). |
| `references/manual.example.txt` | Hand-defined families for titles the automatic grouping misses. |

## Data model

| Metafield | Type | Example |
|---|---|---|
| `switcher.siblings` | list of products | every product in the family, in button order |
| `switcher.label` | text | `30ml`, `02 Ruby Red` |
| `switcher.group` | text | `Shade`, `Size`, `Scent`, `Type`, `Set` |
| `switcher.swatch` | colour (optional) | `#b5364b` |

You can also link products by hand: open a product in Shopify admin and fill in the fields above on each member of the family.

## License

MIT
