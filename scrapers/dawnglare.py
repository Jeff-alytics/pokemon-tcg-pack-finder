"""
Dawnglare price scraper.

pokemon.dawnglare.com has a clean table of sealed product prices (boxes,
ETBs, half boxes) for every Pokemon TCG set with TCGPlayer buy links.
One page, simple HTML, no JS rendering needed.
"""

import json
import re
import logging

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DAWNGLARE_URL = "https://pokemon.dawnglare.com/?p=boxprice"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Keywords to match our set IDs from Dawnglare set names
SET_KEYWORDS = {
    "crown-zenith": ["crown zenith"],
    "pokemon-151": ["151"],
    "paldean-fates": ["paldean fates"],
    "twilight-masquerade": ["twilight masquerade"],
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

# Classify product type from the name
def _classify_product(name_lower: str) -> str | None:
    if "half booster box" in name_lower:
        return "half-booster-box"
    if "enhanced booster box" in name_lower:
        return "enhanced-booster-box"
    if "booster box" in name_lower:
        return "booster-box"
    if "elite trainer box" in name_lower or "etb" in name_lower:
        return "etb"
    if "booster bundle" in name_lower:
        return "booster-bundle"
    return None


def _match_set_id(name: str) -> str | None:
    name_lower = name.lower()
    for sid, keywords in SET_KEYWORDS.items():
        if any(kw in name_lower for kw in keywords):
            return sid
    return None


def scrape() -> dict:
    """
    Scrape Dawnglare. Returns dict keyed by set ID, each containing
    a list of products with prices and buy links.
    """
    log.info("=== Dawnglare Prices ===")
    results = {}

    try:
        resp = requests.get(DAWNGLARE_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        rows = soup.select("table tr")
        log.info(f"Scanning {len(rows)} rows")

        for row in rows:
            cells = row.select("td")
            if len(cells) < 2:
                continue

            name = cells[0].get_text(strip=True)
            price_text = cells[1].get_text(strip=True)

            # Match to our tracked sets
            sid = _match_set_id(name)
            if not sid:
                continue

            # Extract price
            price_match = re.search(r"\$?\s*([\d,]+\.?\d*)", price_text.replace(",", ""))
            if not price_match:
                continue
            price = float(price_match.group(1))
            if price < 10:
                continue

            # Classify product type
            product_type = _classify_product(name.lower())
            if not product_type:
                continue

            # Get buy link
            link = cells[0].select_one("a") or cells[1].select_one("a")
            url = link.get("href", "") if link else ""

            # Determine packs in product
            packs = {"booster-box": 36, "half-booster-box": 18, "enhanced-booster-box": 36,
                     "etb": 9, "booster-bundle": 6}.get(product_type, 1)

            # Skip Pokemon Center exclusives (much higher price, not representative)
            if "pokemon center" in name.lower() and "exclusive" in name.lower():
                continue
            # Skip Dollar General, Costco, Sam's Club exclusives
            if any(x in name.lower() for x in ["dollar general", "costco", "sam's club"]):
                continue

            if sid not in results:
                results[sid] = []

            results[sid].append({
                "name": name,
                "product_type": product_type,
                "price_usd": round(price, 2),
                "per_pack_usd": round(price / packs, 2),
                "packs": packs,
                "url": url,
                "source": "Dawnglare (TCGPlayer)",
            })

            log.info(f"  {name[:50]:50s} ${price:>10.2f}  (${price/packs:.2f}/pk)")

    except requests.RequestException as e:
        log.error(f"Dawnglare request failed: {e}")

    log.info(f"\nMatched {len(results)} tracked sets, {sum(len(v) for v in results.values())} total products")
    return results


def run(sets_json_path: str = "data/sets.json") -> dict:
    """Entry point."""
    return scrape()


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2))
