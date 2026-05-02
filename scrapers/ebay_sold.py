"""
eBay scraper for Pokémon TCG booster packs and chase singles.

Uses eBay's official Finding API (free, no datacenter IP blocks).
Requires EBAY_APP_ID environment variable.

Two modes:
  1. Sold/completed listings — computes median sold price (30 days)
  2. Active listings — cheapest current Buy It Now offers with direct links

Filters out lots, bundles, and multi-pack listings.

To get an API key:
  1. Sign up at https://developer.ebay.com
  2. Create an application (Production)
  3. Copy the App ID (Client ID)
  4. Set as EBAY_APP_ID env var or GitHub secret
"""

import json
import os
import re
import time
import logging
import statistics
from datetime import datetime
from dataclasses import dataclass, asdict

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REQUEST_DELAY = 0.5  # API is fast, but be polite
FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1"

# Pokemon TCG category ID
CATEGORY_ID = "183454"

# Lot/bundle filter
LOT_KEYWORDS = re.compile(
    r"\b(lot|bundle|collection|set of|wholesale|bulk|repack|mystery|grab bag|x\d+|\d+x)\b",
    re.IGNORECASE,
)


@dataclass
class SoldResult:
    query: str
    median_price_usd: float | None
    avg_price_usd: float | None
    low_price_usd: float | None
    high_price_usd: float | None
    num_sales: int
    period_days: int


@dataclass
class ActiveListing:
    title: str
    price_usd: float
    url: str
    seller: str
    listing_type: str
    shipping_usd: float | None


def _get_app_id() -> str | None:
    """Get eBay App ID from environment."""
    return os.environ.get("EBAY_APP_ID", "")


def _is_single_item(title: str) -> bool:
    """Return True if listing appears to be a single item, not a lot."""
    return not LOT_KEYWORDS.search(title)


