"""
Amazon scraper for sealed Pokemon TCG products.

Tracks lowest offers on booster packs, ETBs, boxes. Amazon has aggressive
bot detection, so this scraper uses careful request pacing and rotating
headers. Falls back gracefully if blocked.

Uses requests + BeautifulSoup (no Playwright needed for search results).
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

REQUEST_DELAY = 4.0  # Slower for Amazon
SEARCH_URL = "https://www.amazon.com/s?k={query}&i=toys-and-games"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Filter out non-sealed / irrelevant listings
EXCLUDE_KEYWORDS = re.compile(
    r"\b(sleeve|binder|playmat|coin|dice|card protector|toploader|penny|case|custom|"
    r"proxy|fake|repack|mystery|grab bag|protector|album)\b",
    re.IGNORECASE,
)


@dataclass
class AmazonProduct:
    title: str
    price_usd: float | None
    url: str
    rating: float | None
    num_reviews: int | None
    is_prime: bool
    seller: str


def _extract_price(text: str) -> float | None:
    match = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _get_headers(idx: int = 0) -> dict:
    return {
        "User-Agent": USER_AGENTS[idx % len(USER_AGENTS)],
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    }


def scrape_search(query: str, request_idx: int = 0) -> list[AmazonProduct]:
    """Search Amazon and extract product listings."""
    url = SEARCH_URL.format(query=quote_plus(query))
    log.info(f"  Amazon search: {query}")
    results = []

    try:
        resp = requests.get(url, headers=_get_headers(request_idx), timeout=20)

        if resp.status_code == 503:
            log.warning("  Amazon returned 503 (bot detection). Backing off.")
            return results
        if resp.status_code == 429:
            log.warning("  Amazon rate limited (429). Backing off.")
            return results
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")

        # Check for CAPTCHA
        if soup.select_one("#captchacharacters, .captcha-container"):
            log.warning("  Amazon CAPTCHA detected — skipping")
            return results

        items = soup.select("[data-component-type='s-search-result']")
        log.info(f"    {len(items)} search results")

        for item in items[:15]:
            try:
                # Title
                title_el = item.select_one("h2 a span, h2 span")
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                # Skip non-sealed products
                if EXCLUDE_KEYWORDS.search(title):
                    continue

                # Must contain pokemon
                if "pokemon" not in title.lower() and "pokémon" not in title.lower():
                    continue

                # URL
                link_el = item.select_one("h2 a")
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = f"https://www.amazon.com{href}"
                # Strip tracking params
                if "/dp/" in href:
                    asin_match = re.search(r"/dp/([A-Z0-9]{10})", href)
                    if asin_match:
                        href = f"https://www.amazon.com/dp/{asin_match.group(1)}"

                # Price — whole + fraction
                price = None
                price_whole = item.select_one(".a-price-whole")
                price_frac = item.select_one(".a-price-fraction")
                if price_whole:
                    whole = price_whole.get_text(strip=True).replace(",", "").rstrip(".")
                    frac = price_frac.get_text(strip=True) if price_frac else "00"
                    try:
                        price = float(f"{whole}.{frac}")
                    except ValueError:
                        pass

                if price is None:
                    price_el = item.select_one(".a-price .a-offscreen")
                    if price_el:
                        price = _extract_price(price_el.get_text())

                if price is None or price <= 0:
                    continue

                # Rating
                rating = None
                rating_el = item.select_one(".a-icon-star-small .a-icon-alt, [data-action='a-popover'] .a-icon-alt")
                if rating_el:
                    rmatch = re.search(r"([\d.]+)\s+out", rating_el.get_text())
                    if rmatch:
                        rating = float(rmatch.group(1))

                # Review count
                num_reviews = None
                reviews_el = item.select_one("[data-action='a-popover'] + span .a-size-base, .a-size-base.s-underline-text")
                if reviews_el:
                    rev_text = reviews_el.get_text(strip=True).replace(",", "")
                    if rev_text.isdigit():
                        num_reviews = int(rev_text)

                # Prime
                is_prime = bool(item.select_one(".s-prime, [aria-label*='Prime']"))

                results.append(AmazonProduct(
                    title=title,
                    price_usd=price,
                    url=href,
                    rating=rating,
                    num_reviews=num_reviews,
                    is_prime=is_prime,
                    seller="Amazon",
                ))
            except Exception as e:
                log.debug(f"  Skipping item: {e}")

    except requests.RequestException as e:
        log.error(f"  Request failed: {e}")

    results.sort(key=lambda x: x.price_usd or 999)
    log.info(f"    {len(results)} valid listings, cheapest=${results[0].price_usd if results else 'N/A'}")
    return results


def scrape_set(set_name: str, request_idx: int) -> dict:
    """Scrape Amazon for all product types of a set."""
    log.info(f"\n=== Amazon: {set_name} ===")

    queries = {
        "booster-pack": f"Pokemon {set_name} booster pack sealed",
        "elite-trainer-box": f"Pokemon {set_name} elite trainer box",
        "booster-box": f"Pokemon {set_name} booster box 36 packs",
    }

    set_results = {}
    for pt, query in queries.items():
        products = scrape_search(query, request_idx)
        set_results[pt] = [asdict(p) for p in products[:5]]  # Top 5 cheapest
        request_idx += 1
        time.sleep(REQUEST_DELAY)

    return set_results


def scrape_all_sets(sets_data: list[dict]) -> dict:
    """Scrape Amazon for all tracked sets."""
    results = {}
    request_idx = 0

    for s in sets_data:
        results[s["id"]] = scrape_set(s["name"], request_idx)
        request_idx += len(PRODUCT_QUERIES) if "PRODUCT_QUERIES" in dir() else 3

    return results


PRODUCT_QUERIES = {
    "booster-pack": "booster pack sealed",
    "elite-trainer-box": "elite trainer box",
    "booster-box": "booster box 36 packs",
}


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
