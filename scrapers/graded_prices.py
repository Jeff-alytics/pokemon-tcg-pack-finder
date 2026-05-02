"""
Graded card price scraper.

Fetches eBay sold listings for graded versions (PSA 9, PSA 10, BGS 9.5)
of chase cards. Used by the card scanner to show grade premiums.

Also builds a lookup table stored in data/graded.json so the frontend
can do instant lookups without hitting eBay on every scan.
"""

import json
import re
import time
import logging
import statistics
from dataclasses import dataclass, asdict
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REQUEST_DELAY = 2.5
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

GRADE_QUERIES = {
    "raw": "{card_name} {card_number} -psa -bgs -cgc -graded -slab",
    "psa_9": "PSA 9 {card_name} {card_number}",
    "psa_10": "PSA 10 {card_name} {card_number}",
    "bgs_9_5": "BGS 9.5 {card_name} {card_number}",
}

# Filter out lots, bundles
LOT_KEYWORDS = re.compile(
    r"\b(lot|bundle|collection|wholesale|bulk|repack|mystery|grab bag|x\d+|\d+x)\b",
    re.IGNORECASE,
)


@dataclass
class GradedPrice:
    grade: str
    median_price_usd: float | None
    low_price_usd: float | None
    high_price_usd: float | None
    num_sales: int
    sample_listing_url: str | None


def _extract_price(text: str) -> float | None:
    match = re.search(r"\$\s*([\d,]+\.?\d*)", text.replace(",", ""))
    if match:
        return float(match.group(1))
    return None


def _scrape_ebay_sold(query: str, max_results: int = 40) -> tuple[list[float], str | None]:
    """Scrape eBay sold listings for a query. Returns (prices, sample_url)."""
    base = "https://www.ebay.com/sch/i.html"
    params = f"_nkw={quote_plus(query)}&_sacat=183454&LH_Sold=1&LH_Complete=1&_sop=13"
    url = f"{base}?{params}"

    prices = []
    sample_url = None

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        items = soup.select(".s-item")
        for item in items[:max_results]:
            title_el = item.select_one(".s-item__title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if title.lower().startswith("shop on ebay"):
                continue
            if LOT_KEYWORDS.search(title):
                continue

            price_el = item.select_one(".s-item__price")
            if not price_el:
                continue
            price_text = price_el.get_text(strip=True)
            if "to" in price_text.lower():
                continue
            price = _extract_price(price_text)
            if price and price > 0:
                prices.append(price)
                if sample_url is None:
                    link_el = item.select_one("a.s-item__link")
                    if link_el:
                        sample_url = link_el.get("href", "")

    except requests.RequestException as e:
        log.error(f"  eBay request failed: {e}")

    return prices, sample_url


def lookup_card_grades(card_name: str, card_number: str, set_name: str = "") -> dict:
    """
    Look up raw and graded prices for a single card.

    Returns dict with keys: raw, psa_9, psa_10, bgs_9_5, grade_premium
    """
    # Clean card name for search
    clean_name = re.sub(r"\(.*?\)", "", card_name).strip()
    if set_name:
        clean_name = f"Pokemon {set_name} {clean_name}"
    else:
        clean_name = f"Pokemon {clean_name}"

    results = {}
    for grade, query_tmpl in GRADE_QUERIES.items():
        query = query_tmpl.format(card_name=clean_name, card_number=card_number)
        log.info(f"  {grade}: {query}")
        prices, sample_url = _scrape_ebay_sold(query)
        time.sleep(REQUEST_DELAY)

        results[grade] = asdict(GradedPrice(
            grade=grade,
            median_price_usd=round(statistics.median(prices), 2) if prices else None,
            low_price_usd=min(prices) if prices else None,
            high_price_usd=max(prices) if prices else None,
            num_sales=len(prices),
            sample_listing_url=sample_url,
        ))

    # Compute grade premium (PSA 10 vs raw)
    raw_median = results["raw"]["median_price_usd"]
    psa10_median = results["psa_10"]["median_price_usd"]
    if raw_median and psa10_median and raw_median > 0:
        results["grade_premium"] = {
            "psa_10_vs_raw_multiplier": round(psa10_median / raw_median, 2),
            "psa_10_vs_raw_dollar": round(psa10_median - raw_median, 2),
            "worth_grading": psa10_median - raw_median > 50,
            "note": (
                f"PSA 10 trades at {psa10_median / raw_median:.1f}x raw. "
                f"Grade premium: ${psa10_median - raw_median:.0f}. "
                f"{'Worth grading if card is mint.' if psa10_median - raw_median > 50 else 'Marginal — grading fee may eat the premium.'}"
            ),
        }
    else:
        results["grade_premium"] = {
            "psa_10_vs_raw_multiplier": None,
            "psa_10_vs_raw_dollar": None,
            "worth_grading": None,
            "note": "Insufficient data to compute grade premium.",
        }

    return results


def run(sets_json_path: str = "data/sets.json") -> dict:
    """
    Build graded price lookup table for all chase cards across all sets.
    Returns dict keyed by "{set_id}/{card_number}".
    """
    with open(sets_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    from datetime import date
    today = date.today().isoformat()
    released = [s for s in data["sets"] if s["release_date"] <= today]

    lookup = {}
    for s in released:
        set_id = s["id"]
        set_name = s["name"]
        chase_cards = s.get("top_chase_cards", [])

        log.info(f"\n=== Graded prices: {set_name} ===")
        for card in chase_cards:
            card_name = card["name"]
            card_number = card.get("card_number", "")
            key = f"{set_id}/{card_number}"

            log.info(f"\n  Card: {card_name} ({card_number})")
            grades = lookup_card_grades(card_name, card_number, set_name)
            lookup[key] = {
                "set_id": set_id,
                "set_name": set_name,
                "card_name": card_name,
                "card_number": card_number,
                "estimated_value_usd": card.get("estimated_value_usd"),
                "grades": grades,
            }

    log.info(f"\nGraded lookup complete: {len(lookup)} cards")
    return lookup


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2))
