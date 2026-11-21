#!/usr/bin/env python3
"""Switcher helper: find sibling products (shades/sizes/scents), label them, and build the metafield writes.

  python switcher.py fetch example.com                  -> products.json   (public /products.json, paced)
  python switcher.py group products.json [manual.txt]   -> families.json + families-review.csv
  python switcher.py writes families.json               -> writes/batchN.graphql + writes/batchN.json
  python switcher.py verify-js families.json            -> verify.js (paste into the browser console on the store)
  python switcher.py selftest

Standard library only. Nothing here writes to Shopify: the agent sends writes/batch*.{graphql,json}
with the Admin GraphQL API after the owner approves families-review.csv.
"""
import collections, csv, json, os, re, sys, time, urllib.error, urllib.request

NS = "switcher"
UNIT = r"(ml|g|gm|gms|gram|grams|kg|l|ltr|oz|fl\s?oz|pcs|pc|pieces|sheets|caps|capsules|tablets|tabs|pads)"
SIZE = rf"\b\d+(?:\.\d+)?\s*{UNIT}\b"
SHADE_WORDS = r"foundation|lipstick|lip balm|lip|tint|blush|compact|gloss|concealer|powder|kajal|liner|bb cream|cushion|bronzer|highlighter|nail|mascara|eyeshadow|palette|stick|pencil"
SCENT_WORDS = r"perfume|parfum|deodorant|roll on|roll-on|body mist|fragrance|attar|cologne"


