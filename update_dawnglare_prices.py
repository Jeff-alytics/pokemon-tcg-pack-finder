"""
Update card_values.json with more current Dawnglare prices where available.
Dawnglare prices come directly from TCGPlayer and tend to be more current.
"""
import json

# Dawnglare prices scraped from pokemon.dawnglare.com/?p=chase
# These are the most current TCGPlayer market prices (as of May 2026)
dawnglare = {
    # SV01 - Scarlet & Violet Base
    ("scarlet-violet-base", "245/198"): 98.91,   # Gardevoir ex SIR
    ("scarlet-violet-base", "244/198"): 29.00,   # Miraidon ex SIR
    ("scarlet-violet-base", "247/198"): 25.00,   # Koraidon ex SIR
    ("scarlet-violet-base", "251/198"): 33.24,   # Miriam SIR
    ("scarlet-violet-base", "246/198"): 12.12,   # Great Tusk ex SIR
    ("scarlet-violet-base", "210/198"): 70.00,   # Drowzee IR
    ("scarlet-violet-base", "212/198"): 77.95,   # Kirlia IR
    ("scarlet-violet-base", "211/198"): 60.48,   # Ralts IR
    ("scarlet-violet-base", "204/198"): 56.20,   # Slowpoke IR
    ("scarlet-violet-base", "215/198"): 48.00,   # Riolu IR
    ("scarlet-violet-base", "206/198"): 38.00,   # Wiglett IR
    ("scarlet-violet-base", "213/198"): 29.82,   # Fidough IR
    ("scarlet-violet-base", "214/198"): 26.55,   # Greavard IR
    ("scarlet-violet-base", "203/198"): 18.36,   # Armarouge IR
    ("scarlet-violet-base", "208/198"): 17.00,   # Pachirisu IR
    ("scarlet-violet-base", "207/198"): 15.00,   # Dondozo IR
    ("scarlet-violet-base", "221/198"): 13.25,   # Starly IR
    ("scarlet-violet-base", "199/198"): 11.49,   # Tarountula IR
    ("scarlet-violet-base", "224/198"): 16.50,   # Arcanine ex UR
    ("scarlet-violet-base", "225/198"): 10.75,   # Gyarados ex UR
    ("scarlet-violet-base", "220/198"): 10.07,   # Kingambit IR

    # SV02 - Paldea Evolved
    ("paldea-evolved", "203/193"): 420.00,   # Magikarp IR
    ("paldea-evolved", "211/193"): 127.38,   # Raichu IR
    ("paldea-evolved", "226/193"): 124.85,   # Maushold IR
    ("paldea-evolved", "222/193"): 84.00,    # Tyranitar IR
    ("paldea-evolved", "269/193"): 74.84,    # Iono SIR
    ("paldea-evolved", "262/193"): 74.00,    # Tinkaton ex SIR
    ("paldea-evolved", "204/193"): 61.70,    # Marill IR
    ("paldea-evolved", "196/193"): 60.31,    # Sprigatito IR
    ("paldea-evolved", "201/193"): 55.00,    # Fuecoco IR
    ("paldea-evolved", "259/193"): 52.31,    # Chi-Yu ex SIR
    ("paldea-evolved", "212/193"): 47.59,    # Mismagius IR
    ("paldea-evolved", "217/193"): 44.75,    # Tinkatuff IR
    ("paldea-evolved", "256/193"): 38.69,    # Meowscarada ex SIR
    ("paldea-evolved", "258/193"): 37.21,    # Skeledirge ex SIR
    ("paldea-evolved", "216/193"): 33.78,    # Tinkatink IR
    ("paldea-evolved", "210/193"): 33.09,    # Baxcalibur IR
    ("paldea-evolved", "261/193"): 29.99,    # Chien-Pao ex SIR
    ("paldea-evolved", "219/193"): 28.09,    # Sudowoodo IR
    ("paldea-evolved", "194/193"): 28.00,    # Heracross IR
    ("paldea-evolved", "202/193"): 23.01,    # Crocalor IR
    ("paldea-evolved", "208/193"): 22.00,    # Frigibax IR
    ("paldea-evolved", "265/193"): 21.26,    # Boss's Orders SIR
    ("paldea-evolved", "205/193"): 20.58,    # Eiscue IR
    ("paldea-evolved", "197/193"): 20.18,    # Floragato IR
    ("paldea-evolved", "239/193"): 18.18,    # Dedenne ex UR
    ("paldea-evolved", "268/193"): 18.04,    # Grusha SIR
    ("paldea-evolved", "260/193"): 17.50,    # Quaquaval ex SIR
    ("paldea-evolved", "199/193"): 17.41,    # Fletchinder IR
    ("paldea-evolved", "206/193"): 17.38,    # Quaxly IR
    ("paldea-evolved", "270/193"): 16.55,    # Saguaro SIR
    ("paldea-evolved", "257/193"): 16.00,    # Wo-Chien ex SIR
    ("paldea-evolved", "209/193"): 15.99,    # Arctibax IR
    ("paldea-evolved", "218/193"): 15.43,    # Paldean Tauros IR
    ("paldea-evolved", "200/193"): 15.00,    # Pyroar IR
    ("paldea-evolved", "221/193"): 14.09,    # Paldean Wooper IR
    ("paldea-evolved", "248/193"): 13.73,    # Boss's Orders UR
    ("paldea-evolved", "228/193"): 12.93,    # Farigiraf IR
    ("paldea-evolved", "213/193"): 12.79,    # Gothorita IR
    ("paldea-evolved", "278/193"): 12.71,    # Basic Grass Energy HR
    ("paldea-evolved", "254/193"): 12.40,    # Iono UR
    ("paldea-evolved", "263/193"): 12.20,    # Ting-Lu ex SIR
    ("paldea-evolved", "195/193"): 12.01,    # Tropius IR
    ("paldea-evolved", "264/193"): 11.00,    # Squawkabilly ex SIR
    ("paldea-evolved", "227/193"): 11.00,    # Flamigo IR
    ("paldea-evolved", "225/193"): 11.13,    # Rookidee IR
    ("paldea-evolved", "214/193"): 10.52,    # Sandygast IR
    ("paldea-evolved", "198/193"): 10.48,    # Bramblin IR
    ("paldea-evolved", "266/193"): 10.73,    # Dendra SIR

    # SV03 - Obsidian Flames
    ("obsidian-flames", "223/197"): 112.22,  # Charizard ex SIR
    ("obsidian-flames", "199/197"): 49.88,   # Ninetales IR
    ("obsidian-flames", "228/197"): 49.99,   # Charizard ex HR
    ("obsidian-flames", "202/197"): 45.17,   # Cleffa IR
    ("obsidian-flames", "198/197"): 29.77,   # Gloom IR
    ("obsidian-flames", "215/197"): 24.09,   # Charizard ex UR
    ("obsidian-flames", "225/197"): 21.01,   # Pidgeot ex SIR
    ("obsidian-flames", "205/197"): 17.97,   # Scizor IR
    ("obsidian-flames", "207/197"): 16.94,   # Pidgey IR
    ("obsidian-flames", "209/197"): 15.49,   # Lechonk IR
    ("obsidian-flames", "208/197"): 11.50,   # Pidgeotto IR
    ("obsidian-flames", "204/197"): 11.00,   # Houndour IR

    # SV 151
    ("pokemon-151", "199/165"): 475.00,   # Charizard ex SIR
    ("pokemon-151", "200/165"): 174.00,   # Blastoise ex SIR
    ("pokemon-151", "198/165"): 150.00,   # Venusaur ex SIR
    ("pokemon-151", "202/165"): 120.00,   # Zapdos ex SIR
    ("pokemon-151", "168/165"): 119.99,   # Charmander IR
    ("pokemon-151", "170/165"): 118.00,   # Squirtle IR
    ("pokemon-151", "173/165"): 99.99,    # Pikachu IR
    ("pokemon-151", "166/165"): 96.19,    # Bulbasaur IR
    ("pokemon-151", "201/165"): 90.00,    # Alakazam ex SIR
    ("pokemon-151", "169/165"): 85.91,    # Charmeleon IR
    ("pokemon-151", "171/165"): 74.99,    # Wartortle IR
    ("pokemon-151", "175/165"): 74.49,    # Psyduck IR
    ("pokemon-151", "167/165"): 62.70,    # Ivysaur IR
    ("pokemon-151", "181/165"): 55.44,    # Dragonair IR
    ("pokemon-151", "176/165"): 53.91,    # Poliwhirl IR
    ("pokemon-151", "183/165"): 51.91,    # Charizard ex UR
    ("pokemon-151", "193/165"): 50.00,    # Mew ex UR
    ("pokemon-151", "205/165"): 34.59,    # Mew ex HR
    ("pokemon-151", "184/165"): 30.00,    # Blastoise ex UR
    ("pokemon-151", "177/165"): 28.86,    # Machoke IR
    ("pokemon-151", "203/165"): 24.97,    # Erika's Invitation SIR
    ("pokemon-151", "174/165"): 24.00,    # Nidoking IR
    ("pokemon-151", "182/165"): 21.45,    # Venusaur ex UR
    ("pokemon-151", "204/165"): 21.25,    # Giovanni's Charisma SIR
    ("pokemon-151", "180/165"): 19.98,    # Omanyte IR
    ("pokemon-151", "172/165"): 19.58,    # Caterpie IR
    ("pokemon-151", "178/165"): 18.75,    # Tangela IR
    ("pokemon-151", "186/165"): 17.18,    # Ninetales ex UR
    ("pokemon-151", "188/165"): 15.50,    # Alakazam ex UR
    ("pokemon-151", "192/165"): 14.99,    # Zapdos ex UR
    ("pokemon-151", "179/165"): 17.88,    # Mr. Mime IR
    ("pokemon-151", "196/165"): 11.28,    # Erika's Invitation UR
    ("pokemon-151", "006/165"): 10.40,    # Charizard ex base
    ("pokemon-151", "185/165"): 10.00,    # Arbok ex UR
    ("pokemon-151", "187/165"): 10.00,    # Wigglytuff ex UR
}

# Load current data
with open("data/card_values.json") as f:
    cards = json.load(f)

# Update prices where Dawnglare has data
updated = 0
for card in cards:
    key = (card["set_id"], card["number"])
    if key in dawnglare:
        old = card["value"]
        card["value"] = dawnglare[key]
        if abs(old - dawnglare[key]) > 0.5:
            updated += 1

# Re-sort
cards.sort(key=lambda x: -x["value"])

# Save
with open("data/card_values.json", "w") as f:
    json.dump(cards, f, indent=2)

print(f"Updated {updated} card prices with Dawnglare data")
print(f"Total cards: {len(cards)}")
