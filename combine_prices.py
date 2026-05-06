"""
Combine API-sourced card prices with manually researched data for newer sets.
"""
import json

# Load the API-sourced data
with open("data/card_values.json") as f:
    api_data = json.load(f)

# Manually researched data for sets where TCGPlayer API has no pricing
supplement = [
    # === ASCENDED HEROES (me2pt5) - Released Jan 30, 2026 ===
    # Prices from sets.json research + Japanese market + early TCGPlayer listings

    # SIRs (Special Illustration Rare) - cards 272-293
    {"set_id": "ascended-heroes", "name": "Mega Gengar ex (SIR)", "number": "284/217", "value": 1000},
    {"set_id": "ascended-heroes", "name": "Mega Dragonite ex (SIR)", "number": "290/217", "value": 690},
    {"set_id": "ascended-heroes", "name": "Pikachu ex (SIR)", "number": "276/217", "value": 600},
    {"set_id": "ascended-heroes", "name": "Team Rocket's Mewtwo ex (SIR)", "number": "281/217", "value": 380},
    {"set_id": "ascended-heroes", "name": "Pikachu ex (SIR #2)", "number": "277/217", "value": 350},
    {"set_id": "ascended-heroes", "name": "Lillie's Clefairy ex (SIR)", "number": "280/217", "value": 250},
    {"set_id": "ascended-heroes", "name": "N's Zoroark ex (SIR)", "number": "286/217", "value": 180},
    {"set_id": "ascended-heroes", "name": "Iono's Bellibolt ex (SIR)", "number": "279/217", "value": 120},
    {"set_id": "ascended-heroes", "name": "Mega Meganium ex (SIR)", "number": "272/217", "value": 100},
    {"set_id": "ascended-heroes", "name": "Marnie's Grimmsnarl ex (SIR)", "number": "287/217", "value": 90},
    {"set_id": "ascended-heroes", "name": "Mega Feraligatr ex (SIR)", "number": "274/217", "value": 80},
    {"set_id": "ascended-heroes", "name": "Steven's Metagross ex (SIR)", "number": "289/217", "value": 75},
    {"set_id": "ascended-heroes", "name": "Mega Diancie ex (SIR)", "number": "282/217", "value": 70},
    {"set_id": "ascended-heroes", "name": "Mega Froslass ex (SIR)", "number": "275/217", "value": 65},
    {"set_id": "ascended-heroes", "name": "Mega Emboar ex (SIR)", "number": "273/217", "value": 60},
    {"set_id": "ascended-heroes", "name": "Iris's Fighting Spirit (SIR)", "number": "292/217", "value": 55},
    {"set_id": "ascended-heroes", "name": "Mega Eelektross ex (SIR)", "number": "278/217", "value": 45},
    {"set_id": "ascended-heroes", "name": "Canari (SIR)", "number": "291/217", "value": 45},
    {"set_id": "ascended-heroes", "name": "Mega Hawlucha ex (SIR)", "number": "283/217", "value": 40},
    {"set_id": "ascended-heroes", "name": "Surfer (SIR)", "number": "293/217", "value": 40},
    {"set_id": "ascended-heroes", "name": "Mega Scrafty ex (SIR)", "number": "285/217", "value": 35},
    {"set_id": "ascended-heroes", "name": "Fezandipiti ex (SIR)", "number": "288/217", "value": 30},

    # MHRs (Mega Hyper Rare)
    {"set_id": "ascended-heroes", "name": "Mega Charizard Y ex (MHR)", "number": "294/217", "value": 445},
    {"set_id": "ascended-heroes", "name": "Mega Dragonite ex (MHR)", "number": "295/217", "value": 300},

    # ARs (Alternate Art / early UR style) 265-271
    {"set_id": "ascended-heroes", "name": "Mega Gengar ex (AR)", "number": "269/217", "value": 50},
    {"set_id": "ascended-heroes", "name": "Mega Dragonite ex (AR)", "number": "271/217", "value": 35},
    {"set_id": "ascended-heroes", "name": "Mega Froslass ex (AR)", "number": "265/217", "value": 25},
    {"set_id": "ascended-heroes", "name": "Mega Diancie ex (AR)", "number": "267/217", "value": 25},
    {"set_id": "ascended-heroes", "name": "Mega Eelektross ex (AR)", "number": "266/217", "value": 18},
    {"set_id": "ascended-heroes", "name": "Mega Hawlucha ex (AR)", "number": "268/217", "value": 15},
    {"set_id": "ascended-heroes", "name": "Mega Scrafty ex (AR)", "number": "270/217", "value": 12},

    # URs (Ultra Rare) worth $10+
    {"set_id": "ascended-heroes", "name": "Ultra Ball (UR)", "number": "264/217", "value": 15},
    {"set_id": "ascended-heroes", "name": "Mega Audino ex (UR)", "number": "253/217", "value": 15},
    {"set_id": "ascended-heroes", "name": "Boss's Orders (UR)", "number": "256/217", "value": 12},
    {"set_id": "ascended-heroes", "name": "Counter Gain (UR)", "number": "259/217", "value": 12},
    {"set_id": "ascended-heroes", "name": "Canari (UR)", "number": "257/217", "value": 10},
    {"set_id": "ascended-heroes", "name": "Cheren (UR)", "number": "258/217", "value": 10},
    {"set_id": "ascended-heroes", "name": "Glass Trumpet (UR)", "number": "260/217", "value": 10},
    {"set_id": "ascended-heroes", "name": "Sprigatito ex (UR)", "number": "251/217", "value": 10},

    # IRs (Illustration Rare) worth $10+ - cards 218-250
    {"set_id": "ascended-heroes", "name": "Team Rocket's Mimikyu (IR)", "number": "238/217", "value": 40},
    {"set_id": "ascended-heroes", "name": "Iono's Wattrel (IR)", "number": "231/217", "value": 25},
    {"set_id": "ascended-heroes", "name": "Cynthia's Spiritomb (IR)", "number": "244/217", "value": 22},
    {"set_id": "ascended-heroes", "name": "Marill (IR)", "number": "232/217", "value": 20},
    {"set_id": "ascended-heroes", "name": "Psyduck (IR)", "number": "226/217", "value": 20},
    {"set_id": "ascended-heroes", "name": "Togekiss (IR)", "number": "235/217", "value": 18},
    {"set_id": "ascended-heroes", "name": "Dreepy (IR)", "number": "247/217", "value": 18},
    {"set_id": "ascended-heroes", "name": "Scorbunny (IR)", "number": "225/217", "value": 15},
    {"set_id": "ascended-heroes", "name": "Misdreavus (IR)", "number": "233/217", "value": 15},
    {"set_id": "ascended-heroes", "name": "Drakloak (IR)", "number": "248/217", "value": 15},
    {"set_id": "ascended-heroes", "name": "Hop's Trevenant (IR)", "number": "237/217", "value": 15},
    {"set_id": "ascended-heroes", "name": "Ethan's Magcargo (IR)", "number": "222/217", "value": 12},
    {"set_id": "ascended-heroes", "name": "Weavile (IR)", "number": "228/217", "value": 12},
    {"set_id": "ascended-heroes", "name": "Banette (IR)", "number": "234/217", "value": 12},
    {"set_id": "ascended-heroes", "name": "Galarian Obstagoon (IR)", "number": "245/217", "value": 12},
    {"set_id": "ascended-heroes", "name": "Larry's Staraptor (IR)", "number": "249/217", "value": 12},
    {"set_id": "ascended-heroes", "name": "Budew (IR)", "number": "221/217", "value": 10},
    {"set_id": "ascended-heroes", "name": "Slurpuff (IR)", "number": "236/217", "value": 10},
    {"set_id": "ascended-heroes", "name": "Mawile (IR)", "number": "246/217", "value": 10},
    {"set_id": "ascended-heroes", "name": "Fan Rotom (IR)", "number": "250/217", "value": 10},
    {"set_id": "ascended-heroes", "name": "Snorunt (IR)", "number": "227/217", "value": 10},

    # === PERFECT ORDER (me3) - Released Mar 27, 2026 ===
    # MHR
    {"set_id": "perfect-order", "name": "Mega Zygarde ex (MHR)", "number": "124/088", "value": 200},
    # SIRs
    {"set_id": "perfect-order", "name": "Rosa's Encouragement (SIR)", "number": "123/088", "value": 152},
    {"set_id": "perfect-order", "name": "Meowth ex (SIR)", "number": "121/088", "value": 140},
    {"set_id": "perfect-order", "name": "Mega Zygarde ex (SIR)", "number": "120/088", "value": 80},
    {"set_id": "perfect-order", "name": "Jacinthe (SIR)", "number": "122/088", "value": 60},
    {"set_id": "perfect-order", "name": "Mega Starmie ex (SIR)", "number": "118/088", "value": 55},
    {"set_id": "perfect-order", "name": "Mega Clefable ex (SIR)", "number": "119/088", "value": 50},
    # URs worth $10+
    {"set_id": "perfect-order", "name": "Rosa's Encouragement (UR)", "number": "114/088", "value": 20},
    {"set_id": "perfect-order", "name": "Meowth ex (UR)", "number": "107/088", "value": 18},
    {"set_id": "perfect-order", "name": "Mega Starmie ex (UR)", "number": "102/088", "value": 15},
    {"set_id": "perfect-order", "name": "Mega Zygarde ex (UR)", "number": "104/088", "value": 15},
    {"set_id": "perfect-order", "name": "Mega Clefable ex (UR)", "number": "103/088", "value": 12},
    {"set_id": "perfect-order", "name": "Yveltal ex (UR)", "number": "105/088", "value": 12},
    {"set_id": "perfect-order", "name": "Jacinthe (UR)", "number": "110/088", "value": 10},
    {"set_id": "perfect-order", "name": "Mega Skarmory ex (UR)", "number": "106/088", "value": 10},
    {"set_id": "perfect-order", "name": "Sacred Ash (UR)", "number": "115/088", "value": 10},
    # IRs worth $10+
    {"set_id": "perfect-order", "name": "Clefairy (IR)", "number": "94/088", "value": 18},
    {"set_id": "perfect-order", "name": "Rowlet (IR)", "number": "90/088", "value": 15},
    {"set_id": "perfect-order", "name": "Dedenne (IR)", "number": "93/088", "value": 12},
    {"set_id": "perfect-order", "name": "Espurr (IR)", "number": "95/088", "value": 12},
    {"set_id": "perfect-order", "name": "Talonflame (IR)", "number": "91/088", "value": 10},
    {"set_id": "perfect-order", "name": "Raticate (IR)", "number": "99/088", "value": 10},
    # Mega Starmie base card (include regardless of value per user request)
    {"set_id": "perfect-order", "name": "Mega Starmie ex", "number": "21/088", "value": 3, "note": "included regardless of value (Mega Starmie ex)"},

    # === CHAOS RISING (me4) - UNRELEASED (May 22, 2026) - Pre-order estimates ===
    {"set_id": "chaos-rising", "name": "Mega Greninja ex (MHR)", "number": "122/086", "value": 250},
    {"set_id": "chaos-rising", "name": "Mega Greninja ex (SIR)", "number": "114/086", "value": 150},
    {"set_id": "chaos-rising", "name": "Mega Pyroar ex (SIR)", "number": "112/086", "value": 75},
    {"set_id": "chaos-rising", "name": "Mega Greninja ex (AR)", "number": "116/086", "value": 60},
    {"set_id": "chaos-rising", "name": "Mega Dragalge ex (SIR)", "number": "115/086", "value": 45},
    {"set_id": "chaos-rising", "name": "Mega Dragalge ex (AR)", "number": "118/086", "value": 20},
]

# Combine API data with supplement
combined = api_data + supplement

# Sort by value descending
combined.sort(key=lambda x: -x["value"])

# Deduplicate (same set_id + number)
seen = set()
deduped = []
for card in combined:
    key = (card["set_id"], card["number"])
    if key not in seen:
        seen.add(key)
        deduped.append(card)

print(f"Total cards: {len(deduped)}")
print(f"Sets covered: {len(set(c['set_id'] for c in deduped))}")
for sid in sorted(set(c["set_id"] for c in deduped)):
    count = sum(1 for c in deduped if c["set_id"] == sid)
    print(f"  {sid}: {count} cards")

# Save
with open("data/card_values.json", "w") as f:
    json.dump(deduped, f, indent=2)

print(f"\nSaved to data/card_values.json")