# ---------- fetch ----------
def fetch(domain, out="products.json"):
    products, page = [], 1
    while True:
        url = f"https://{domain}/products.json?limit=250&page={page}"
        for attempt in range(6):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 switcher-skill"})
                batch = json.load(urllib.request.urlopen(req, timeout=60))["products"]
                break
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
                time.sleep(15 * (attempt + 1))  # storefront rate limit: back off
        else:
            sys.exit(f"gave up on page {page} (rate limited)")
        if not batch:
            break
        products += [dict(id=p["id"], title=p["title"], handle=p["handle"], vendor=p["vendor"],
                          available=any(v["available"] for v in p["variants"])) for p in batch]
        page += 1
        time.sleep(2)
    json.dump(products, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(len(products), "products ->", out)


# ---------- grouping ----------
def norm(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def base(title):
    """Family key: title without sizes, brackets and the part after a ' - ' / '|' / 'shade'."""
    s = re.sub(r"\(.*?\)", "", title.lower())
    s = re.sub(SIZE, "", s, flags=re.I)
    s = re.split(r"\s+[-–|]|[-–|]\s+|\bshade\b", s)[0]
    return norm(s)


def words(t):
    return re.findall(r"\d+(?:\.\d+)?-\d+|\b[A-Z]{1,2}-[A-Z]{1,2}\b|[A-Za-z0-9.&+%']+", t)


def tidy(label):
    label = re.sub(r"\bshade\b", "", label, flags=re.I).strip(" -&,#")
    label = re.sub(r"\s+", " ", label)
    m = re.fullmatch(rf"(\d+(?:\.\d+)?)\s*{UNIT}", label, re.I)
    if m:
        unit = label[len(m.group(1)):].strip().lower()
        return m.group(1) + ("g" if unit in ("gm", "gms", "gram", "grams") else unit)
    m = re.fullmatch(r"([A-Za-z' ]+?) (\d{1,3})", label)  # "ROYAL RED 01" -> "01 ROYAL RED"
    if m:
        label = f"{m.group(2)} {m.group(1)}"
    label = " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in label.split())
    return label[:1].upper() + label[1:]


def labels_by_diff(titles):
    """Button labels = the words that differ between sibling titles (common prefix/suffix removed)."""
    W = [words(t) for t in titles]
    low = [[w.lower() for w in x] for x in W]
    pre = 0
    while all(len(x) > pre for x in low) and len({x[pre] for x in low}) == 1:
        pre += 1
    suf = 0
    while all(len(x) > pre + suf for x in low) and len({x[-1 - suf] for x in low}) == 1:
        suf += 1
    labs = [" ".join(x[pre:len(x) - suf]) for x in W]
    # a unit shared by every title ("- 118 ml") was stripped with the suffix: put it back
    if suf and all(re.search(r"\d$", l) for l in labs) and re.fullmatch(UNIT, low[0][len(low[0]) - suf], re.I):
        labs = [l + low[0][len(low[0]) - suf] for l in labs]
    return [tidy(l) for l in labs]


def label_by_prefix(title, prefix):
    s = re.sub(SIZE, "", title[len(prefix):], flags=re.I)
    return tidy(re.sub(r"\s*[-,#]+\s*", " ", s))


def group_name(title, labels):
    if all(re.fullmatch(rf"\d+(?:\.\d+)?{UNIT}", l, re.I) for l in labels):
        return "Size"
    if re.search(SCENT_WORDS, title, re.I):
        return "Scent"
    if re.search(SHADE_WORDS, title, re.I):
        return "Shade"
    return "Type"


def natural_key(label):
    m = re.match(r"\d+(?:\.\d+)?", label)
    return (float(m.group()) if m else 1e9, label.lower())


def read_manual(path):
    """manual.txt: one family per line, 'Title prefix | Group'. Prefix families win over auto ones."""
    rules = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            prefix, _, grp = line.partition("|")
            rules.append((prefix.strip(), grp.strip() or None))
    return rules


def group(products, manual=()):
    used, fams, skipped = set(), [], []
    for prefix, grp in manual:
        mem = [p for p in products if p["title"].lower().startswith(prefix.lower()) and p["id"] not in used]
        if len(mem) < 2:
            skipped.append((prefix, "fewer than 2 products match"))
            continue
        labs = [label_by_prefix(p["title"], p["title"][:len(prefix)]) for p in mem]
        fams.append(make_family(mem, labs, grp))
        used |= {p["id"] for p in mem}
    buckets = collections.defaultdict(list)
    for p in products:
        if p["id"] not in used:
            buckets[(p["vendor"].lower(), base(p["title"]))].append(p)
    for mem in buckets.values():
        if len(mem) < 2:
            continue
        labs = labels_by_diff([p["title"] for p in mem])
        fams.append(make_family(mem, labs, None))
    good = []
    for f in fams:
        labs = [i["label"] for i in f["items"]]
        if any(not l for l in labs) or len({l.lower() for l in labs}) < len(labs) or max(map(len, labs)) > 40:
            skipped.append((f["items"][0]["title"], f"unclear labels {labs}"))
        else:
            good.append(f)
    return good, skipped


def make_family(members, labels, grp):
    items = sorted(({**p, "label": l} for p, l in zip(members, labels)), key=lambda i: natural_key(i["label"]))
    return dict(vendor=members[0]["vendor"], group=grp or group_name(members[0]["title"], labels), items=items)


def cmd_group(products_path, manual_path=None):
    products = json.load(open(products_path, encoding="utf-8"))
    fams, skipped = group(products, read_manual(manual_path) if manual_path else ())
    json.dump(fams, open("families.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open("families-review.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["family", "vendor", "group", "button_label", "title", "handle", "in_stock"])
        for n, f in enumerate(fams, 1):
            for i in f["items"]:
                w.writerow([n, f["vendor"], f["group"], i["label"], i["title"], i["handle"], "yes" if i["available"] else "no"])
        for title, why in skipped:
            w.writerow(["SKIPPED", "", "", why, title, "", ""])
    print(f"{len(fams)} families, {sum(len(f['items']) for f in fams)} products, {len(skipped)} skipped"
          " -> families.json, families-review.csv")
    print(dict(collections.Counter(f["group"] for f in fams)))


# ---------- writes ----------
def cmd_writes(families_path, per_set=25, sets_per_call=8):
    fams = json.load(open(families_path, encoding="utf-8"))
    ids = [i["id"] for f in fams for i in f["items"]]
    assert len(ids) == len(set(ids)), "a product is in two families"
    mf = []
    for f in fams:
        refs = json.dumps([f"gid://shopify/Product/{i['id']}" for i in f["items"]])
        for i in f["items"]:
            owner = f"gid://shopify/Product/{i['id']}"
            mf += [dict(ownerId=owner, namespace=NS, key="siblings", value=refs),
                   dict(ownerId=owner, namespace=NS, key="label", value=i["label"]),
                   dict(ownerId=owner, namespace=NS, key="group", value=f["group"])]
    os.makedirs("writes", exist_ok=True)
    chunks = [mf[i:i + per_set] for i in range(0, len(mf), per_set)]  # metafieldsSet takes at most 25
    calls = [chunks[i:i + sets_per_call] for i in range(0, len(chunks), sets_per_call)]
    for n, call in enumerate(calls):
        v = {f"a{j}": c for j, c in enumerate(call)}
        q = ("mutation(" + ",".join(f"${k}:[MetafieldsSetInput!]!" for k in v) + "){"
             + " ".join(f"{k}:metafieldsSet(metafields:${k}){{userErrors{{field message code}}}}" for k in v) + "}")
        open(f"writes/batch{n}.graphql", "w", encoding="utf-8").write(q)
        json.dump(v, open(f"writes/batch{n}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{len(mf)} metafields in {len(calls)} requests -> writes/batch0..{len(calls) - 1}")


# ---------- verify ----------
VERIFY_JS = r"""// Switcher check: paste into the browser console on the store (any page). Prints problems, or "all good".
// Run it a minute after the writes: Shopify's page cache can serve the old page for ~1 minute.
(async () => {
  const expected = __EXPECTED__;
  const bad = []; let n = 0;
  for (const [handle, want] of Object.entries(expected)) {
    const r = await fetch('/products/' + handle, {cache: 'no-store'});
    const d = new DOMParser().parseFromString(await r.text(), 'text/html');
    const nav = d.querySelector('.switcher');
    n++;
    if (!nav) { bad.push([handle, 'no switcher']); continue; }
    const items = [...nav.querySelectorAll('.switcher__item')].map(a => {
      const c = a.cloneNode(true); c.querySelectorAll('.switcher__sr,.switcher__swatch').forEach(x => x.remove());
      return [new URL(a.href).pathname.split('/products/')[1], c.textContent.trim(), a.hasAttribute('aria-current')];
    });
    const got = JSON.stringify({group: nav.querySelector('.switcher__label').childNodes[0].textContent.replace(/:\s*$/, '').trim(), items});
    if (got !== JSON.stringify(want)) bad.push([handle, got]);
    await new Promise(res => setTimeout(res, 400));
  }
  console.log(n + ' pages checked'); console.log(bad.length ? bad : 'all good');
})();
"""


def cmd_verify_js(families_path):
    fams = json.load(open(families_path, encoding="utf-8"))
    exp = {}
    for f in fams:
        for i in f["items"]:
            exp[i["handle"]] = dict(group=f["group"], items=[[j["handle"], j["label"], j["id"] == i["id"]] for j in f["items"]])
    open("verify.js", "w", encoding="utf-8").write(VERIFY_JS.replace("__EXPECTED__", json.dumps(exp, ensure_ascii=False)))
    print(len(exp), "pages -> verify.js")


# ---------- selftest ----------
def selftest():
    P = lambda i, t, v="Brand", a=True: dict(id=i, title=t, handle=f"h{i}", vendor=v, available=a)
    products = [
        P(1, "Brand Hydra Gel - 50ml"), P(2, "Brand Hydra Gel - 100ml"), P(3, "Brand Hydra Gel- 15 ML"),
        P(4, "Brand Velvet Lipstick 3.2g 02 Ruby Red"), P(5, "Brand Velvet Lipstick 3.2g 10 Nude Kiss"),
        P(6, "Brand Lip Liner ROYAL RED 01"), P(7, "Brand Lip Liner HOT PINK 05"),
        P(8, "Brand Cleanser 118 ml"), P(9, "Brand Cleanser 25 ml"),
        P(10, "Brand Only One Of Me 30ml"),
    ]
    fams, skipped = group(products, [("Brand Velvet Lipstick 3.2g", "Shade"), ("Brand Lip Liner", None)])
    got = {f["items"][0]["title"].split(" ")[1]: (f["group"], [i["label"] for i in f["items"]]) for f in fams}
    assert got["Velvet"] == ("Shade", ["02 Ruby Red", "10 Nude Kiss"]), got["Velvet"]
    assert got["Lip"] == ("Shade", ["01 Royal Red", "05 Hot Pink"]), got["Lip"]
    assert got["Hydra"] == ("Size", ["15ml", "50ml", "100ml"]), got["Hydra"]
    assert got["Cleanser"] == ("Size", ["25ml", "118ml"]), got["Cleanser"]
    assert len(fams) == 4 and not skipped, (len(fams), skipped)
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"fetch": fetch, "group": cmd_group, "writes": cmd_writes, "verify-js": cmd_verify_js, "selftest": selftest}
    if not a or a[0] not in cmds:
        sys.exit(__doc__)
    cmds[a[0]](*a[1:])
