"""
Reddit r/PokemonTCGDeals scraper.

Pulls recent deal posts from the subreddit using Reddit's public JSON API.
This catches deals from every source — Costco finds, Target clearance,
random vendor sales, restocks — that no product scraper would find.

No authentication needed (public JSON endpoint).
"""

import json
import re
import time
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SUBREDDIT_URL = "https://www.reddit.com/r/PokemonTCGDeals"
JSON_URL = SUBREDDIT_URL + "/new.json"
SEARCH_URL = SUBREDDIT_URL + "/search.json"
HEADERS = {
    "User-Agent": "PokemonTCGPackFinder/1.0 (deal aggregator; educational use)",
    "Accept": "application/json",
}
REQUEST_DELAY = 2.0

# Flair categories we care about
DEAL_FLAIRS = {"deal", "in stock", "sale", "restock", "clearance", "price drop"}

# Set name patterns to match in post titles
SET_PATTERNS = {}  # Populated dynamically from sets.json


@dataclass
class RedditDeal:
    title: str
    url: str
    reddit_url: str
    score: int
    num_comments: int
    flair: str
    created_utc: str
    author: str
    price_mentioned: float | None
    matched_sets: list[str]
    source_store: str | None


def _extract_price(text: str) -> float | None:
    """Try to find a price mentioned in the post title."""
    match = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _detect_store(title: str, url: str) -> str | None:
    """Detect which store the deal is from."""
    text = (title + " " + url).lower()
    stores = {
        "walmart": ["walmart.com", "walmart"],
        "target": ["target.com", "target"],
        "amazon": ["amazon.com", "amzn.to", "amazon"],
        "costco": ["costco.com", "costco"],
        "best buy": ["bestbuy.com", "best buy"],
        "gamestop": ["gamestop.com", "gamestop"],
        "pokemon center": ["pokemoncenter.com", "pokemon center", "pokémon center"],
        "gamenerdz": ["gamenerdz.com", "gamenerdz"],
        "tcgplayer": ["tcgplayer.com", "tcgplayer"],
        "ebay": ["ebay.com", "ebay"],
        "troll and toad": ["trollandtoad.com", "troll and toad"],
        "dave & adam's": ["dacardworld.com", "dave & adam", "dave and adam"],
        "steel city": ["steelcitycollectibles.com", "steel city"],
        "safari zone": ["safarizone", "safari zone"],
        "mvp sports": ["mvpsportsandmore", "mvp sports"],
    }
    for store_name, keywords in stores.items():
        if any(kw in text for kw in keywords):
            return store_name
    return None


def _match_sets(title: str, set_names: dict[str, str]) -> list[str]:
    """Match post title against tracked set names. Returns list of set IDs."""
    title_lower = title.lower()
    matched = []
    for set_id, set_name in set_names.items():
        # Match full name or common abbreviations
        if set_name.lower() in title_lower:
            matched.append(set_id)
        # Also try set code
        pattern = SET_PATTERNS.get(set_id)
        if pattern and pattern.search(title_lower):
            matched.append(set_id)
    return list(set(matched))


def fetch_recent_posts(limit: int = 100) -> list[dict]:
    """Fetch recent posts from r/PokemonTCGDeals."""
    posts = []
    after = None

    while len(posts) < limit:
        params = {"limit": min(100, limit - len(posts)), "raw_json": 1}
        if after:
            params["after"] = after

        try:
            resp = requests.get(JSON_URL, headers=HEADERS, params=params, timeout=15)
            if resp.status_code == 429:
                log.warning("Reddit rate limited, backing off")
                time.sleep(10)
                continue
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            log.error(f"Reddit request failed: {e}")
            break

        children = data.get("data", {}).get("children", [])
        if not children:
            break

        for child in children:
            posts.append(child.get("data", {}))

        after = data.get("data", {}).get("after")
        if not after:
            break

        time.sleep(REQUEST_DELAY)

    log.info(f"Fetched {len(posts)} posts from r/PokemonTCGDeals")
    return posts