def _finding_api_search(
    query: str, app_id: str, completed: bool = False, sort_order: str = "BestMatch",
    max_results: int = 50
) -> list[dict]:
    """
    Call eBay Finding API.
    completed=True uses findCompletedItems (sold), False uses findItemsByKeywords (active).
    """
    operation = "findCompletedItems" if completed else "findItemsByKeywords"

    params = {
        "OPERATION-NAME": operation,
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": query,
        "categoryId": CATEGORY_ID,
        "sortOrder": sort_order,
        "paginationInput.entriesPerPage": str(min(max_results, 100)),
        "paginationInput.pageNumber": "1",
        # Filter to Buy It Now for active listings
        "itemFilter(0).name": "ListingType",
        "itemFilter(0).value(0)": "FixedPrice",
        "itemFilter(0).value(1)": "AuctionWithBIN",
    }

    if completed:
        # For sold items, filter to sold only (not just completed)
        params["itemFilter(1).name"] = "SoldItemsOnly"
        params["itemFilter(1).value"] = "true"

    try:
        resp = requests.get(FINDING_API_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Navigate the nested response
        result_key = f"{operation}Response"
        response = data.get(result_key, [{}])[0]
        search_result = response.get("searchResult", [{}])[0]
        items = search_result.get("item", [])
        count = int(search_result.get("@count", "0"))

        log.info(f"    API returned {count} items")
        return items

    except requests.RequestException as e:
        log.error(f"    eBay API request failed: {e}")
        return []
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        log.error(f"    eBay API parse error: {e}")
        return []


def _extract_price_from_item(item: dict) -> float | None:
    """Extract price from a Finding API item."""
    try:
        selling = item.get("sellingStatus", [{}])[0]
        # For sold items, use convertedCurrentPrice; for active, currentPrice
        price_info = selling.get("convertedCurrentPrice", [{}])[0] or selling.get("currentPrice", [{}])[0]
        return float(price_info.get("__value__", 0))
    except (IndexError, KeyError, ValueError, TypeError):
        return None


def _extract_item_url(item: dict) -> str:
    """Extract URL from a Finding API item."""
    try:
        return item.get("viewItemURL", [""])[0]
    except (IndexError, KeyError):
        return ""


def _extract_title(item: dict) -> str:
    """Extract title from a Finding API item."""
    try:
        return item.get("title", [""])[0]
    except (IndexError, KeyError):
        return ""


def _extract_shipping(item: dict) -> float | None:
    """Extract shipping cost from a Finding API item."""
    try:
        shipping = item.get("shippingInfo", [{}])[0]
        cost = shipping.get("shippingServiceCost", [{}])[0]
        return float(cost.get("__value__", 0))
    except (IndexError, KeyError, ValueError, TypeError):
        return None


def scrape_sold(query: str, app_id: str, period_days: int = 30) -> SoldResult:
    """Query sold listings and compute median price."""
    log.info(f"  Sold: {query}")
    items = _finding_api_search(query, app_id, completed=True, sort_order="EndTimeSoonest", max_results=80)

    prices = []
    for item in items:
        title = _extract_title(item)
        if not _is_single_item(title):
            continue
        price = _extract_price_from_item(item)
        if price and price > 0:
            prices.append(price)

    result = SoldResult(
        query=query,
        median_price_usd=round(statistics.median(prices), 2) if prices else None,
        avg_price_usd=round(statistics.mean(prices), 2) if prices else None,
        low_price_usd=min(prices) if prices else None,
        high_price_usd=max(prices) if prices else None,
        num_sales=len(prices),
        period_days=period_days,
    )
    log.info(f"    {result.num_sales} sales, median=${result.median_price_usd}")
    return result


def scrape_active(query: str, app_id: str, max_listings: int = 5) -> list[ActiveListing]:
    """Query cheapest active Buy It Now listings."""
    log.info(f"  Active: {query}")
    items = _finding_api_search(query, app_id, completed=False, sort_order="PricePlusShippingLowest", max_results=30)

    listings = []
    for item in items:
        title = _extract_title(item)
        if not _is_single_item(title):
            continue
        price = _extract_price_from_item(item)
        if price is None or price <= 0:
            continue
        url = _extract_item_url(item)
        shipping = _extract_shipping(item)

        listings.append(ActiveListing(
            title=title,
            price_usd=price,
            url=url,
            seller="eBay",
            listing_type="buy_it_now",
            shipping_usd=shipping,
        ))
        if len(listings) >= max_listings:
            break

    log.info(f"    {len(listings)} active, cheapest=${listings[0].price_usd if listings else 'N/A'}")
    return listings


def scrape_set(set_data: dict, app_id: str) -> dict:
    """Scrape eBay sold + active data for one set."""
    set_name = set_data["name"]
    log.info(f"\n=== eBay: {set_name} ===")
    result = {}

    # Booster pack
    pack_query = f"Pokemon {set_name} booster pack sealed -lot -bundle -repack"
    sold = scrape_sold(pack_query, app_id)
    time.sleep(REQUEST_DELAY)
    active = scrape_active(pack_query, app_id)
    time.sleep(REQUEST_DELAY)
    result["booster_pack"] = {
        "sold": asdict(sold),
        "active_listings": [asdict(l) for l in active],
    }

    # Chase singles
    chase_cards = set_data.get("top_chase_cards", [])
    result["chase_singles"] = {}
    for card in chase_cards:
        card_name = card["name"]
        card_number = card.get("card_number", "")
        search_name = re.sub(r"\(.*?\)", "", card_name).strip()
        card_query = f"Pokemon {search_name} {card_number} -lot -bundle -repack"

        sold = scrape_sold(card_query, app_id)
        time.sleep(REQUEST_DELAY)
        active = scrape_active(card_query, app_id, max_listings=3)
        time.sleep(REQUEST_DELAY)

        result["chase_singles"][card_name] = {
            "card_number": card_number,
            "sold": asdict(sold),
            "active_listings": [asdict(l) for l in active],
        }

    return result


def scrape_all_sets(sets_data: list[dict], app_id: str) -> dict:
    """Scrape eBay for all tracked sets."""
    results = {}
    for s in sets_data:
        results[s["id"]] = scrape_set(s, app_id)
    return results


def run(sets_json_path: str = "data/sets.json") -> dict:
    """Entry point."""
    app_id = _get_app_id()
    if not app_id:
        log.warning("EBAY_APP_ID not set — skipping eBay scraper")
        log.warning("Get a free API key at https://developer.ebay.com")
        return {}

    with open(sets_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    from datetime import date
    today = date.today().isoformat()
    released = [s for s in data["sets"] if s["release_date"] <= today]
    unreleased = [s for s in data["sets"] if s["release_date"] > today]

    if unreleased:
        log.info(f"Skipping {len(unreleased)} unreleased sets")

    return scrape_all_sets(released, app_id)


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2, default=str))
