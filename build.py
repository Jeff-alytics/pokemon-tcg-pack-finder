"""
Build pipeline — orchestrates scrapers, scoring, and alerts.

Usage:
  python build.py              # Full run: scrape + score + alert
  python build.py --score-only # Re-score from existing prices.json (no scraping)
  python build.py --dry-run    # Scrape but don't overwrite prices.json
"""

import argparse
import json
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SETS_JSON = DATA_DIR / "sets.json"
PRICES_JSON = DATA_DIR / "prices.json"
SCORED_JSON = DATA_DIR / "scored.json"
GRADED_JSON = DATA_DIR / "graded.json"
CONFIG_JSON = ROOT / "config.json"


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    log.info(f"Saved {path}")


def check_price_drift(old_prices: dict, new_prices: dict, config: dict) -> list[str]:
    """
    Compare new prices against old. Flag items where price drifted
    more than the configured threshold percentage.
    """
    threshold = config.get("thresholds", {}).get("price_drift_alert_pct", 50)
    warnings = []

    old_tcg = old_prices.get("tcgplayer", {})
    new_tcg = new_prices.get("tcgplayer", {})

    for set_id, new_products in new_tcg.items():
        old_products = old_tcg.get(set_id, {})
        for pt, new_data in new_products.items():
            old_data = old_products.get(pt, {})
            old_mid = old_data.get("mid_price_usd")
            new_mid = new_data.get("mid_price_usd")
            if old_mid and new_mid and old_mid > 0:
                drift_pct = abs(new_mid - old_mid) / old_mid * 100
                if drift_pct > threshold:
                    warnings.append(
                        f"DRIFT: {set_id}/{pt} mid price ${old_mid} -> ${new_mid} "
                        f"({drift_pct:.0f}% change, threshold {threshold}%)"
                    )

    return warnings


def _run_scraper(name: str, import_path: str, sets_path: str) -> dict:
    """Run a single scraper with error handling. Returns empty dict on failure."""
    log.info("")
    log.info("=" * 60)
    log.info(f"Running {name} scraper...")
    log.info("=" * 60)
    try:
        import importlib
        mod = importlib.import_module(import_path)
        return mod.run(sets_path)
    except Exception as e:
        log.error(f"{name} scraper failed: {e}")
        log.error("Continuing with remaining scrapers...")
        return {}


def run_scrapers() -> dict:
    """Run all scrapers and merge results."""
    sets_path = str(SETS_JSON)

    tcg_data = _run_scraper("TCGPlayer", "scrapers.tcgplayer_sealed", sets_path)
    ebay_data = _run_scraper("eBay", "scrapers.ebay_sold", sets_path)
    pc_data = _run_scraper("Pokemon Center", "scrapers.pokemoncenter", sets_path)
    gn_data = _run_scraper("GameNerdz", "scrapers.gamenerdz", sets_path)
    amz_data = _run_scraper("Amazon", "scrapers.amazon", sets_path)
    reddit_data = _run_scraper("Reddit Deals", "scrapers.reddit_deals", sets_path)

    return {
        "_meta": {
            "description": "Scraped pricing data — updated by the pipeline",
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "scraper_version": "2.0.0",
            "sources": ["tcgplayer", "ebay", "pokemoncenter", "gamenerdz", "amazon", "reddit"],
        },
        "tcgplayer": tcg_data,
        "ebay": ebay_data,
        "pokemoncenter": pc_data,
        "gamenerdz": gn_data,
        "amazon": amz_data,
        "reddit": reddit_data,
    }


def run_scoring() -> list[dict]:
    """Run the scoring module."""
    log.info("")
    log.info("=" * 60)
    log.info("Computing scores...")
    log.info("=" * 60)
    from scoring import run as score_run
    return score_run(str(SETS_JSON), str(PRICES_JSON), str(CONFIG_JSON))


def run_graded() -> dict:
    """Run the graded price scraper."""
    log.info("")
    log.info("=" * 60)
    log.info("Scraping graded card prices...")
    log.info("=" * 60)
    return _run_scraper("Graded Prices", "scrapers.graded_prices", str(SETS_JSON))


def run_alerts():
    """Run the alert evaluation and email."""
    log.info("")
    log.info("=" * 60)
    log.info("Evaluating deal alerts...")
    log.info("=" * 60)
    from alerts import run as alerts_run
    return alerts_run(str(PRICES_JSON), str(CONFIG_JSON))


def main():
    parser = argparse.ArgumentParser(description="Pokémon TCG Pack Finder build pipeline")
    parser.add_argument("--score-only", action="store_true", help="Re-score from existing prices.json")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but don't overwrite prices.json")
    parser.add_argument("--no-alerts", action="store_true", help="Skip deal alert evaluation")
    parser.add_argument("--with-graded", action="store_true", help="Include graded price scraper (slow, needs non-datacenter IP)")
    parser.add_argument("--force", action="store_true", help="Skip price drift check (use after fixing scraper data)")
    args = parser.parse_args()

    config = load_json(CONFIG_JSON)

    if not args.score_only:
        # Run scrapers
        new_prices = run_scrapers()

        if args.dry_run:
            log.info("\n[DRY RUN] Would save prices.json but skipping.")
            print(json.dumps(new_prices, indent=2, default=str)[:2000])
            return

        # Check for suspicious price drift
        if args.force:
            log.info("--force flag set, skipping drift check")
        elif PRICES_JSON.exists():
            old_prices = load_json(PRICES_JSON)
            if old_prices.get("_meta", {}).get("last_updated"):
                drift_warnings = check_price_drift(old_prices, new_prices, config)
                if drift_warnings:
                    log.warning("\n⚠️  PRICE DRIFT DETECTED:")
                    for w in drift_warnings:
                        log.warning(f"  {w}")
                    # In CI, this will cause the workflow to flag for review
                    # rather than auto-committing
                    flag_path = ROOT / ".price_drift_flag"
                    flag_path.write_text("\n".join(drift_warnings))
                    log.warning(f"  Drift warnings written to {flag_path}")

        save_json(PRICES_JSON, new_prices)

    # Run scoring
    scored = run_scoring()
    save_json(SCORED_JSON, {
        "_meta": {
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "num_sets": len(scored),
        },
        "sets": scored,
    })

    # Run graded price scraper (opt-in — eBay blocks datacenter IPs)
    if args.with_graded:
        graded = run_graded()
        save_json(GRADED_JSON, {
            "_meta": {
                "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "num_cards": len(graded),
            },
            "cards": graded,
        })
    else:
        log.info("\nSkipping graded scraper (use --with-graded to include, best run locally)")

    # Run alerts
    if not args.no_alerts:
        run_alerts()

    log.info("\n" + "=" * 60)
    log.info("BUILD COMPLETE")
    log.info(f"  Sets scored: {len(scored)}")
    if scored:
        log.info(f"  Top pick: {scored[0]['name']} (score: {scored[0]['pack_value_score']})")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
