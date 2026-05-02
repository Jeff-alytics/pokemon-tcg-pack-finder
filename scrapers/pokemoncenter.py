"""
Pokemon Center scraper.

Tracks MSRP prices and stock status for sealed Pokemon TCG products.
Key value: restock alerts — Pokemon Center sells at MSRP but frequently
sells out. Knowing when something is back in stock is the deal.

Uses Playwright since pokemoncenter.com is JS-heavy.
"""

import json
import re
import time
import logging
from dataclasses import dataclass, asdict
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REQUEST_DELAY = 3.0

# Search URL for Pokemon TCG sealed products
SEARCH_URL = "https://www.pokemoncenter.com/search?q={query}&fh_location=pokemon-tcg"

PRODUCT_QUERIES = {
    "booster-pack": "{set_name} booster pack",
    "elite-trainer-box": "{set_name} elite trainer box",
    "booster-bundle": "{set_name} booster bundle",
    "booster-box": "{set_name} booster box",
}


@dataclass
class PokemonCenterProduct:
    title: str
    price_usd: float | None
    url: str
    in_stock: bool
    product_type: str


def _extract_price(text: str) -> float | None:
    match = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def scrape_search(page, query: str, product_type: str) -> list[PokemonCenterProduct]:
    """Search Pokemon Center for a query and extract product listings."""
    url = SEARCH_URL.format(query=query.replace(" ", "+"))
    log.info(f"  PC search: {query}")
    results = []

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("[data-testid='product-card'], .product-card, .search-results", timeout=12000)
        time.sleep(2)

        cards = page.query_selector_all("[data-testid='product-card'], .product-card, .product-tile")

        for card in cards[:10]:
            try:
                title_el = card.query_selector("[data-testid='product-card-title'], .product-card__title, h3, h2")
                title = title_el.inner_text().strip() if title_el else ""
                if not title:
                    continue

                price_el = card.query_selector("[data-testid='product-card-price'], .product-card__price, .price")
                price = _extract_price(price_el.inner_text()) if price_el else None

                link_el = card.query_selector("a[href*='/product/']")
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = f"https://www.pokemoncenter.com{href}"

                # Check stock status
                oos_el = card.query_selector(
                    "[data-testid='out-of-stock'], .out-of-stock, .sold-out, "
                    "button[disabled], .product-card__oos"
                )
                add_btn = card.query_selector(
                    "button:not([disabled]):has-text('Add'), "
                    "[data-testid='add-to-cart']"
                )
                in_stock = add_btn is not None and oos_el is None

                results.append(PokemonCenterProduct(
                    title=title,
                    price_usd=price,
                    url=href,
                    in_stock=in_stock,
                    product_type=product_type,
                ))
            except Exception as e:
                log.debug(f"  Skipping card: {e}")

    except PwTimeout:
        log.warning(f"  Timeout on Pokemon Center search: {query}")
    except Exception as e:
        log.error(f"  Error scraping Pokemon Center: {e}")

    log.info(f"    Found {len(results)} products, {sum(1 for r in results if r.in_stock)} in stock")
    return results


def scrape_set(page, set_name: str) -> dict:
    """Scrape Pokemon Center for all product types of a set."""
    log.info(f"\n=== Pokemon Center: {set_name} ===")
    set_results = {}

    for pt, query_tmpl in PRODUCT_QUERIES.items():
        query = query_tmpl.format(set_name=set_name)
        products = scrape_search(page, query, pt)
        set_results[pt] = [asdict(p) for p in products]
        time.sleep(REQUEST_DELAY)

    return set_results


def scrape_all_sets(sets_data: list[dict]) -> dict:
    """Scrape Pokemon Center for all tracked sets."""
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
            results[s["id"]] = scrape_set(page, s["name"])

        browser.close()

    return results


def run(sets_json_path: str = "data/sets.json") -> dict:
    """Entry point."""
    with open(sets_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    from datetime import date
    today = date.today().isoformat()
    released = [s for s in data["sets"] if s["release_date"] <= today]

    return scrape_all_sets(released)


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2))
