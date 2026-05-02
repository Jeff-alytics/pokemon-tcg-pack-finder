"""
Graded card price lookup via eBay Finding API.

Fetches sold listings for graded versions (PSA 9, PSA 10, BGS 9.5)
of chase cards. Builds a lookup table in data/graded.json.

Requires EBAY_APP_ID environment variable (same key as ebay_sold.py).
"""

import json
import os
import re
import time
import logging
import statistics
from dataclasses import dataclass, asdict

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REQUEST_DELAY = 0.5
FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
CATEGORY_ID = "183454"

GRADE_QUERIES = {
    "raw": "{card_name} {card_number} -psa -bgs -cgc -graded -slab",
    "psa_9": "PSA 9 {card_name} {card_number}",
    "psa_10": "PSA 10 {card_name} {card_number}",
    "bgs_9_5": "BGS 9.5 {card_name} {card_number}",
}

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


def _api_sold_search(query: str, app_id: str, max_results: int = 50) -> tuple[list[float], str | None]:
    """Query eBay Finding API for sold items. Returns (prices, sample_url)."""
    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": query,
        "categoryId": CATEGORY_ID,
        "sortOrder": "EndTimeSoonest",
        "paginationInput.entriesPerPage": str(min(max_results, 100)),
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
    }

    prices = []
    sample_url = None

    try:
        resp = requests.get(FINDING_API_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        response = data.get("findCompletedItemsResponse", [{}])[0]
        items = response.get("searchResult", [{}])[0].get("item", [])

        for item in items:
            title = item.get("title", [""])[0] if isinstance(item.get("title"), list) else item.get("title", "")
            if LOT_KEYWORDS.search(title):
                continue
            try:
                selling = item.get("sellingStatus", [{}])[0]
                price_info = selling.get("convertedCurrentPrice", [{}])[0]
                price = float(price_info.get("__value__", 0))
                if price > 0:
                    prices.append(price)
                    if sample_url is None:
                        sample_url = item.get("viewItemURL", [""])[0] if isinstance(item.get("viewItemURL"), list) else ""
            except (IndexError, KeyError, ValueError, TypeError):
                continue

    except requests.RequestException as e:
        log.error(f"    API request failed: {e}")

    return prices, sample_url


def lookup_card_grades(card_name: str, card_number: str, set_name: str, app_id: str) -> dict:
    """Look up raw and graded prices for a single card."""
    clean_name = re.sub(r"\(.*?\)", "", card_name).strip()
    full_name = f"Pokemon {set_name} {clean_name}" if set_name else f"Pokemon {clean_name}"

    results = {}
    for grade, query_tmpl in GRADE_QUERIES.items():
        query = query_tmpl.format(card_name=full_name, card_number=card_number)
        log.info(f"    {grade}: {query[:80]}...")
        prices, sample_url = _api_sold_search(query, app_id)
        time.sleep(REQUEST_DELAY)

        results[grade] = asdict(GradedPrice(
            grade=grade,
            median_price_usd=round(statistics.median(prices), 2) if prices else None,
            low_price_usd=min(prices) if prices else None,
            high_price_usd=max(prices) if prices else None,
            num_sales=len(prices),
            sample_listing_url=sample_url,
        ))

    # Grade premium
    raw_med = results["raw"]["median_price_usd"]
    psa10_med = results["psa_10"]["median_price_usd"]
    if raw_med and psa10_med and raw_med > 0:
        results["grade_premium"] = {
            "psa_10_vs_raw_multiplier": round(psa10_med / raw_med, 2),
            "psa_10_vs_raw_dollar": round(psa10_med - raw_med, 2),
            "worth_grading": psa10_med - raw_med > 50,
            "note": (
                f"PSA 10 trades at {psa10_med / raw_med:.1f}x raw. "
                f"Premium: ${psa10_med - raw_med:.0f}. "
                f"{'Worth grading if mint.' if psa10_med - raw_med > 50 else 'Marginal — grading fee may eat the premium.'}"
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
    """Build graded price lookup table for all chase cards."""
    app_id = os.environ.get("EBAY_APP_ID", "")
    if not app_id:
        log.warning("EBAY_APP_ID not set — skipping graded price scraper")
        return {}

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

        log.info(f"\n=== Graded: {set_name} ===")
        for card in chase_cards:
            card_name = card["name"]
            card_number = card.get("card_number", "")
            key = f"{set_id}/{card_number}"
            log.info(f"  {card_name} ({card_number})")

            grades = lookup_card_grades(card_name, card_number, set_name, app_id)
            lookup[key] = {
                "set_id": set_id,
                "set_name": set_name,
                "card_name": card_name,
                "card_number": card_number,
                "estimated_value_usd": card.get("estimated_value_usd"),
                "grades": grades,
            }

    log.info(f"\nGraded lookup: {len(lookup)} cards")
    return lookup


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2))
