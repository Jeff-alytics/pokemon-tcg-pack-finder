"""
TCGPlayer product link finder.

Finds the correct TCGPlayer product page URLs for sealed Pokemon TCG products.
Does NOT extract prices (TCGPlayer's dynamic JS rendering makes scraped prices
unreliable). Prices come from other scrapers (GameNerdz, Amazon, eBay API).

Provides direct "buy here" links for the frontend.
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


@dataclass
class ProductLink:
    title: str
    url: str
    product_type: str


def find_product_links(page, set_name: str, product_type: str) -> list[ProductLink]:
    """Search TCGPlayer and return matching product links (no prices)."""
    query = f"{set_name} {PRODUCT_LABELS[product_type]}".replace(" ", "+")
    url = SEARCH_URL.format(query=query)
    log.info(f"  Searching: {set_name} / {PRODUCT_LABELS[product_type]}")

    matches = []
    required_terms = TITLE_MUST_CONTAIN.get(product_type, [])

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(".search-result", timeout=12000)
        time.sleep(1.5)

        cards = page.query_selector_all(".search-result")

        for card in cards[:15]:
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

                # Must relate to the set
                set_words = set_name.lower().split()
                if not any(w in title_lower for w in set_words if len(w) > 3):
                    continue

                link_el = card.query_selector("a[href*='/product/']")
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = f"https://www.tcgplayer.com{href}"

                if href:
                    matches.append(ProductLink(title=title, url=href, product_type=product_type))
            except Exception:
                continue

    except PwTimeout:
        log.warning(f"  Timeout on search")
    except Exception as e:
        log.error(f"  Search error: {e}")

    log.info(f"  Found {len(matches)} matching products")
    return matches[:3]


def scrape_all_sets(sets_data: list[dict]) -> dict:
    """Find TCGPlayer product links for all tracked sets."""
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
            log.info(f"\n=== {set_name} ===")

            set_results = {}
            for pt in PRODUCT_TYPES:
                links = find_product_links(page, set_name, pt)
                set_results[pt] = {
                    "product_type": pt,
                    "product_label": PRODUCT_LABELS[pt],
                    "links": [asdict(l) for l in links],
                }
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

    return scrape_all_sets(released)


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2))