def search_set_deals(set_name: str, limit: int = 25) -> list[dict]:
    """Search the subreddit for deals mentioning a specific set."""
    params = {
        "q": set_name,
        "restrict_sr": "on",
        "sort": "new",
        "t": "month",
        "limit": limit,
        "raw_json": 1,
    }

    try:
        resp = requests.get(SEARCH_URL, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        children = data.get("data", {}).get("children", [])
        return [c.get("data", {}) for c in children]
    except requests.RequestException as e:
        log.error(f"Reddit search failed for '{set_name}': {e}")
        return []


def process_posts(posts: list[dict], set_names: dict[str, str]) -> list[RedditDeal]:
    """Process raw Reddit posts into structured deal objects."""
    deals = []

    for post in posts:
        title = post.get("title", "")
        if not title:
            continue

        # Skip removed/deleted posts
        if post.get("removed_by_category") or post.get("selftext") == "[deleted]":
            continue

        flair = (post.get("link_flair_text") or "").lower()
        url = post.get("url", "")
        permalink = post.get("permalink", "")
        reddit_url = f"https://www.reddit.com{permalink}" if permalink else ""

        # Check flair relevance (if flair exists)
        if flair and not any(f in flair for f in DEAL_FLAIRS) and "deal" not in flair:
            # Still include if it mentions a price or known store
            if not _extract_price(title) and not _detect_store(title, url):
                continue

        price = _extract_price(title)
        store = _detect_store(title, url)
        matched = _match_sets(title, set_names)

        deals.append(RedditDeal(
            title=title,
            url=url,
            reddit_url=reddit_url,
            score=post.get("score", 0),
            num_comments=post.get("num_comments", 0),
            flair=flair,
            created_utc=datetime.fromtimestamp(
                post.get("created_utc", 0), tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M UTC"),
            author=post.get("author", ""),
            price_mentioned=price,
            matched_sets=matched,
            source_store=store,
        ))

    # Sort by Reddit score (best deals bubble up)
    deals.sort(key=lambda d: d.score, reverse=True)
    return deals


def run(sets_json_path: str = "data/sets.json") -> dict:
    """
    Entry point. Returns:
      - recent_deals: All recent deals (last 100 posts)
      - by_set: Deals grouped by matched set ID
      - top_deals: Highest-upvoted deals (score >= 20)
    """
    global SET_PATTERNS

    with open(sets_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    set_names = {}
    for s in data["sets"]:
        set_names[s["id"]] = s["name"]
        # Build regex pattern for abbreviations and variations
        name = s["name"].lower()
        code = s.get("set_code", "").lower()
        patterns = [re.escape(name)]
        if code:
            patterns.append(re.escape(code))
        # Common abbreviations
        if "pokémon" in name or "pokemon" in name:
            patterns.append(name.replace("pokémon", "pokemon"))
        SET_PATTERNS[s["id"]] = re.compile("|".join(patterns))

    log.info("=== Reddit r/PokemonTCGDeals ===")

    # Fetch recent posts
    posts = fetch_recent_posts(limit=100)
    deals = process_posts(posts, set_names)

    # Also do targeted searches for each set
    for s in data["sets"]:
        time.sleep(REQUEST_DELAY)
        set_posts = search_set_deals(s["name"], limit=10)
        set_deals = process_posts(set_posts, set_names)
        # Merge without duplicates
        existing_urls = {d.url for d in deals}
        for d in set_deals:
            if d.url not in existing_urls:
                deals.append(d)
                existing_urls.add(d.url)

    # Organize output
    by_set = {}
    for deal in deals:
        for sid in deal.matched_sets:
            if sid not in by_set:
                by_set[sid] = []
            by_set[sid].append(asdict(deal))

    top_deals = [asdict(d) for d in deals if d.score >= 20]
    recent_deals = [asdict(d) for d in deals[:50]]

    log.info(f"  Total deals: {len(deals)}")
    log.info(f"  Top deals (score>=20): {len(top_deals)}")
    log.info(f"  Sets matched: {len(by_set)}")

    return {
        "recent_deals": recent_deals,
        "by_set": by_set,
        "top_deals": top_deals,
    }


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2))
