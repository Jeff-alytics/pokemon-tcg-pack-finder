"""
eBay scraper for Pokémon TCG booster packs and chase singles.

Two modes:
  1. Sold listings (trailing 30 days) — computes median sold price
  2. Active listings — cheapest current Buy It Now offers with direct links

Filters out lots, bundles, and multi-pack listings to keep data clean.
Uses requests + BeautifulSoup (eBay search works without JS rendering).
"""

import json
import re
import time
import logging
import statistics
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REQUEST_DELAY = 2.0
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Words that indicate a listing is a lot/bundle (not a single item)
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
    listing_type: str  # "buy_it_now" or "auction"
    shipping_usd: float | None


def _extract_price(text: str) -> float | None:
    """Parse price from eBay listing text."""
    match = re.search(r"\$\s*([\d,]+\.?\d*)", text.replace(",", ""))
    if match:
        return float(match.group(1))
    return None


def _is_single_item(title: str) -> bool:
    """Return True if the listing appears to be a single pack/card, not a lot."""
    return not LOT_KEYWORDS.search(title)


def _build_ebay_url(query: str, sold: bool = False, sort_price_asc: bool = False) -> str:
    """Build eBay search URL."""
    base = "https://www.ebay.com/sch/i.html"
    params = {
        "_nkw": query,
        "_sacat": "183454",  # Pokemon TCG category
    }
    if sold:
        params["LH_Sold"] = "1"
        params["LH_Complete"] = "1"
        params["_sop"] = "13"  # Sort by end date (recent first)
    else:
        params["LH_BIN"] = "1"  # Buy It Now only
        if sort_price_asc:
            params["_sop"] = "15"  # Sort by price + shipping: lowest first
        else:
            params["_sop"] = "15"
    param_str = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
    return f"{base}?{param_str}"


def _scrape_listings(url: str, max_results: int = 50) -> list[tuple[str, float, str]]:
    """
    Scrape eBay search results page.
    Returns list of (title, price, url) tuples.
    """
    results = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        items = soup.select(".s-item")
        for item in items[:max_results]:
            # Title
            title_el = item.select_one(".s-item__title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if title.lower().startswith("shop on ebay"):
                continue

            # Price
            price_el = item.select_one(".s-item__price")
            if not price_el:
                continue
            price_text = price_el.get_text(strip=True)
            # Skip price ranges ("$10.00 to $20.00")
            if "to" in price_text.lower():
                continue
            price = _extract_price(price_text)
            if price is None or price <= 0:
                continue

            # URL
            link_el = item.select_one("a.s-item__link")
            href = link_el.get("href", "") if link_el else ""

            # Filter out lots
            if not _is_single_item(title):
                continue

            results.append((title, price, href))

    except requests.RequestException as e:
        log.error(f"  Request failed: {e}")

    return results


def scrape_sold(query: str, period_days: int = 30) -> SoldResult:
    """Scrape sold listings for a query and compute median price."""
    url = _build_ebay_url(query, sold=True)
    log.info(f"  Sold listings: {query}")

    raw = _scrape_listings(url, max_results=80)
    prices = [p for _, p, _ in raw]

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


def scrape_active(query: str, max_listings: int = 5) -> list[ActiveListing]:
    """Scrape cheapest active Buy It Now listings for a query."""
    url = _build_ebay_url(query, sold=False, sort_price_asc=True)
    log.info(f"  Active listings: {query}")

    raw = _scrape_listings(url, max_results=30)

    listings = []
    for title, price, href in raw[:max_listings]:
        listings.append(ActiveListing(
            title=title,
            price_usd=price,
            url=href,
            seller="eBay",
            listing_type="buy_it_now",
            shipping_usd=None,  # Would require per-listing fetch to get exact shipping
        ))

    log.info(f"    {len(listings)} active listings, cheapest=${listings[0].price_usd if listings else 'N/A'}")
    return listings


def scrape_set(set_data: dict) -> dict:
    """
    Scrape eBay sold + active data for one set.

    Returns dict with:
      - booster_pack_sold: SoldResult for booster packs
      - booster_pack_active: list of ActiveListing
      - chase_singles: dict keyed by card name, each with sold + active data
    """
    set_name = set_data["name"]
    log.info(f"\n=== eBay: {set_name} ===")

    result = {}

    # Booster pack search
    pack_query = f"Pokemon {set_name} booster pack sealed -lot -bundle -repack"
    sold = scrape_sold(pack_query)
    time.sleep(REQUEST_DELAY)
    active = scrape_active(pack_query)
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
        # Build a targeted search query
        search_name = re.sub(r"\(.*?\)", "", card_name).strip()  # Remove parentheticals
        card_query = f"Pokemon {search_name} {card_number} -lot -bundle -repack"

        sold = scrape_sold(card_query)
        time.sleep(REQUEST_DELAY)
        active = scrape_active(card_query, max_listings=3)
        time.sleep(REQUEST_DELAY)

        result["chase_singles"][card_name] = {
            "card_number": card_number,
            "sold": asdict(sold),
            "active_listings": [asdict(l) for l in active],
        }

    return result


def scrape_all_sets(sets_data: list[dict]) -> dict:
    """Scrape eBay for all tracked sets. Returns dict keyed by set ID."""
    results = {}
    for s in sets_data:
        results[s["id"]] = scrape_set(s)
    return results


def run(sets_json_path: str = "data/sets.json") -> dict:
    """Entry point — load sets, scrape, return results dict."""
    with open(sets_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    from datetime import date
    today = date.today().isoformat()
    released = [s for s in data["sets"] if s["release_date"] <= today]
    unreleased = [s for s in data["sets"] if s["release_date"] > today]

    if unreleased:
        log.info(f"Skipping {len(unreleased)} unreleased sets: {[s['name'] for s in unreleased]}")

    return scrape_all_sets(released)


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2, default=str))
