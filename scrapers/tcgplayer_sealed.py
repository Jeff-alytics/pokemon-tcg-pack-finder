"""
TCGPlayer sealed product scraper.

Pulls real listing prices for booster packs, ETBs, booster bundles, and
booster boxes. Finds products via search, then visits each product page
to get actual listing prices (not the algorithmic "market price").

Uses Playwright for JS-heavy page rendering.
"""

import json
import re
import time
import logging
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

# Title must contain one of these to be considered a match
TITLE_MUST_CONTAIN = {
    "booster-pack": ["booster pack", "sleeved booster"],
    "elite-trainer-box": ["elite trainer box", "etb"],
    "booster-bundle": ["booster bundle"],
    "booster-box": ["booster box", "36 pack", "36-pack"],
}

SEARCH_URL = (
    "https://www.tcgplayer.com/search/pokemon/product"
    "?productLineName=pokemon&q={query}&view=grid"
)

REQUEST_DELAY = 2.0
PRODUCT_PAGE_DELAY = 2.0


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


def _extract_price(text: str) -> float | None:
    match = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _find_product_urls(page, set_name: str, product_type: str) -> list[tuple[str, str]]:
    """
    Search TCGPlayer and return list of (title, url) for matching sealed products.
    Only returns products whose title matches the expected product type.
    """
    query = f"{set_name} {PRODUCT_LABELS[product_type]}".replace(" ", "+")
    url = SEARCH_URL.format(query=query)
    log.info(f"  Searching: {url}")

    matches = []
    required_terms = TITLE_MUST_CONTAIN.get(product_type, [])

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(".search-result", timeout=12000)
        time.sleep(1.5)

        cards = page.query_selector_all(".search-result")
        log.info(f"  Found {len(cards)} search results")

        for card in cards:
            try:
                title_el = card.query_selector(".search-result__title, .product-card__title")
                title = title_el.inner_text().strip() if title_el else ""
                title_lower = title.lower()

                # Must match product type
                if required_terms and not any(t in title_lower for t in required_terms):
                    continue

                # Skip code cards
                if any(skip in title_lower for skip in ["code card", "online code", "ptcgo", "ptcgl"]):
                    continue

                # Must contain set name (at least partially)
                set_words = set_name.lower().split()
                if not any(w in title_lower for w in set_words if len(w) > 3):
                    continue

                link_el = card.query_selector("a[href*='/product/']")
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = f"https://www.tcgplayer.com{href}"

                if href:
                    matches.append((title, href))
            except Exception:
                continue

    except PwTimeout:
        log.warning(f"  Timeout on search")
    except Exception as e:
        log.error(f"  Search error: {e}")

    log.info(f"  {len(matches)} matching products found")
    return matches[:3]  # Top 3 matches max


