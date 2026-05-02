"""
TCGPlayer sealed product scraper.

Pulls market prices for booster packs, ETBs, booster bundles, and booster boxes
for each tracked set. Uses Playwright for JS-heavy page rendering.

Returns:
  - Market data: median/low/high prices per product type
  - Active listings: cheapest 5 listings per set/product type with direct URLs
"""

import json
import re
import time
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PRODUCT_TYPES = ["booster-pack", "elite-trainer-box", "booster-bundle", "booster-box"]

PRODUCT_LABELS = {
    "booster-pack": "Booster Pack",
    "elite-trainer-box": "Elite Trainer Box",
    "booster-bundle": "Booster Bundle",
    "booster-box": "Booster Box",
}

# TCGPlayer sealed product search — uses the general search with sealed keyword filters
SEARCH_URL = (
    "https://www.tcgplayer.com/search/pokemon/product"
    "?productLineName=pokemon"
    "&q={query}"
    "&view=grid"
)

# Delay between page loads (seconds) — be respectful
REQUEST_DELAY = 3.0


@dataclass
class Listing:
    title: str
    price_usd: float
    url: str
    seller: str
    condition: str


@dataclass
class ProductPricing:
    product_type: str
    product_label: str
    market_price_usd: float | None
    low_price_usd: float | None
    mid_price_usd: float | None
    high_price_usd: float | None
    num_listings: int
    cheapest_listings: list[dict]


def _build_search_url(set_name: str, product_type: str) -> str:
    """Build a TCGPlayer search URL targeting sealed products."""
    product_label = PRODUCT_LABELS.get(product_type, product_type)
    # Explicitly search for sealed product by name + type
    query = f"{set_name} {product_label} sealed".replace(" ", "+")
    return SEARCH_URL.format(query=query)


def _extract_price(text: str) -> float | None:
    """Parse a price string like '$4.49' or '$129.99' into a float."""
    match = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def scrape_set_product(page, set_name: str, product_type: str) -> ProductPricing:
    """Scrape pricing for one set + product type combo from TCGPlayer."""
    url = _build_search_url(set_name, product_type)
    log.info(f"Scraping: {set_name} / {PRODUCT_LABELS[product_type]} -> {url}")

    listings: list[Listing] = []
    prices: list[float] = []
    result = ProductPricing(
        product_type=product_type,
        product_label=PRODUCT_LABELS[product_type],
        market_price_usd=None,
        low_price_usd=None,
        mid_price_usd=None,
        high_price_usd=None,
        num_listings=0,
        cheapest_listings=[],
    )

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Wait for product listings to render
        page.wait_for_selector(".search-result", timeout=15000)
        time.sleep(1.5)  # Let lazy-loaded prices settle

        # Grab all result cards
        cards = page.query_selector_all(".search-result")
        log.info(f"  Found {len(cards)} result cards")

        for card in cards:
            try:
                # Title
                title_el = card.query_selector(".search-result__title, .product-card__title")
                title = title_el.inner_text().strip() if title_el else "Unknown"

                # Filter out individual cards, code cards, and non-sealed items
                title_lower = title.lower()
                if any(skip in title_lower for skip in [
                    "code card", "online code", "ptcgo", "ptcgl",
                    " - ", " v ", " ex ", " gx ", " vmax ", " vstar ",
                ]):
                    # Check if it's actually a sealed product keyword
                    if not any(keep in title_lower for keep in [
                        "booster", "pack", "box", "etb", "elite trainer",
                        "bundle", "sealed", "collection", "tin",
                    ]):
                        continue

                # Price — look for the market price or listing price
                price_el = card.query_selector(
                    ".product-card__market-price__price, "
                    ".search-result__market-price--value, "
                    ".inventory__price-with-shipping"
                )
                if not price_el:
                    continue
                price = _extract_price(price_el.inner_text())
                if price is None or price < 1.00:  # Sealed products are never under $1
                    continue

                # URL
                link_el = card.query_selector("a[href*='/product/']")
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = f"https://www.tcgplayer.com{href}"

                prices.append(price)
                listings.append(Listing(
                    title=title,
                    price_usd=price,
                    url=href,
                    seller="TCGPlayer",
                    condition="Sealed",
                ))
            except Exception as e:
                log.debug(f"  Skipping card: {e}")
                continue

    except PwTimeout:
        log.warning(f"  Timeout loading {url} — may have no listings")
    except Exception as e:
        log.error(f"  Error scraping {url}: {e}")

    if prices:
        prices.sort()
        result.low_price_usd = prices[0]
        result.high_price_usd = prices[-1]
        result.mid_price_usd = round(prices[len(prices) // 2], 2)
        result.market_price_usd = round(sum(prices) / len(prices), 2)
        result.num_listings = len(prices)

    # Keep cheapest 5 with direct links
    listings.sort(key=lambda x: x.price_usd)
    result.cheapest_listings = [asdict(l) for l in listings[:5]]

    log.info(
        f"  {result.num_listings} listings, "
        f"low=${result.low_price_usd}, mid=${result.mid_price_usd}, "
        f"market=${result.market_price_usd}"
    )
    return result


def scrape_all_sets(sets_data: list[dict]) -> dict:
    """
    Scrape TCGPlayer for all tracked sets.

    Args:
        sets_data: List of set dicts from sets.json

    Returns:
        Dict keyed by set ID, each containing product type pricing.
    """
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        for s in sets_data:
            set_id = s["id"]
            set_name = s["name"]
            log.info(f"\n=== {set_name} ({set_id}) ===")

            set_results = {}
            for pt in PRODUCT_TYPES:
                pricing = scrape_set_product(page, set_name, pt)
                set_results[pt] = asdict(pricing)
                time.sleep(REQUEST_DELAY)

            results[set_id] = set_results

        browser.close()

    return results


def run(sets_json_path: str = "data/sets.json") -> dict:
    """Entry point — load sets, scrape, return results dict."""
    with open(sets_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Only scrape released sets (release_date <= today)
    from datetime import date
    today = date.today().isoformat()
    released = [s for s in data["sets"] if s["release_date"] <= today]
    unreleased = [s for s in data["sets"] if s["release_date"] > today]

    if unreleased:
        log.info(f"Skipping {len(unreleased)} unreleased sets: {[s['name'] for s in unreleased]}")

    return scrape_all_sets(released)


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2))
