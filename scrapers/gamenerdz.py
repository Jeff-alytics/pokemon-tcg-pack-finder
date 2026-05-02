"""
GameNerdz scraper.

GameNerdz frequently has sealed Pokemon TCG below MSRP, especially their
"Deal of the Day" items. Uses requests + BeautifulSoup (site renders
server-side).
"""

import json
import re
import time
import logging
from dataclasses import dataclass, asdict
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REQUEST_DELAY = 2.0
BASE_URL = "https://www.gamenerdz.com"
SEARCH_URL = BASE_URL + "/catalogsearch/result/?q={query}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class GameNerdzProduct:
    title: str
    price_usd: float | None
    original_price_usd: float | None
    url: str
    in_stock: bool
    is_deal_of_day: bool


def _extract_price(text: str) -> float | None:
    match = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def scrape_search(query: str) -> list[GameNerdzProduct]:
    """Search GameNerdz and extract product listings."""
    url = SEARCH_URL.format(query=quote_plus(query))
    log.info(f"  GN search: {query}")
    results = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        products = soup.select(".product-item, .item.product.product-item")

        for product in products[:15]:
            try:
                # Title
                title_el = product.select_one(".product-item-link, .product-name a")
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                # Filter to Pokemon TCG sealed only
                title_lower = title.lower()
                if "pokemon" not in title_lower and "pokémon" not in title_lower:
                    continue

                # URL
                href = ""
                if title_el and title_el.name == "a":
                    href = title_el.get("href", "")
                elif title_el:
                    link = title_el.find_parent("a")
                    href = link.get("href", "") if link else ""

                # Price — look for sale price first, then regular
                sale_price_el = product.select_one(".special-price .price, .sale-price")
                regular_price_el = product.select_one(".old-price .price, .regular-price .price, .price")

                price = None
                original_price = None
                if sale_price_el:
                    price = _extract_price(sale_price_el.get_text())
                    if regular_price_el and regular_price_el != sale_price_el:
                        original_price = _extract_price(regular_price_el.get_text())
                elif regular_price_el:
                    price = _extract_price(regular_price_el.get_text())

                # Stock status
                oos = product.select_one(".out-of-stock, .stock.unavailable")
                add_btn = product.select_one("button.tocart, button[title='Add to Cart']")
                in_stock = oos is None and (add_btn is not None or price is not None)

                # Deal of the Day detection
                is_dotd = bool(product.select_one(".dotd, .deal-of-the-day")) or (
                    original_price and price and price < original_price * 0.8
                )

                results.append(GameNerdzProduct(
                    title=title,
                    price_usd=price,
                    original_price_usd=original_price,
                    url=href,
                    in_stock=in_stock,
                    is_deal_of_day=is_dotd,
                ))
            except Exception as e:
                log.debug(f"  Skipping product: {e}")

    except requests.RequestException as e:
        log.error(f"  Request failed: {e}")

    log.info(f"    Found {len(results)} products, {sum(1 for r in results if r.in_stock)} in stock")
    return results


def scrape_deal_of_day() -> list[GameNerdzProduct]:
    """Scrape the Deal of the Day page for Pokemon TCG items."""
    url = BASE_URL + "/deal-of-the-day"
    log.info("  GN Deal of the Day page")
    results = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        products = soup.select(".product-item, .item.product.product-item")
        for product in products:
            try:
                title_el = product.select_one(".product-item-link, .product-name a")
                title = title_el.get_text(strip=True) if title_el else ""
                title_lower = title.lower()
                if not ("pokemon" in title_lower or "pokémon" in title_lower):
                    continue

                href = ""
                if title_el and title_el.name == "a":
                    href = title_el.get("href", "")

                price_el = product.select_one(".special-price .price, .price")
                price = _extract_price(price_el.get_text()) if price_el else None

                old_price_el = product.select_one(".old-price .price")
                original_price = _extract_price(old_price_el.get_text()) if old_price_el else None

                results.append(GameNerdzProduct(
                    title=title,
                    price_usd=price,
                    original_price_usd=original_price,
                    url=href,
                    in_stock=True,
                    is_deal_of_day=True,
                ))
            except Exception:
                continue

    except requests.RequestException as e:
        log.error(f"  Deal of Day request failed: {e}")

    log.info(f"    {len(results)} Pokemon TCG deals of the day")
    return results


def scrape_set(set_name: str) -> dict:
    """Scrape GameNerdz for all product types of a set."""
    log.info(f"\n=== GameNerdz: {set_name} ===")

    queries = {
        "booster-pack": f"Pokemon {set_name} booster pack",
        "elite-trainer-box": f"Pokemon {set_name} elite trainer box",
        "booster-bundle": f"Pokemon {set_name} booster bundle",
        "booster-box": f"Pokemon {set_name} booster box",
    }

    set_results = {}
    for pt, query in queries.items():
        products = scrape_search(query)
        set_results[pt] = [asdict(p) for p in products]
        time.sleep(REQUEST_DELAY)

    return set_results


def scrape_all_sets(sets_data: list[dict]) -> dict:
    """Scrape GameNerdz for all tracked sets + Deal of the Day."""
    results = {"_deal_of_day": [asdict(p) for p in scrape_deal_of_day()]}
    time.sleep(REQUEST_DELAY)

    for s in sets_data:
        results[s["id"]] = scrape_set(s["name"])

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
