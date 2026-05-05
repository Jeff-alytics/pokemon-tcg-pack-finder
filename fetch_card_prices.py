"""
Fetch all cards worth $10+ (raw/ungraded) from target sets using Pokemon TCG API.
The API includes TCGPlayer market prices.
"""

import json
import time
from pokemontcgsdk import Card

# Map: our set_id -> API set.id(s)
SETS = {
    "pokemon-go": ["pgo"],
    "crown-zenith": ["swsh12pt5", "swsh12pt5gg"],
    "scarlet-violet-base": ["sv1"],
    "paldea-evolved": ["sv2"],
    "obsidian-flames": ["sv3"],
    "pokemon-151": ["sv3pt5"],
    "paradox-rift": ["sv4"],
    "paldean-fates": ["sv4pt5"],
    "temporal-forces": ["sv5"],
    "twilight-masquerade": ["sv6"],
    "shrouded-fable": ["sv6pt5"],
    "stellar-crown": ["sv7"],
    "surging-sparks": ["sv8"],
    "prismatic-evolutions": ["sv8pt5"],
    "journey-together": ["sv9"],
    "destined-rivals": ["sv10"],
    "mega-evolution": ["me1"],
    "ascended-heroes": ["me2pt5"],
    "perfect-order": ["me3"],
    # "chaos-rising": ["me4"],  # May not be in API yet
}

MIN_VALUE = 10.0
results = []

def get_best_price(card):
    """Extract the best market price from TCGPlayer data."""
    if not card.tcgplayer or not card.tcgplayer.prices:
        return None

    prices = card.tcgplayer.prices
    best = None

    # Check all price variants
    for variant_name in ['holofoil', 'reverseHolofoil', 'normal', '1stEditionHolofoil',
                          '1stEditionNormal', 'unlimitedHolofoil']:
        variant = getattr(prices, variant_name, None) if hasattr(prices, variant_name) else None
        if variant is None:
            # Try dict access
            if isinstance(prices, dict):
                variant = prices.get(variant_name)
            continue

        market = getattr(variant, 'market', None)
        if market and (best is None or market > best):
            best = market

    return best

def get_rarity_label(card):
    """Create a label suffix from rarity."""
    r = (card.rarity or "").lower()
    if "special illustration" in r or "sir" in r:
        return " (SIR)"
    if "illustration rare" in r and "special" not in r:
        return " (IR)"
    if "hyper" in r:
        return " (HR)"
    if "ultra" in r:
        return " (UR)"
    if "secret" in r:
        return " (Secret)"
    if "full art" in r or "art rare" in r:
        return " (AR)"
    if "mega hyper" in r:
        return " (MHR)"
    if "shiny" in r:
        return " (Shiny)"
    if "gold" in r:
        return " (Gold)"
    return ""

for set_slug, api_ids in SETS.items():
    for api_id in api_ids:
        print(f"Fetching {set_slug} ({api_id})...")
        page = 1
        while True:
            try:
                cards = Card.where(q=f'set.id:{api_id}', page=page, pageSize=250)
            except Exception as e:
                print(f"  Error on page {page}: {e}")
                time.sleep(3)
                try:
                    cards = Card.where(q=f'set.id:{api_id}', page=page, pageSize=250)
                except Exception as e2:
                    print(f"  Retry failed: {e2}")
                    break

            if not cards:
                break

            for card in cards:
                price = get_best_price(card)
                if price is not None and price >= MIN_VALUE:
                    label = get_rarity_label(card)
                    name = card.name + label
                    results.append({
                        "set_id": set_slug,
                        "name": name,
                        "number": card.number + "/" + str(card.set.printedTotal if hasattr(card.set, 'printedTotal') else card.set.total),
                        "value": round(price, 2),
                        "rarity": card.rarity or "Unknown",
                        "api_set": api_id,
                    })
                    print(f"  ${price:>8.2f}  {name} ({card.number})")

                # Check for Mega Starmie ex regardless of value
                if "starmie" in card.name.lower() and "mega" in card.name.lower():
                    # Add if not already added
                    already = any(r["number"].startswith(card.number) and r["set_id"] == set_slug for r in results)
                    if not already:
                        label = get_rarity_label(card)
                        name = card.name + label
                        results.append({
                            "set_id": set_slug,
                            "name": name,
                            "number": card.number + "/" + str(card.set.printedTotal if hasattr(card.set, 'printedTotal') else card.set.total),
                            "value": round(price, 2) if price else 0,
                            "rarity": card.rarity or "Unknown",
                            "api_set": api_id,
                            "note": "included regardless of value (Mega Starmie ex)"
                        })
                        print(f"  ${price or 0:>8.2f}  {name} ({card.number}) [MEGA STARMIE - forced include]")

            if len(cards) < 250:
                break
            page += 1
            time.sleep(0.5)

    time.sleep(0.3)

# Also try chaos-rising
print("Trying chaos-rising (me4)...")
try:
    cards = Card.where(q='set.id:me4', page=1, pageSize=250)
    if cards:
        for card in cards:
            price = get_best_price(card)
            if price is not None and price >= MIN_VALUE:
                label = get_rarity_label(card)
                name = card.name + label
                results.append({
                    "set_id": "chaos-rising",
                    "name": name,
                    "number": card.number + "/" + str(card.set.printedTotal if hasattr(card.set, 'printedTotal') else card.set.total),
                    "value": round(price, 2),
                    "rarity": card.rarity or "Unknown",
                    "api_set": "me4",
                })
                print(f"  ${price:>8.2f}  {name} ({card.number})")
            if "starmie" in card.name.lower() and "mega" in card.name.lower():
                already = any(r["number"].startswith(card.number) and r["set_id"] == "chaos-rising" for r in results)
                if not already:
                    label = get_rarity_label(card)
                    name = card.name + label
                    results.append({
                        "set_id": "chaos-rising",
                        "name": name,
                        "number": card.number + "/" + str(card.set.printedTotal if hasattr(card.set, 'printedTotal') else card.set.total),
                        "value": round(price, 2) if price else 0,
                        "rarity": card.rarity or "Unknown",
                        "api_set": "me4",
                        "note": "included regardless of value (Mega Starmie ex)"
                    })
                    print(f"  ${price or 0:>8.2f}  {name} ({card.number}) [MEGA STARMIE - forced include]")
    else:
        print("  No cards found for me4")
except Exception as e:
    print(f"  me4 not in API yet: {e}")

# Sort by value descending
results.sort(key=lambda x: -x["value"])

# Clean output - remove api_set field
output = []
for r in results:
    entry = {
        "set_id": r["set_id"],
        "name": r["name"],
        "number": r["number"],
        "value": r["value"]
    }
    if "note" in r:
        entry["note"] = r["note"]
    output.append(entry)

print(f"\n=== TOTAL: {len(output)} cards worth $10+ ===")
print(f"Sets covered: {len(set(r['set_id'] for r in output))}")

with open("data/card_values.json", "w") as f:
    json.dump(output, f, indent=2)

print("Saved to data/card_values.json")
