"""
Scoring module — computes a 0-100 Pack Value Score for each tracked set.

Components (weights configurable via config.json):
  1. Cost efficiency:  lower price-per-pack → higher score
  2. Chase magnitude:  higher top-card value → higher score
  3. Pull odds:        smaller "1 in N" → higher score (better odds)
  4. Hit density:      more chase cards per total set size → higher score

Also computes auxiliary metrics:
  - Expected $ value per pack opened
  - Average packs needed to pull a $50+ card
  - ROI per ETB at current prices
"""

import json
import re
import logging
from pathlib import Path

PRODUCT_LABELS = {
    "booster-pack": "Booster Pack",
    "elite-trainer-box": "Elite Trainer Box",
    "booster-bundle": "Booster Bundle",
    "booster-box": "Booster Box",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _parse_pull_rate(rate_str: str) -> float | None:
    """Parse '1 in N' string into N (float). Returns None if unparseable."""
    match = re.search(r"1\s+in\s+([\d,.]+)", rate_str)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _normalize(values: list[float], invert: bool = False) -> list[float]:
    """
    Min-max normalize a list of values to 0-100 range.
    If invert=True, lower raw values get higher normalized scores.
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [50.0] * len(values)
    if invert:
        return [100.0 * (hi - v) / (hi - lo) for v in values]
    else:
        return [100.0 * (v - lo) / (hi - lo) for v in values]


def compute_scores(sets_data: list[dict], prices_data: dict, config: dict) -> list[dict]:
    """
    Compute Pack Value Score and auxiliary metrics for each set.

    Args:
        sets_data: List of set dicts from sets.json
        prices_data: Pricing data from prices.json
        config: Config dict with scoring_weights and thresholds

    Returns:
        List of scored set dicts, sorted by score descending.
    """
    weights = config["scoring_weights"]
    thresholds = config.get("thresholds", {})
    default_msrp = thresholds.get("default_pack_msrp_usd", 4.49)
    high_value_threshold = thresholds.get("high_value_card_usd", 50)

    tcg = prices_data.get("tcgplayer", {})
    ebay = prices_data.get("ebay", {})

    # First pass: gather raw metrics for each set
    raw = []
    for s in sets_data:
        sid = s["id"]

        # --- Price per pack (find best deal across all product types) ---
        # Packs per product type and minimum sane prices
        PACKS_PER = {"booster-pack": 1, "booster-bundle": 6, "elite-trainer-box": 9, "booster-box": 36}
        MIN_PRICE = {"booster-pack": 1, "booster-bundle": 15, "elite-trainer-box": 20, "booster-box": 40}

        pack_price = default_msrp
        best_deal_product = "booster-pack"
        best_deal_total = default_msrp
        best_deal_source = ""

        tcg_set = tcg.get(sid, {})
        ebay_set = ebay.get(sid, {})
        gn = prices_data.get("gamenerdz", {})
        gn_set = gn.get(sid, {})
        amz = prices_data.get("amazon", {})
        amz_set = amz.get(sid, {})

        def _check_per_pack(total_price, packs, product_type, source):
            nonlocal pack_price, best_deal_product, best_deal_total, best_deal_source
            min_p = MIN_PRICE.get(product_type, 1)
            if total_price and total_price >= min_p and packs > 0:
                per_pack = total_price / packs
                if per_pack < pack_price:
                    pack_price = per_pack
                    best_deal_product = product_type
                    best_deal_total = total_price
                    best_deal_source = source

        # Check all product types across all sources
        for pt, packs in PACKS_PER.items():
            # TCGPlayer
            tcg_pt = tcg_set.get(pt, {})
            if tcg_pt.get("low_price_usd"):
                _check_per_pack(tcg_pt["low_price_usd"], packs, pt, "TCGPlayer")

            # GameNerdz
            for gn_prod in gn_set.get(pt, []):
                if gn_prod.get("price_usd") and gn_prod.get("in_stock", True):
                    _check_per_pack(gn_prod["price_usd"], packs, pt, "GameNerdz")

            # Amazon
            for amz_prod in amz_set.get(pt, []):
                if amz_prod.get("price_usd"):
                    _check_per_pack(amz_prod["price_usd"], packs, pt, "Amazon")

        # eBay (only has booster_pack data)
        ebay_pack = ebay_set.get("booster_pack", {}).get("sold", {})
        if ebay_pack.get("median_price_usd"):
            _check_per_pack(ebay_pack["median_price_usd"], 1, "booster-pack", "eBay")
        for amz_prod in amz_set.get("booster-pack", []):
            if amz_prod.get("price_usd"):
                pack_price = min(pack_price, amz_prod["price_usd"])

        # --- Top chase card value ---
        chase_cards = s.get("top_chase_cards", [])
        top_chase_value = max((c.get("estimated_value_usd", 0) for c in chase_cards), default=0)

        # Update chase values from live eBay data if available
        ebay_singles = ebay_set.get("chase_singles", {})
        for card in chase_cards:
            card_name = card["name"]
            if card_name in ebay_singles:
                sold = ebay_singles[card_name].get("sold", {})
                if sold.get("median_price_usd"):
                    card["live_value_usd"] = sold["median_price_usd"]
                    top_chase_value = max(top_chase_value, sold["median_price_usd"])

        # --- Pull odds (1 in N for top chase) ---
        pull_rate_str = s.get("pull_rates", {}).get("top_chase_specific", "")
        top_chase_n = _parse_pull_rate(pull_rate_str)
        if top_chase_n is None:
            top_chase_n = 500  # Conservative fallback

        # --- Hit density (chase cards / total set size) ---
        total_cards = s.get("total_cards", 200)
        num_chase = len(chase_cards)
        hit_density = num_chase / total_cards if total_cards > 0 else 0

        # --- Auxiliary metrics ---
        # Expected value per pack = sum(card_value / pull_rate) for each chase
        expected_value = 0.0
        for card in chase_cards:
            card_value = card.get("live_value_usd", card.get("estimated_value_usd", 0))
            # Estimate specific pull rate from any_chase_rare rate + number of chases
            any_chase_str = s.get("pull_rates", {}).get("any_chase_rare", "")
            any_chase_n = _parse_pull_rate(any_chase_str)
            if any_chase_n and num_chase > 0:
                specific_n = any_chase_n * num_chase
            else:
                specific_n = top_chase_n
            if specific_n > 0:
                expected_value += card_value / specific_n

        # Packs to $50+ card: using the any_chase_rare rate
        any_chase_str = s.get("pull_rates", {}).get("any_chase_rare", "")
        any_chase_n = _parse_pull_rate(any_chase_str)
        # Find how many chase cards are worth $50+
        high_value_count = sum(
            1 for c in chase_cards
            if c.get("live_value_usd", c.get("estimated_value_usd", 0)) >= high_value_threshold
        )
        if any_chase_n and high_value_count > 0 and num_chase > 0:
            packs_to_50 = any_chase_n * (num_chase / high_value_count)
        else:
            packs_to_50 = None

        # ROI per ETB (typically 9 packs in SV era, 8 in SWSH)
        packs_per_etb = 9 if s.get("release_date", "") >= "2023-03-31" else 8
        etb_price = default_msrp * packs_per_etb * 2.5  # ETBs ~2.5x pack cost
        tcg_etb = tcg_set.get("elite-trainer-box", {})
        if tcg_etb.get("low_price_usd"):
            etb_price = tcg_etb["low_price_usd"]
        etb_ev = expected_value * packs_per_etb
        etb_roi = ((etb_ev - etb_price) / etb_price * 100) if etb_price > 0 else 0

        # --- Active deals (find cheapest across all sources) ---
        cheapest_pack = None

        def _check_cheaper(listing):
            nonlocal cheapest_pack
            if listing and listing.get("price_usd"):
                if cheapest_pack is None or listing["price_usd"] < cheapest_pack.get("price_usd", 999):
                    cheapest_pack = listing

        # eBay
        pack_active = ebay_set.get("booster_pack", {}).get("active_listings", [])
        if pack_active:
            _check_cheaper(pack_active[0])
        # TCGPlayer
        tcg_cheapest = tcg_set.get("booster-pack", {}).get("cheapest_listings", [])
        if tcg_cheapest:
            _check_cheaper(tcg_cheapest[0])
        # GameNerdz
        for gn_prod in gn_set.get("booster-pack", []):
            if gn_prod.get("in_stock") and gn_prod.get("price_usd"):
                _check_cheaper({"title": gn_prod.get("title", ""), "price_usd": gn_prod["price_usd"],
                                "url": gn_prod.get("url", ""), "seller": "GameNerdz"})
        # Amazon
        for amz_prod in amz_set.get("booster-pack", []):
            if amz_prod.get("price_usd"):
                _check_cheaper({"title": amz_prod.get("title", ""), "price_usd": amz_prod["price_usd"],
                                "url": amz_prod.get("url", ""), "seller": "Amazon"})
        # Pokemon Center (MSRP, but in-stock is notable)
        pc = prices_data.get("pokemoncenter", {})
        pc_set = pc.get(sid, {})
        for pc_prod in pc_set.get("booster-pack", []):
            if pc_prod.get("in_stock") and pc_prod.get("price_usd"):
                _check_cheaper({"title": pc_prod.get("title", ""), "price_usd": pc_prod["price_usd"],
                                "url": pc_prod.get("url", ""), "seller": "Pokemon Center"})

        raw.append({
            "set": s,
            "pack_price": pack_price,
            "best_deal_product": best_deal_product,
            "best_deal_total": round(best_deal_total, 2),
            "best_deal_source": best_deal_source,
            "top_chase_value": top_chase_value,
            "top_chase_n": top_chase_n,
            "hit_density": hit_density,
            "expected_value_per_pack": round(expected_value, 2),
            "packs_to_50_card": round(packs_to_50) if packs_to_50 else None,
            "etb_roi_pct": round(etb_roi, 1),
            "etb_price": round(etb_price, 2),
            "cheapest_pack_listing": cheapest_pack,
        })

    # Second pass: normalize each component across all sets
    pack_prices = [r["pack_price"] for r in raw]
    chase_values = [r["top_chase_value"] for r in raw]
    pull_ns = [r["top_chase_n"] for r in raw]
    densities = [r["hit_density"] for r in raw]

    norm_cost = _normalize(pack_prices, invert=True)       # Lower = better
    norm_chase = _normalize(chase_values, invert=False)     # Higher = better
    norm_odds = _normalize(pull_ns, invert=True)            # Lower N = better
    norm_density = _normalize(densities, invert=False)      # Higher = better

    # Compute weighted score
    results = []
    for i, r in enumerate(raw):
        score = (
            weights["cost_efficiency"] * norm_cost[i]
            + weights["chase_magnitude"] * norm_chase[i]
            + weights["pull_odds"] * norm_odds[i]
            + weights["hit_density"] * norm_density[i]
        )
        score = round(min(100, max(0, score)), 1)

        s = r["set"]
        results.append({
            "id": s["id"],
            "name": s["name"],
            "set_code": s.get("set_code", ""),
            "release_date": s.get("release_date", ""),
            "set_type": s.get("set_type", ""),
            "in_print": s.get("in_print", False),
            "in_print_note": s.get("in_print_note", ""),
            "total_cards": s.get("total_cards", 0),
            "pack_value_score": score,
            "component_scores": {
                "cost_efficiency": round(norm_cost[i], 1),
                "chase_magnitude": round(norm_chase[i], 1),
                "pull_odds": round(norm_odds[i], 1),
                "hit_density": round(norm_density[i], 1),
            },
            "pack_price_usd": r["pack_price"],
            "best_deal": {
                "product": r["best_deal_product"],
                "total_price": r["best_deal_total"],
                "per_pack": r["pack_price"],
                "source": r["best_deal_source"],
                "label": PRODUCT_LABELS.get(r["best_deal_product"], r["best_deal_product"]),
            },
            "top_chase_value_usd": r["top_chase_value"],
            "top_chase_card": s["top_chase_cards"][0]["name"] if s.get("top_chase_cards") else "",
            "top_chase_card_number": s["top_chase_cards"][0].get("card_number", "") if s.get("top_chase_cards") else "",
            "pull_rate_top_chase": s.get("pull_rates", {}).get("top_chase_specific", ""),
            "expected_value_per_pack": r["expected_value_per_pack"],
            "packs_to_50_card": r["packs_to_50_card"],
            "etb_price_usd": r["etb_price"],
            "etb_roi_pct": r["etb_roi_pct"],
            "num_chase_cards": len(s.get("top_chase_cards", [])),
            "chase_cards": s.get("top_chase_cards", []),
            "cheapest_pack_listing": r["cheapest_pack_listing"],
        })

    results.sort(key=lambda x: x["pack_value_score"], reverse=True)

    # Generate top pick justification
    if results:
        top = results[0]
        top["is_top_pick"] = True
        reasons = []
        if top["component_scores"]["cost_efficiency"] >= 70:
            reasons.append(f"affordable at ${top['pack_price_usd']:.2f}/pack")
        if top["component_scores"]["chase_magnitude"] >= 70:
            reasons.append(f"top chase worth ${top['top_chase_value_usd']:.0f}")
        if top["component_scores"]["pull_odds"] >= 70:
            reasons.append(f"favorable pull rate ({top['pull_rate_top_chase']})")
        if top["component_scores"]["hit_density"] >= 70:
            reasons.append(f"high hit density ({top['num_chase_cards']} chases in {top['total_cards']} cards)")
        if not reasons:
            reasons.append("best overall balance of cost, chase value, and pull rates")
        top["top_pick_reason"] = "; ".join(reasons)

    log.info(f"Scored {len(results)} sets. Top pick: {results[0]['name'] if results else 'N/A'}")
    return results


def run(
    sets_json_path: str = "data/sets.json",
    prices_json_path: str = "data/prices.json",
    config_path: str = "config.json",
) -> list[dict]:
    """Entry point — load data, compute scores, return results."""
    with open(sets_json_path, "r", encoding="utf-8") as f:
        sets_data = json.load(f)["sets"]
    with open(prices_json_path, "r", encoding="utf-8") as f:
        prices_data = json.load(f)
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    return compute_scores(sets_data, prices_data, config)


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2))