def _scrape_product_page(page, product_url: str, title: str) -> list[Listing]:
    """
    Visit a TCGPlayer product page and extract actual listing prices.
    Returns list of Listing objects sorted by price.
    """
    listings = []
    log.info(f"  Visiting product page: {title[:50]}...")

    try:
        page.goto(product_url, wait_until="domcontentloaded", timeout=30000)

        # Wait for listings to load — TCGPlayer shows seller listings
        page.wait_for_selector(
            ".listing-item, .product-listing, [class*='listing'], .sellers__listing-row",
            timeout=10000
        )
        time.sleep(PRODUCT_PAGE_DELAY)

        # Try multiple selector patterns for seller listings
        rows = page.query_selector_all(
            ".listing-item, .product-listing, [class*='listing-item'], "
            ".sellers__listing-row, [data-testid='listing']"
        )

        if not rows:
            # Fallback: try to get the "add to cart" price from the main product area
            price_el = page.query_selector(
                ".product-detail__price, .price-point__price, "
                "[class*='price'] [class*='value'], .add-to-cart__price"
            )
            if price_el:
                price = _extract_price(price_el.inner_text())
                if price and price >= 1.0:
                    listings.append(Listing(
                        title=title,
                        price_usd=price,
                        url=product_url,
                        seller="TCGPlayer",
                        condition="Sealed",
                    ))
            # Also try the market price as a fallback
            mp_el = page.query_selector(".product-detail__market-price, .market-price__price")
            if mp_el:
                mp = _extract_price(mp_el.inner_text())
                if mp and mp >= 1.0 and not listings:
                    listings.append(Listing(
                        title=title,
                        price_usd=mp,
                        url=product_url,
                        seller="TCGPlayer (market)",
                        condition="Sealed",
                    ))
            log.info(f"    No listing rows found, fallback price: ${listings[0].price_usd if listings else 'N/A'}")
            return listings

        log.info(f"    {len(rows)} seller listings found")

        for row in rows[:10]:
            try:
                # Price
                price_el = row.query_selector(
                    ".listing-item__listing-data__info__price, "
                    "[class*='price'], .product-listing__price"
                )
                if not price_el:
                    continue
                price = _extract_price(price_el.inner_text())
                if price is None or price < 1.0:
                    continue

                # Seller name
                seller = "TCGPlayer"
                seller_el = row.query_selector(
                    ".seller-info__name, [class*='seller'] a, .product-listing__seller"
                )
                if seller_el:
                    seller = seller_el.inner_text().strip() or "TCGPlayer"

                # Condition
                condition = "Sealed"
                cond_el = row.query_selector("[class*='condition'], .listing-item__condition")
                if cond_el:
                    condition = cond_el.inner_text().strip() or "Sealed"

                listings.append(Listing(
                    title=title,
                    price_usd=price,
                    url=product_url,
                    seller=seller,
                    condition=condition,
                ))
            except Exception:
                continue

    except PwTimeout:
        log.warning(f"    Timeout on product page")
    except Exception as e:
        log.error(f"    Product page error: {e}")

    listings.sort(key=lambda x: x.price_usd)
    if listings:
        log.info(f"    Cheapest: ${listings[0].price_usd:.2f} from {listings[0].seller}")
    return listings


def scrape_set_product(page, set_name: str, product_type: str) -> ProductPricing:
    """Scrape pricing for one set + product type combo."""
    log.info(f"\n  --- {set_name} / {PRODUCT_LABELS[product_type]} ---")

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

    # Step 1: Find matching product URLs from search
    product_matches = _find_product_urls(page, set_name, product_type)
    time.sleep(REQUEST_DELAY)

    if not product_matches:
        log.warning(f"  No matching products found for {set_name} / {PRODUCT_LABELS[product_type]}")
        return result

    # Step 2: Visit top product page to get real listing prices
    all_listings = []
    # Only visit the first match (most relevant) to keep it fast
    title, href = product_matches[0]
    page_listings = _scrape_product_page(page, href, title)
    all_listings.extend(page_listings)
    time.sleep(REQUEST_DELAY)

    # If first product had no listings, try the second
    if not all_listings and len(product_matches) > 1:
        title2, href2 = product_matches[1]
        page_listings2 = _scrape_product_page(page, href2, title2)
        all_listings.extend(page_listings2)
        time.sleep(REQUEST_DELAY)

    if all_listings:
        prices = [l.price_usd for l in all_listings]
        prices.sort()
        result.low_price_usd = prices[0]
        result.high_price_usd = prices[-1]
        result.mid_price_usd = round(prices[len(prices) // 2], 2)
        result.market_price_usd = round(sum(prices) / len(prices), 2)
        result.num_listings = len(prices)
        result.cheapest_listings = [asdict(l) for l in all_listings[:5]]

    log.info(f"  Result: {result.num_listings} listings, low=${result.low_price_usd}")
    return result


def scrape_all_sets(sets_data: list[dict]) -> dict:
    """Scrape TCGPlayer for all tracked sets."""
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
            log.info(f"\n{'='*50}")
            log.info(f"=== {set_name} ({set_id}) ===")

            set_results = {}
            for pt in PRODUCT_TYPES:
                pricing = scrape_set_product(page, set_name, pt)
                set_results[pt] = asdict(pricing)
                time.sleep(REQUEST_DELAY)

            results[set_id] = set_results

        browser.close()

    return results


def run(sets_json_path: str = "data/sets.json") -> dict:
    """Entry point."""
    with open(sets_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    from datetime import date
    today = date.today().isoformat()
    released = [s for s in data["sets"] if s["release_date"] <= today]
    unreleased = [s for s in data["sets"] if s["release_date"] > today]

    if unreleased:
        log.info(f"Skipping {len(unreleased)} unreleased sets")

    return scrape_all_sets(released)


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2))
