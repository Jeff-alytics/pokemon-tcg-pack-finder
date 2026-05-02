"""
Pokemon Center stock checker.

Only checks high-demand sets that frequently sell out and restock.
When something goes from out-of-stock to in-stock at MSRP, that's
a deal worth alerting on.

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

SEARCH_URL = "https://www.pokemoncenter.com/search?q={query}"

# Only check sets where restocks matter (high demand, frequently OOS)
RESTOCK_WATCH = [
    "prismatic-evolutions",
    "paldean-fates",
    "pokemon-151",
    "destined-rivals",
    "journey-together",
]


@dataclass
class StockStatus:
    title: str
    price_usd: float | None
    url: str
    in_stock: bool


def _extract_price(text):
    m = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    return float(m.group(1).replace(",", "")) if m else None


def check_stock(page, set_name: str) -> list[StockStatus]:
    """Check Pokemon Center for a set's stock status."""
    query = set_name.replace(" ", "+")
    url = SEARCH_URL.format(query=query)
    log.info(f"  Checking: {set_name}")
    results = []

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("[data-testid='product-card'], .product-card, .search-results", timeout=10000)
        time.sleep(2)

        cards = page.query_selector_all("[data-testid='product-card'], .product-card, .product-tile")
        for card in cards[:8]:
            try:
                title_el = card.query_selector("[data-testid='product-card-title'], .product-card__title, h3, h2")
                title = title_el.inner_text().strip() if title_el else ""
                if not title:
                    continue

                # Only care about packs, ETBs, boxes, bundles
                tl = title.lower()
                if not any(kw in tl for kw in ["booster", "pack", "elite trainer", "etb", "bundle", "box"]):
                    continue

                price_el = card.query_selector("[data-testid='product-card-price'], .product-card__price, .price")
                price = _extract_price(price_el.inner_text()) if price_el else None

                link_el = card.query_selector("a[href*='/product/']")
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = f"https://www.pokemoncenter.com{href}"

                oos_el = card.query_selector("[data-testid='out-of-stock'], .out-of-stock, .sold-out, button[disabled]")
                add_btn = card.query_selector("button:not([disabled])")
                in_stock = oos_el is None

                results.append(StockStatus(title=title, price_usd=price, url=href, in_stock=in_stock))
                status = "IN STOCK" if in_stock else "out of stock"
                log.info(f"    {title[:50]:50s} ${price or '?':>8}  {status}")
            except Exception:
                continue

    except PwTimeout:
        log.warning(f"  Timeout checking {set_name}")
    except Exception as e:
        log.error(f"  Error: {e}")

    return results


def run(sets_json_path: str = "data/sets.json") -> dict:
    """Check stock for high-demand sets. Returns dict keyed by set ID."""
    with open(sets_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    set_names = {s["id"]: s["name"] for s in data["sets"]}
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        for sid in RESTOCK_WATCH:
            if sid in set_names:
                items = check_stock(page, set_names[sid])
                results[sid] = [asdict(item) for item in items]
                time.sleep(2)

        browser.close()

    # Summary
    total_in_stock = sum(1 for items in results.values() for i in items if i["in_stock"])
    log.info(f"\nStock check done: {total_in_stock} products in stock across {len(results)} sets")
    return results


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
