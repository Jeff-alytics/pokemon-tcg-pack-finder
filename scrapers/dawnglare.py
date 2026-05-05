"""
Dawnglare price scraper.

pokemon.dawnglare.com has TCGPlayer market prices for sealed products.
We grab: Booster Box, Half Booster Box, Enhanced Booster Box, ETB.
Simple HTML, one request, no JS.
"""

import json
import re
import logging

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DAWNGLARE_URL = "https://pokemon.dawnglare.com/?p=boxprice"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}

SET_KEYWORDS = {
    "evolving-skies": ["evolving skies"],
    "brilliant-stars": ["brilliant stars"],
    "pokemon-go": ["pokemon go"],
    "lost-origin": ["lost origin"],
    "crown-zenith": ["crown zenith"],
    "scarlet-violet-base": ["scarlet & violet", "scarlet and violet"],
    "paldea-evolved": ["paldea evolved"],
    "obsidian-flames": ["obsidian flames"],
    "pokemon-151": ["151"],
    "paradox-rift": ["paradox rift"],
    "paldean-fates": ["paldean fates"],
    "temporal-forces": ["temporal forces"],
    "twilight-masquerade": ["twilight masquerade"],
    "shrouded-fable": ["shrouded fable"],
    "stellar-crown": ["stellar crown"],
    "surging-sparks": ["surging sparks"],
    "prismatic-evolutions": ["prismatic evolutions"],
    "journey-together": ["journey together"],
    "destined-rivals": ["destined rivals"],
    "mega-evolution": ["mega evolution"],
    "ascended-heroes": ["ascended heroes"],
    "perfect-order": ["perfect order"],
    "chaos-rising": ["chaos rising"],
}

# Products we care about and their pack counts
PRODUCT_TYPES = {
    "booster box": {"packs": 36, "label": "Booster Box"},
    "half booster box": {"packs": 18, "label": "Half Booster Box"},
    "enhanced booster box": {"packs": 36, "label": "Enhanced Booster Box"},
    "elite trainer box": {"packs": 9, "label": "ETB"},
    "booster bundle": {"packs": 6, "label": "Booster Bundle"},
}


def _match_set(name):
    nl = name.lower()
    for sid, kws in SET_KEYWORDS.items():
        if any(kw in nl for kw in kws):
            return sid
    return None


def _match_product(name):
    nl = name.lower()
    # Skip Pokemon Center exclusives
    if "pokemon center" in nl and "exclusive" in nl:
        return None, None
    # Order matters — check longer strings first
    for key in ["half booster box", "enhanced booster box", "booster box",
                "elite trainer box", "booster bundle"]:
        if key in nl:
            return key, PRODUCT_TYPES[key]
    return None, None


def scrape():
    log.info("=== Dawnglare ===")
    results = {}
    try:
        resp = requests.get(DAWNGLARE_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for row in soup.select("table tr"):
            cells = row.select("td")
            if len(cells) < 2:
                continue
            name = cells[0].get_text(strip=True)
            sid = _match_set(name)
            if not sid:
                continue
            ptype, pinfo = _match_product(name)
            if not ptype:
                continue
            price_match = re.search(r"\$?([\d,]+\.?\d*)", cells[1].get_text(strip=True).replace(",", ""))
            if not price_match:
                continue
            price = float(price_match.group(1))
            if price < 20:
                continue

            link = cells[0].select_one("a") or cells[1].select_one("a")
            url = link.get("href", "") if link else ""

            if sid not in results:
                results[sid] = []
            results[sid].append({
                "name": name,
                "product_type": ptype,
                "label": pinfo["label"],
                "price_usd": round(price, 2),
                "packs": pinfo["packs"],
                "per_pack_usd": round(price / pinfo["packs"], 2),
                "url": url,
            })
            log.info(f"  {name[:55]:55s} ${price:>8.2f}  ${price/pinfo['packs']:.2f}/pk")

    except Exception as e:
        log.error(f"Dawnglare failed: {e}")

    # Sort each set's products by per-pack price
    for sid in results:
        results[sid].sort(key=lambda x: x["per_pack_usd"])

    log.info(f"Done: {len(results)} sets, {sum(len(v) for v in results.values())} products")
    return results


def run(sets_json_path="data/sets.json"):
    return scrape()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
