#!/usr/bin/env python3
"""Genereert book/_static/db/gadgetshop.db, de databank van de overhoringen (issue #61).

Gebruik:
    python scripts/generate_gadgetshop_db.py

Een webshop voor gadgets. De overhoringen (book/overhoringen/) gebruiken deze
databank en de cursuslessen (book/chapters/) niet: zo kan een leerling op een
toets geen antwoord uit de cursus overnemen en moet hij het schema echt lezen.
Engelse tabel- en kolomnamen zoals in webshop.db, Vlaamse klantnamen en
steden. Iets rijker dan webshop.db, duidelijk eenvoudiger dan adventureworks.db:

    brands       (brand_id, name, country, founded_year)
    categories   (category_id, name, parent_category_id)
    products     (product_id, name, model_code, brand_id, category_id, price,
                  stock, color, weight_g, battery_hours, release_date,
                  discontinued)
    customers    (customer_id, first_name, last_name, email, phone, city,
                  postal_code, birth_date, join_date, newsletter)
    orders       (order_id, customer_id, order_date, status, payment_method,
                  shipping_method, shipped_date, coupon_code)
    order_items  (order_id, product_id, quantity, unit_price, discount_pct)
    reviews      (review_id, product_id, customer_id, rating, title,
                  review_date, verified_purchase)

Het script is deterministisch (vaste seed): elke run produceert exact dezelfde
data. tests/test_gadgetshop_db.py controleert dat de gecommitte databank gelijk
is aan wat dit script maakt. Pas de constantes hieronder aan en run opnieuw om
de dataset te wijzigen.

Onderaan staan controles (asserts) die bewaken wat de overhoringen nodig
hebben. Voor SQL hoofdstuk 1 en 2 (SELECT, WHERE, ORDER BY, LIMIT, DISTINCT,
berekende kolommen met AS en ||, NULL, LIKE, IN, BETWEEN, datums als tekst):

- tekst met patronen voor LIKE: productnamen met terugkerende woorden (Pro,
  Mini, Max, Lite, Buds, Phone, ...), met twee valkuilen ("Pronto Charger",
  "Maxi LED Strip"); een modelcode met vaste lengte ('EB-312', voor `_`);
  e-mails op verschillende domeinen; postcodes van vier cijfers;
- NULL met betekenis, in meerdere kolommen: geen kleur (kabels) of batterij,
  geen e-mail, telefoon of geboortedatum, nog niet verzonden (shipped_date),
  geen kortingscode, een review zonder titel, een merk zonder oprichtingsjaar;
- datums als tekst YYYY-MM-DD, bestellingen gespreid over drie jaar
  (2023-09-01 .. 2026-08-31) met een piek rond Black Friday en de feestdagen;
- getallen met een breed bereik: prijs (EUR 5 - 2.500), gewicht (15 g - 10 kg),
  batterijduur, stock (ook 0), rating 1-5, korting in procent;
- kolommen met weinig verschillende waarden voor IN / NOT IN en DISTINCT:
  status, payment_method, shipping_method, country, kleur, categorie;
- "vuile" records: twee steden in kleine letters (LOWER()-tip) en een dubbel
  e-mailadres.

Voor latere overhoringen (JOIN, GROUP BY, HAVING): klanten zonder bestellingen,
producten die nooit besteld en/of nooit beoordeeld werden, merken en een
categorie zonder producten, hoofdcategorieen (parent_category_id IS NULL), en
reviews zonder aankoop (verified_purchase = 0). Een review met
verified_purchase = 1 hoort altijd bij een geleverde bestelling van die klant.

Opgelet bij berekende kolommen: discount_pct is een geheel getal (10 = 10 %).
`unit_price * (100 - discount_pct) / 100` rekent juist omdat unit_price een
REAL is; `discount_pct / 100` alleen is een gehele deling (altijd 0).

De foreign keys zijn geldig: de SQL-editor zet PRAGMA foreign_keys aan (#46).
Het bestand blijft klein (< 1 MB), want elke overhoringpagina laadt het op
trage leerlingenlaptops.
"""

from __future__ import annotations

import bisect
import random
import sqlite3
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

SEED = 20260929
DB_PATH = Path(__file__).resolve().parent.parent / "book" / "_static" / "db" / "gadgetshop.db"
MAX_BYTES = 1_000_000

# De webshop opent op START_DATE; END_DATE is "vandaag" voor deze dataset.
START_DATE = date(2023, 9, 1)
END_DATE = date(2026, 8, 31)
# Op deze dag daalden de prijzen: oudere orderregels hebben soms een hogere unit_price.
PRICE_CHANGE_DATE = date(2025, 1, 1)

N_CUSTOMERS = 500  # inclusief de "vuile" records onderaan make_customers()

# ---------------------------------------------------------------------------
# Merken en categorieen
# ---------------------------------------------------------------------------

BRANDS = [
    # (brand_id, name, country, founded_year)
    (1, "Voltix", "Belgium", 2012),
    (2, "Lumora", "Netherlands", 2015),
    (3, "Kumo", "Japan", 1978),
    (4, "Sonaro", "Germany", 1964),
    (5, "Nordvik", "Sweden", 2009),
    (6, "Pixelgrid", "United States", 1998),
    (7, "Zentek", "China", 2011),
    (8, "Hanbit", "South Korea", 1983),
    (9, "Taipix", "Taiwan", 1992),
    (10, "Aurelle", "France", 2004),
    (11, "Bergli", "Switzerland", 1951),
    (12, "Fluxon", "United States", 2016),
    (13, "Mokai", "Japan", 1969),
    (14, "Brixel", "Belgium", 2019),
    (15, "Yunto", "China", 2014),
    (16, "Wendel", "Germany", 1987),
    (17, "Tidewave", "United States", 2007),
    (18, "Hikari", "Japan", 1955),
    (19, "Dalvo", "Netherlands", 2021),
    (20, "Orbis", "Taiwan", 2001),
    (21, "Seonu", "South Korea", 2017),
    (22, "Nimbl", "China", None),      # oprichtingsjaar onbekend
    # Merken zonder producten (LEFT JOIN-oefening)
    (23, "Glint", "Belgium", None),
    (24, "Retrona", "France", 1972),
    (25, "Pebblo", "Sweden", 2022),
]
BRANDS_WITHOUT_PRODUCTS = {23, 24, 25}

CATEGORIES = [
    # (category_id, name, parent_category_id) -- NULL: hoofdcategorie
    (1, "Audio", None),
    (2, "Computing", None),
    (3, "Mobile", None),
    (4, "Smart Home", None),
    (5, "Accessories", None),
    (6, "Headphones", 1),
    (7, "Earbuds", 1),
    (8, "Speakers", 1),
    (9, "Laptops", 2),
    (10, "Peripherals", 2),
    (11, "Smartphones", 3),
    (12, "Tablets", 3),
    (13, "Smartwatches", 3),
    (14, "Smart Lighting", 4),
    (15, "Cables", 5),
    (16, "Chargers", 5),
    (17, "Projectors", 2),  # nieuwe categorie, nog zonder producten
]

# Prefix van de modelcode per categorie: 'EB-312' = Earbuds, 3e generatie, nr. 12.
MODEL_PREFIX = {6: "HP", 7: "EB", 8: "SK", 9: "LT", 10: "PE", 11: "SM", 12: "TB",
                13: "SW", 14: "LI", 15: "CB", 16: "CH"}

# ---------------------------------------------------------------------------
# Productcatalogus: productlijnen met varianten
# ---------------------------------------------------------------------------

# Varianten: (factor prijs, factor gewicht, factor batterij)
VARIANTS = {
    "": (1.0, 1.0, 1.0),
    "Lite": (0.7, 0.9, 0.85),
    "Mini": (0.75, 0.7, 0.7),
    "SE": (0.85, 1.0, 0.95),
    "Plus": (1.2, 1.1, 1.15),
    "Pro": (1.4, 1.05, 1.1),
    "Max": (1.7, 1.3, 1.35),
    "Ultra": (1.9, 1.15, 1.25),
}

# (categorie, lijn, merk, varianten, basisprijs, basisgewicht in g,
#  batterijduur in uur of None, kleuren -- None: het product heeft geen kleur)
FAMILIES = [
    # Headphones
    (6, "Arc Headphones", 4, ["", "Pro", "Max"], 149, 260, 30, ["black", "silver", "blue"]),
    (6, "QuietWave", 3, ["Lite", "", "Pro"], 199, 250, 35, ["black", "white"]),
    (6, "Studio H", 10, ["", "Pro"], 299, 320, 25, ["black", "gray"]),
    (6, "Trail Headphones", 5, ["Mini", "", "Max"], 59, 190, 45, ["black", "green", "blue"]),
    (6, "Beam Headset", 12, ["Lite", "", "Pro"], 89, 280, 20, ["black", "red"]),
    (6, "Kids Headphones", 14, [""], 29, 150, 40, ["pink", "blue", "green"]),
    # Earbuds
    (7, "Nova Buds", 7, ["Lite", "", "Pro", "Max"], 79, 48, 7, ["white", "black", "blue"]),
    (7, "Pulse Buds", 8, ["Mini", "", "Pro"], 129, 52, 6, ["white", "black", "gray"]),
    (7, "Echo Buds", 1, ["", "Pro"], 99, 50, 8, ["black", "white", "red"]),
    (7, "Sport Buds", 5, ["", "Plus"], 69, 55, 9, ["black", "green", "blue"]),
    (7, "Tiny Buds", 15, ["Mini", "Lite"], 24, 40, 5, ["white", "pink"]),
    (7, "Aura Buds", 10, ["Pro", "Max"], 179, 56, 7, ["white", "gold", "black"]),
    # Speakers
    (8, "Echo Speaker", 1, ["Mini", "", "Max"], 79, 600, 12, ["black", "red", "blue", "green"]),
    (8, "Boom Box", 17, ["", "Pro", "Max"], 149, 1800, 20, ["black", "blue"]),
    (8, "Pebble Speaker", 2, ["Mini", "Lite", ""], 39, 280, 10, ["white", "pink", "gray"]),
    (8, "Soundbar", 4, ["Lite", "", "Pro"], 249, 3200, None, ["black"]),
    (8, "Party Tower", 17, ["", "Max"], 399, 7400, 18, ["black"]),
    (8, "Home Speaker", 16, ["", "Plus"], 129, 1400, None, ["white", "black", "gray"]),
    # Laptops
    (9, "AeroBook 13", 6, ["", "Pro"], 1099, 1200, 16, ["silver", "gray"]),
    (9, "AeroBook 15", 6, ["", "Pro", "Max"], 1399, 1650, 14, ["silver", "gray"]),
    (9, "WorkMate 14", 9, ["Lite", "", "Pro"], 649, 1450, 11, ["gray", "black"]),
    (9, "GameForce 16", 20, ["", "Max"], 1599, 2400, 6, ["black"]),
    (9, "StudyBook 14", 7, ["", "Plus"], 449, 1500, 10, ["gray", "blue"]),
    (9, "Slate 13", 13, ["", "Ultra"], 1199, 1080, 18, ["silver", "gold"]),
    # Peripherals
    (10, "Swift Mouse", 12, ["Mini", "", "Pro"], 29, 90, 70, ["black", "white"]),
    (10, "Glide Mouse", 16, [""], 15, 85, None, ["black"]),
    (10, "Type Keyboard", 16, ["Mini", "", "Pro"], 45, 750, None, ["black", "white"]),
    (10, "Clack Keyboard", 12, ["", "Pro"], 119, 950, 200, ["black", "gray"]),
    (10, "View Cam", 18, ["", "Pro"], 59, 140, None, ["black"]),
    (10, "Desk Hub", 19, ["", "Max"], 39, 120, None, ["gray"]),
    (10, "Stylus Pen", 13, ["", "Pro"], 49, 16, 12, ["white", "black"]),
    # Smartphones
    (11, "Nova Phone", 7, ["Lite", "", "Pro", "Max"], 399, 185, 28, ["black", "blue", "green", "pink"]),
    (11, "Halo Phone", 8, ["", "Plus", "Ultra"], 749, 190, 30, ["black", "silver", "blue"]),
    (11, "Pixo Phone", 6, ["", "Pro"], 699, 200, 27, ["black", "white", "blue"]),
    (11, "Moka Phone", 13, ["Mini", ""], 549, 160, 22, ["white", "pink", "black"]),
    (11, "Rugged Phone", 17, [""], 349, 290, 40, ["black", "green"]),
    (11, "Flip Phone", 21, ["Lite", ""], 999, 180, 20, ["black", "gold"]),
    # Tablets
    (12, "Nova Tab", 7, ["Lite", "", "Pro"], 249, 480, 12, ["gray", "blue"]),
    (12, "Halo Tab", 8, ["", "Plus", "Ultra"], 549, 520, 13, ["silver", "gray"]),
    (12, "Kids Tab", 14, [""], 129, 420, 10, ["blue", "pink"]),
    (12, "Pixo Tab", 6, ["Mini", ""], 499, 330, 10, ["silver", "white"]),
    # Smartwatches
    (13, "Orbit Watch", 7, ["Lite", "", "Pro"], 149, 38, 48, ["black", "silver", "pink"]),
    (13, "Halo Watch", 8, ["", "Ultra"], 299, 45, 40, ["black", "silver"]),
    (13, "Pixo Watch", 6, ["SE", "", "Ultra"], 399, 42, 20, ["black", "white", "gold"]),
    (13, "Fit Band", 5, ["Mini", "", "Pro"], 49, 25, 240, ["black", "blue", "pink"]),
    (13, "Trek Watch", 11, ["", "Max"], 449, 60, 336, ["black", "green"]),
    # Smart Lighting
    (14, "Glow Bulb", 2, ["", "Pro"], 15, 70, None, ["white"]),
    (14, "Glow Spot", 2, ["Lite", ""], 19, 60, None, ["white"]),
    (14, "Glow Strip 2m", 2, [""], 39, 180, None, None),
    (14, "Maxi LED Strip 5m", 19, [""], 59, 350, None, None),   # valkuil voor LIKE '%Max%'
    (14, "Lumo Lamp", 22, ["Mini", ""], 89, 1200, None, ["white", "black"]),
    (14, "Light Panel", 2, ["", "Max"], 199, 900, None, ["white"]),
    (14, "Night Light", 14, [""], 25, 150, 12, ["white", "blue"]),
    # Cables: geen kleur, geen batterij
    (15, "USB-C Cable 1m", 1, [""], 10, 30, None, None),
    (15, "USB-C Cable 2m", 1, [""], 13, 50, None, None),
    (15, "USB-C to USB-A Cable 1m", 15, [""], 8, 30, None, None),
    (15, "Micro-USB Cable 1m", 15, [""], 5.5, 25, None, None),
    (15, "HDMI Cable 2m", 19, [""], 15, 110, None, None),
    (15, "HDMI Cable 5m", 19, [""], 25, 250, None, None),
    (15, "DisplayPort Cable 2m", 20, [""], 20, 120, None, None),
    (15, "Audio Cable 3.5mm", 4, [""], 7, 35, None, None),
    (15, "Ethernet Cable 3m", 19, [""], 9, 90, None, None),
    (15, "Ethernet Cable 10m", 19, [""], 18, 280, None, None),
    (15, "Flux Cable USB-C", 12, ["Lite", "", "Pro"], 12, 35, None, None),
    # Chargers (ook powerbanks: die hebben een capaciteit, geen batterijduur)
    (16, "Pronto Charger 20W", 1, [""], 20, 60, None, ["white"]),   # valkuil voor LIKE '%Pro%'
    (16, "Pronto Charger 65W", 1, [""], 45, 140, None, ["white", "black"]),
    (16, "Volt Charger 30W", 15, ["Mini", ""], 25, 70, None, ["white", "black"]),
    (16, "Juice Pack", 7, ["Mini", "", "Max"], 30, 210, None, ["black", "white", "blue"]),
    (16, "Wireless Pad", 8, ["", "Pro"], 35, 120, None, ["black", "white"]),
    (16, "Travel Adapter", 11, [""], 28, 110, None, ["white"]),
    (16, "Car Charger", 15, [""], 15, 40, None, ["black"]),
    (16, "Charging Station", 21, ["", "Max"], 79, 450, None, ["black", "white"]),
]

# Producten die nooit besteld werden (LEFT JOIN-oefening). De eerste twee
# kregen ook geen enkele review; de andere wel een review zonder aankoop.
NEVER_ORDERED = ["Studio H Pro", "Party Tower Max", "Ethernet Cable 10m",
                 "Trek Watch Max", "Charging Station Max"]
NEVER_ORDERED_BUT_REVIEWED = ["Trek Watch Max", "Charging Station Max", "Party Tower Max"]

# Hoe graag klanten een product beoordelen, per categorie (niemand reviewt een kabel).
REVIEW_APPETITE = {15: 0.003, 16: 0.4}

# ---------------------------------------------------------------------------
# Klanten
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Anna", "Amber", "Axel", "Adam", "Aline", "Arthur", "Ayoub", "Bo", "Bram",
    "Britt", "Cas", "Céline", "Daan", "Dina", "Elias", "Emma", "Eva", "Ferre",
    "Fleur", "Gilles", "Hanne", "Ibrahim", "Ilias", "Ine", "Jana", "Jef",
    "Jules", "Kato", "Kobe", "Lars", "Lien", "Liv", "Lotte", "Lou", "Lucas",
    "Marie", "Mathis", "Milan", "Mo", "Nina", "Noa", "Nora", "Omar", "Pieter",
    "Quinten", "Rania", "Robbe", "Ruben", "Sam", "Sara", "Seppe", "Senne",
    "Stan", "Thomas", "Tom", "Tuur", "Victor", "Warre", "Wout", "Yana", "Zoë",
    "Elif", "Mehmet", "Sofia", "Lena", "Finn", "Febe", "Hamza", "Ella",
]

LAST_NAMES = [
    "Claes", "Cox", "Vos", "Bos", "Janssens", "Peeters", "Maes", "Jacobs",
    "Mertens", "Willems", "Wouters", "De Backer", "De Clercq", "De Vos",
    "Van Damme", "Van den Broeck", "Vermeulen", "Vercauteren", "Hermans",
    "Aerts", "Segers", "Pauwels", "Dubois", "Lemmens", "Michiels", "Smets",
    "Stevens", "Van Acker", "Verhoeven", "Deckers", "Yildiz", "El Amrani",
    "Nguyen", "Kaya", "Costa", "De Ridder", "Van Hoof", "Bogaerts", "Goossens",
    "Wauters", "Martens", "De Smet", "Ali", "Lambrechts", "Coppens", "Verstraete",
    "D'Hondt", "Desmet", "Tan", "Hendrickx",
]

# (stad, postcodes, gewicht)
CITIES = [
    ("Antwerpen", ["2000", "2018", "2060", "2100", "2140"], 16),
    ("Gent", ["9000", "9030", "9040", "9050"], 12),
    ("Brussel", ["1000", "1020", "1050"], 9),
    ("Leuven", ["3000", "3010"], 8),
    ("Brugge", ["8000", "8200"], 7),
    ("Mechelen", ["2800"], 6),
    ("Hasselt", ["3500"], 6),
    ("Kortrijk", ["8500"], 5),
    ("Oostende", ["8400"], 4),
    ("Aalst", ["9300"], 4),
    ("Sint-Niklaas", ["9100"], 4),
    ("Genk", ["3600"], 3),
    ("Turnhout", ["2300"], 3),
    ("Roeselare", ["8800"], 3),
    ("Lier", ["2500"], 2),
    ("Sint-Truiden", ["3800"], 2),
    ("Geel", ["2440"], 2),
    ("Dendermonde", ["9200"], 2),
    ("Ieper", ["8900"], 2),
    ("Tienen", ["3300"], 2),
    ("Vilvoorde", ["1800"], 2),
    ("Halle", ["1500"], 1),
    ("Diest", ["3290"], 1),
    ("Knokke-Heist", ["8300"], 1),
    ("Maaseik", ["3680"], 1),
]

EMAIL_DOMAINS = [
    ("gmail.com", 32), ("telenet.be", 16), ("hotmail.com", 14), ("outlook.com", 10),
    ("icloud.com", 8), ("proximus.be", 7), ("skynet.be", 5), ("yahoo.com", 4), ("live.be", 4),
]
MOBILE_PREFIXES = ["0468", "0470", "0471", "0472", "0473", "0474", "0475", "0476", "0477",
                   "0478", "0479", "0484", "0485", "0486", "0487", "0488", "0489", "0491",
                   "0492", "0493", "0494", "0495", "0496", "0497", "0498", "0499"]

# ---------------------------------------------------------------------------
# Bestellingen
# ---------------------------------------------------------------------------

STATUSES = ["pending", "processing", "shipped", "delivered", "cancelled", "returned"]
PAYMENT_METHODS = [("bancontact", 40), ("credit card", 25), ("paypal", 18),
                   ("bank transfer", 10), ("gift card", 7)]
SHIPPING_METHODS = [("standard", 55), ("pickup point", 22), ("express", 15), ("store pickup", 8)]
# Dagen tussen bestelling en verzending, per verzendmethode.
SHIPPING_DELAY = {"standard": (1, 3), "pickup point": (1, 3), "express": (0, 1), "store pickup": (0, 2)}
COUPONS = {"WELCOME10": 10, "SUMMER15": 15, "BLACKFRIDAY": 25, "STUDENT5": 5, "NEWSLETTER10": 10}
PROMO_DISCOUNTS = [5, 10, 15, 20]

# Seizoensgewichten per maand: eindejaar piekt, de zomer is kalmer.
SEASON_WEIGHT = {1: 1.1, 2: 0.8, 3: 0.9, 4: 0.95, 5: 0.95, 6: 0.85,
                 7: 0.75, 8: 0.8, 9: 1.0, 10: 1.05, 11: 1.6, 12: 2.0}

# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

TITLES = {
    5: ["Top!", "Echt een aanrader", "Perfect", "Beste aankoop dit jaar", "Super tevreden",
        "Waar voor je geld", "Prima prijs-kwaliteit", "Doet precies wat het moet doen"],
    4: ["Goed product", "Tevreden", "Bijna perfect", "Goede prijs", "Aanrader, met een kleine min",
        "Mooi afgewerkt"],
    3: ["Oké", "Gemiddeld", "Niet slecht, niet super", "Te duur voor wat het is", "Kan beter"],
    2: ["Valt tegen", "Niet wat ik verwachtte", "Te duur", "Kwaliteit valt tegen"],
    1: ["Niet kopen!", "Na een week kapot", "Slechte kwaliteit", "Geld terug gevraagd",
        "Teleurstellend"],
}
BATTERY_TITLES = {5: ["Batterij gaat superlang mee"], 4: ["Goede batterij"],
                  3: ["Batterij kon beter"], 2: ["Batterij valt tegen"], 1: ["Batterij na een maand stuk"]}
SOUND_TITLES = {5: ["Geweldig geluid"], 4: ["Mooi geluid"], 3: ["Geluid is oké"],
                2: ["Geluid valt tegen"], 1: ["Slecht geluid"]}
AUDIO_CATEGORIES = {6, 7, 8}


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------


def round_price(value: float) -> float:
    """Een winkelprijs: 1399.0 of 79.99 of 12.99 (nooit onder 5)."""
    if value >= 100:
        return float(round(value / 10) * 10 - 1)
    return max(round(value) - 0.01, 5.49)


def ascii_slug(text: str) -> str:
    """'D'Hondt' -> 'dhondt', 'Zoë' -> 'zoe' (voor e-mailadressen)."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(ch for ch in plain.lower() if ch.isalnum())


def random_date(rng: random.Random, lo: date, hi: date) -> date:
    return lo + timedelta(days=rng.randint(0, (hi - lo).days))


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 februari
        return d.replace(year=d.year + years, day=28)


def is_black_friday_week(d: date) -> bool:
    return (d.month == 11 and d.day >= 24) or (d.month == 12 and d.day <= 1)


# ---------------------------------------------------------------------------
# Generatie
# ---------------------------------------------------------------------------


def make_products(rng: random.Random):
    """Producten plus interne gegevens (populariteit, stopdatum, oude prijs, kwaliteit)."""
    products = []
    extra = {}
    seq = {cat: 0 for cat in MODEL_PREFIX}
    pid = 1
    for cat, line, brand, variants, base_price, base_weight, base_battery, colors in FAMILIES:
        # De lijn verschijnt op een basisdatum; de varianten volgen in de volgorde van de lijst.
        release = random_date(rng, date(2021, 3, 1), date(2025, 10, 31))
        for variant in variants:
            price_f, weight_f, battery_f = VARIANTS[variant]
            name = f"{line} {variant}".strip()
            release = min(release + timedelta(days=rng.randint(0, 150)), date(2026, 7, 15))
            price = min(round_price(base_price * price_f * rng.uniform(0.95, 1.05)), 2499.0)
            weight = max(15, round(base_weight * weight_f * rng.uniform(0.9, 1.1)))
            battery = None if base_battery is None else max(3, round(base_battery * battery_f * rng.uniform(0.9, 1.1)))
            color = None if colors is None else rng.choice(colors)

            seq[cat] += 1
            generation = release.year - 2020  # 2021 -> 1, ..., 2026 -> 6
            model_code = f"{MODEL_PREFIX[cat]}-{generation}{seq[cat]:02d}"

            # Oudere producten gaan uit het gamma: nog besteld tot de stopdatum.
            stop = None
            if release < date(2023, 3, 1) and rng.random() < 0.5:
                stop = random_date(rng, date(2024, 6, 1), date(2026, 3, 31))
            discontinued = 1 if stop is not None else 0
            if discontinued:
                stock = 0
            elif rng.random() < 0.05:
                stock = 0  # tijdelijk uitverkocht
            elif price < 50:
                stock = rng.randint(40, 250)
            elif price < 500:
                stock = rng.randint(5, 80)
            else:
                stock = rng.randint(1, 30)

            products.append((pid, name, model_code, brand, cat, price, stock, color,
                             weight, battery, release.isoformat(), discontinued))
            old_price = None
            if release < date(2024, 6, 1) and rng.random() < 0.35:
                old_price = round_price(price * rng.uniform(1.08, 1.2))
            extra[pid] = {
                "popularity": rng.uniform(0.5, 1.6) / price ** 0.5,
                "stop": stop,
                "old_price": old_price,
                "quality": rng.uniform(3.0, 4.6),
                "release": release,
            }
            pid += 1
    return products, extra


def make_customers(rng: random.Random):
    """Klanten, genummerd in volgorde van registratie."""
    city_pool = [(c, pcs) for c, pcs, w in CITIES for _ in range(w)]
    domains = [d for d, _ in EMAIL_DOMAINS]
    domain_weights = [w for _, w in EMAIL_DOMAINS]
    used_emails: set[str] = set()

    # Veel klanten schrijven zich in bij de opening; daarna een gestage stroom.
    join_span = (END_DATE - timedelta(days=10) - START_DATE).days
    raw = []
    n_regular = N_CUSTOMERS - 5
    for _ in range(n_regular):
        fn, ln = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        city, pcs = rng.choice(city_pool)
        pc = rng.choice(pcs)
        if rng.random() < 0.15:
            join = random_date(rng, START_DATE, START_DATE + timedelta(days=30))
        else:  # meer klanten in het begin dan op het eind
            join = START_DATE + timedelta(days=int(join_span * rng.random() ** 1.7))
        birth = None
        if rng.random() > 0.15:
            age = rng.choices([rng.randint(16, 24), rng.randint(25, 44), rng.randint(45, 75)],
                              weights=[30, 45, 25])[0]
            birth = random_date(rng, add_years(join, -age - 1) + timedelta(days=1), add_years(join, -age))
        email = None
        if rng.random() > 0.07:
            f, l = ascii_slug(fn), ascii_slug(ln)
            yy = f"{birth.year % 100:02d}" if birth else f"{rng.randint(0, 99):02d}"
            local = rng.choices([f"{f}.{l}", f"{f[0]}.{l}", f"{f}{l}", f"{f}.{l}{yy}", f"{l}.{f}"],
                                weights=[50, 15, 10, 15, 10])[0]
            domain = rng.choices(domains, weights=domain_weights)[0]
            email = f"{local}@{domain}"
            n = 2
            while email in used_emails:
                email = f"{local}{n}@{domain}"
                n += 1
            used_emails.add(email)
        phone = None
        if rng.random() > 0.22:
            phone = (f"{rng.choice(MOBILE_PREFIXES)} {rng.randint(10, 99)} "
                     f"{rng.randint(10, 99)} {rng.randint(10, 99)}")
        newsletter = 1 if rng.random() < 0.4 else 0
        raw.append([fn, ln, email, phone, city, pc, birth, join, newsletter])

    # --- Bewust "vuile" records ----------------------------------------------
    # Steden in kleine letters: WHERE city = 'Gent' mist ze, LOWER(city) niet.
    raw.append(["Jonas", "Verstraete", "jonas.verstraete@telenet.be", "0476 21 43 65",
                "gent", "9000", date(1994, 5, 17), date(2024, 5, 14), 0])
    raw.append(["Hilde", "Mertens", "hilde.mertens@gmail.com", None,
                "leuven", "3000", None, date(2025, 2, 3), 1])
    # Dubbel e-mailadres: dezelfde persoon registreerde zich twee keer.
    raw.append(["Jan", "Claes", "jan.claes@skynet.be", "0495 12 34 56",
                "Diksmuide", "8600", date(1968, 11, 2), date(2023, 10, 2), 0])
    raw.append(["Jan", "Claes", "jan.claes@skynet.be", None,
                "Diksmuide", "8600", None, date(2025, 11, 19), 1])
    # Een klant zonder e-mail, telefoon en geboortedatum.
    raw.append(["Mila", "Vos", None, None, "Brugge", "8000", None, date(2024, 3, 9), 0])
    for email in ("jonas.verstraete@telenet.be", "hilde.mertens@gmail.com"):
        assert email not in used_emails, email

    raw.sort(key=lambda r: r[7])  # customer_id volgt de registratiedatum
    customers = []
    for cid, (fn, ln, email, phone, city, pc, birth, join, nl) in enumerate(raw, start=1):
        customers.append((cid, fn, ln, email, phone, city, pc,
                          birth.isoformat() if birth else None, join.isoformat(), nl))
    return customers


def day_weights():
    """(dagen, cumulatieve gewichten) voor de besteldatum: seizoen, groei, Black Friday."""
    days, cum, total = [], [], 0.0
    d = START_DATE
    while d <= END_DATE:
        growth = 0.8 + 0.5 * (d - START_DATE).days / (END_DATE - START_DATE).days
        w = SEASON_WEIGHT[d.month] * growth
        if is_black_friday_week(d):
            w *= 2.5
        if d.weekday() >= 5:
            w *= 1.2
        total += w
        days.append(d)
        cum.append(total)
        d += timedelta(days=1)
    return days, cum


def pick_day(rng: random.Random, days, cum, lo: date, hi: date) -> date:
    """Een gewogen dag tussen lo en hi (inclusief)."""
    i, j = (lo - START_DATE).days, (hi - START_DATE).days
    base = cum[i - 1] if i > 0 else 0.0
    r = base + rng.random() * (cum[j] - base)
    return days[min(bisect.bisect_left(cum, r, i, j + 1), j)]


def make_orders(rng: random.Random, customers):
    days, cum = day_weights()
    raw = []  # (date, customer_id, first_order)
    for cust in customers:
        cid, join = cust[0], date.fromisoformat(cust[8])
        r = rng.random()
        if r < 0.12:
            n = 0                          # nooit besteld (LEFT JOIN)
        elif r < 0.28:
            n = 1
        elif r < 0.92:
            n = rng.randint(2, 20)
        else:
            n = rng.randint(22, 55)        # trouwe klanten
        # Wie laat klant werd, bestelde nog niet zo vaak.
        active = (END_DATE - join).days
        n = min(n, max(1, round(n * active / 900))) if n else 0
        if not n:
            continue
        # Eerste bestelling: meestal bij de registratie.
        first = join if rng.random() < 0.6 else min(join + timedelta(days=rng.randint(1, 14)), END_DATE)
        raw.append((first, cid, True))
        for _ in range(n - 1):
            raw.append((pick_day(rng, days, cum, first, END_DATE), cid, False))
    raw.sort(key=lambda o: (o[0], o[1], not o[2]))
    return [(10001 + i, cid, d, first) for i, (d, cid, first) in enumerate(raw)]


def order_details(rng: random.Random, order, customer):
    """status, payment_method, shipping_method, shipped_date, coupon_code."""
    order_id, cid, d, first = order
    age = (END_DATE - d).days
    payment = rng.choices([p for p, _ in PAYMENT_METHODS], weights=[w for _, w in PAYMENT_METHODS])[0]
    shipping = rng.choices([s for s, _ in SHIPPING_METHODS], weights=[w for _, w in SHIPPING_METHODS])[0]

    if rng.random() < 0.035:
        status = "cancelled"
    elif age <= 3 or (payment == "bank transfer" and age <= 7):
        status = "pending" if rng.random() < 0.5 else "processing"
    elif age <= 6:
        status = "processing" if rng.random() < 0.3 else "shipped"
    elif age <= 20:
        status = "shipped" if rng.random() < 0.4 else "delivered"
    else:
        status = "returned" if rng.random() < 0.03 else "delivered"

    shipped = None
    if status in ("shipped", "delivered", "returned"):
        lo, hi = SHIPPING_DELAY[shipping]
        shipped = (d + timedelta(days=min(rng.randint(lo, hi), age))).isoformat()

    newsletter, birth = customer[9], customer[7]
    coupon = None
    if first and rng.random() < 0.3:
        coupon = "WELCOME10"
    elif is_black_friday_week(d) and rng.random() < 0.45:
        coupon = "BLACKFRIDAY"
    elif d.month in (6, 7, 8) and rng.random() < 0.15:
        coupon = "SUMMER15"
    elif newsletter and rng.random() < 0.08:
        coupon = "NEWSLETTER10"
    elif birth and birth >= "2002-01-01" and rng.random() < 0.15:
        coupon = "STUDENT5"
    return (order_id, cid, d.isoformat(), status, payment, shipping, shipped, coupon)


def make_order_items(rng: random.Random, orders, products, extra):
    never = {p[0] for p in products if p[1] in NEVER_ORDERED}
    prices = {p[0]: p[5] for p in products}
    orderable = [p[0] for p in products if p[0] not in never]
    n_choices, n_weights = [1, 2, 3, 4, 5, 6], [30, 28, 20, 12, 6, 4]

    items = []
    for order in orders:
        order_id, d = order[0], date.fromisoformat(order[2])
        coupon = order[7]
        pool = [pid for pid in orderable
                if extra[pid]["release"] <= d and (extra[pid]["stop"] is None or d < extra[pid]["stop"])]
        weights = [extra[pid]["popularity"] for pid in pool]
        n = min(rng.choices(n_choices, weights=n_weights)[0], len(pool))
        chosen: list[int] = []
        while len(chosen) < n:
            pid = rng.choices(pool, weights=weights)[0]
            if pid not in chosen:
                chosen.append(pid)
        for pid in sorted(chosen):
            price = prices[pid]
            if d < PRICE_CHANGE_DATE and extra[pid]["old_price"] is not None:
                price = extra[pid]["old_price"]
            if price < 20:
                qty = rng.choices([1, 2, 3, 4, 5], weights=[50, 25, 12, 8, 5])[0]
            elif price < 100:
                qty = rng.choices([1, 2, 3], weights=[75, 18, 7])[0]
            else:
                qty = rng.choices([1, 2], weights=[94, 6])[0]
            if coupon:
                discount = COUPONS[coupon]
            elif rng.random() < 0.07:
                discount = rng.choice(PROMO_DISCOUNTS)
            else:
                discount = 0
            items.append((order_id, pid, qty, price, discount))

    # Een uitschieter: een school bestelt 40 USB-C-kabels in een keer.
    cable = next(p[0] for p in products if p[1] == "USB-C Cable 1m")
    occurrences = [i for i, it in enumerate(items) if it[1] == cable]
    idx = occurrences[len(occurrences) // 2]
    items[idx] = (items[idx][0], cable, 40, items[idx][3], items[idx][4])
    return items


def rating_for(rng: random.Random, quality: float, spread: float) -> int:
    return max(1, min(5, round(rng.gauss(quality, spread))))


def review_title(rng: random.Random, rating: int, product) -> str | None:
    if rng.random() < 0.1:
        return None  # alleen sterren, geen titel
    category, battery = product[4], product[9]
    r = rng.random()
    if battery is not None and r < 0.2:
        return rng.choice(BATTERY_TITLES[rating])
    if category in AUDIO_CATEGORIES and r < 0.4:
        return rng.choice(SOUND_TITLES[rating])
    return rng.choice(TITLES[rating])


def make_reviews(rng: random.Random, orders, items, products, customers, extra):
    by_id = {p[0]: p for p in products}
    order_info = {o[0]: o for o in orders}
    joins = {c[0]: date.fromisoformat(c[8]) for c in customers}

    # Aankopen die geleverd zijn: (klant, product) -> (verzenddatum, teruggestuurd?)
    bought: dict[tuple[int, int], tuple[date, bool]] = {}
    ever_bought: set[tuple[int, int]] = set()
    for order_id, pid, *_ in items:
        o = order_info[order_id]
        ever_bought.add((o[1], pid))
        if o[3] in ("delivered", "returned") and (o[1], pid) not in bought:
            bought[(o[1], pid)] = (date.fromisoformat(o[6]), o[3] == "returned")

    reviews = []  # (review_date, product_id, customer_id, rating, title, verified)
    reviewed: set[tuple[int, int]] = set()
    for (cid, pid), (shipped, returned) in sorted(bought.items()):
        p_review = (0.19 + (0.4 if returned else 0.0)) * REVIEW_APPETITE.get(by_id[pid][4], 1.0)
        if rng.random() >= p_review:
            continue
        when = shipped + timedelta(days=rng.randint(3, 45))
        if when > END_DATE:
            continue
        rating = rating_for(rng, extra[pid]["quality"], 0.9)
        if returned:
            rating = min(rating, rng.choice([1, 2, 2, 3]))
        reviews.append((when, pid, cid, rating, review_title(rng, rating, by_id[pid]), 1))
        reviewed.add((cid, pid))

    # Reviews zonder aankoop: de klant kocht het product nooit in deze webshop.
    never = [p[0] for p in products if p[1] in NEVER_ORDERED]
    allowed_never = {p[0] for p in products if p[1] in NEVER_ORDERED_BUT_REVIEWED}
    candidates = [p[0] for p in products if p[0] not in never or p[0] in allowed_never]
    appetite = [REVIEW_APPETITE.get(by_id[pid][4], 1.0) for pid in candidates]
    customer_ids = [c[0] for c in customers]
    forced = sorted(allowed_never)  # elk van deze producten krijgt er minstens een
    target = 320
    unverified = 0
    while unverified < target:
        pid = forced.pop(0) if forced else rng.choices(candidates, weights=appetite)[0]
        cid = rng.choice(customer_ids)
        if (cid, pid) in ever_bought or (cid, pid) in reviewed:
            if pid in allowed_never:
                forced.insert(0, pid)
            continue
        lo = max(joins[cid], extra[pid]["release"], START_DATE)
        if lo > END_DATE:
            if pid in allowed_never:
                forced.insert(0, pid)
            continue
        when = random_date(rng, lo, END_DATE)
        rating = rating_for(rng, extra[pid]["quality"], 1.4)
        reviews.append((when, pid, cid, rating, review_title(rng, rating, by_id[pid]), 0))
        reviewed.add((cid, pid))
        unverified += 1

    reviews.sort(key=lambda r: (r[0], r[1], r[2]))
    return [(rid, pid, cid, rating, title, when.isoformat(), verified)
            for rid, (when, pid, cid, rating, title, verified) in enumerate(reviews, start=1)]


def generate() -> dict[str, list[tuple]]:
    """Alle rijen per tabel. Deterministisch: dezelfde seed geeft dezelfde data."""
    rng = random.Random(SEED)
    products, extra = make_products(rng)
    customers = make_customers(rng)
    by_cid = {c[0]: c for c in customers}
    raw_orders = make_orders(rng, customers)
    orders = [order_details(rng, o, by_cid[o[1]]) for o in raw_orders]
    items = make_order_items(rng, orders, products, extra)
    reviews = make_reviews(rng, orders, items, products, customers, extra)
    return {
        "brands": BRANDS,
        "categories": CATEGORIES,
        "products": products,
        "customers": customers,
        "orders": orders,
        "order_items": items,
        "reviews": reviews,
    }


SCHEMA = """
CREATE TABLE brands (
  brand_id      INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  country       TEXT NOT NULL,
  founded_year  INTEGER            -- NULL: onbekend
);
CREATE TABLE categories (
  category_id         INTEGER PRIMARY KEY,
  name                TEXT NOT NULL,
  parent_category_id  INTEGER,     -- NULL: hoofdcategorie
  FOREIGN KEY (parent_category_id) REFERENCES categories(category_id)
);
CREATE TABLE products (
  product_id     INTEGER PRIMARY KEY,
  name           TEXT NOT NULL,
  model_code     TEXT NOT NULL UNIQUE,  -- vaste lengte, bv. 'EB-312'
  brand_id       INTEGER NOT NULL,
  category_id    INTEGER NOT NULL,
  price          REAL NOT NULL,         -- in euro
  stock          INTEGER NOT NULL,
  color          TEXT,                  -- NULL: geen kleur
  weight_g       INTEGER NOT NULL,      -- in gram
  battery_hours  INTEGER,               -- NULL: geen batterij
  release_date   TEXT NOT NULL,         -- YYYY-MM-DD
  discontinued   INTEGER NOT NULL,      -- 1: uit het gamma
  FOREIGN KEY (brand_id) REFERENCES brands(brand_id),
  FOREIGN KEY (category_id) REFERENCES categories(category_id)
);
CREATE TABLE customers (
  customer_id  INTEGER PRIMARY KEY,
  first_name   TEXT NOT NULL,
  last_name    TEXT NOT NULL,
  email        TEXT,
  phone        TEXT,
  city         TEXT NOT NULL,
  postal_code  TEXT NOT NULL,
  birth_date   TEXT,                    -- YYYY-MM-DD
  join_date    TEXT NOT NULL,           -- YYYY-MM-DD
  newsletter   INTEGER NOT NULL         -- 1: ingeschreven
);
CREATE TABLE orders (
  order_id         INTEGER PRIMARY KEY,
  customer_id      INTEGER NOT NULL,
  order_date       TEXT NOT NULL,       -- YYYY-MM-DD
  status           TEXT NOT NULL,
  payment_method   TEXT NOT NULL,
  shipping_method  TEXT NOT NULL,
  shipped_date     TEXT,                -- NULL: nog niet verzonden
  coupon_code      TEXT,                -- NULL: geen kortingscode
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
CREATE TABLE order_items (
  order_id      INTEGER NOT NULL,
  product_id    INTEGER NOT NULL,
  quantity      INTEGER NOT NULL,
  unit_price    REAL NOT NULL,          -- prijs bij verkoop (kan afwijken van products.price)
  discount_pct  INTEGER NOT NULL,       -- korting in procent: 10 = 10 %
  PRIMARY KEY (order_id, product_id),
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (product_id) REFERENCES products(product_id)
);
CREATE TABLE reviews (
  review_id          INTEGER PRIMARY KEY,
  product_id         INTEGER NOT NULL,
  customer_id        INTEGER NOT NULL,
  rating             INTEGER NOT NULL,  -- 1 tot 5 sterren
  title              TEXT,              -- NULL: alleen sterren
  review_date        TEXT NOT NULL,     -- YYYY-MM-DD
  verified_purchase  INTEGER NOT NULL,  -- 1: de klant kocht het product hier
  FOREIGN KEY (product_id) REFERENCES products(product_id),
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
"""


def write_db(path: Path, tables: dict[str, list[tuple]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA foreign_keys = ON")  # zoals de SQL-editor (#46)
        con.executescript(SCHEMA)
        for table, rows in tables.items():
            marks = ",".join("?" * len(rows[0]))
            con.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------------

DATE_COLUMNS = [("products", "release_date"), ("customers", "birth_date"), ("customers", "join_date"),
                ("orders", "order_date"), ("orders", "shipped_date"), ("reviews", "review_date")]


def verify(path: Path = DB_PATH) -> dict[str, int]:
    """Controleer wat de overhoringen verwachten. Faalt hard als iets ontbreekt."""
    size = path.stat().st_size
    assert size < MAX_BYTES, f"{path.name} is {size} bytes, meer dan {MAX_BYTES}"
    con = sqlite3.connect(path)
    try:
        return _verify(con)
    finally:
        con.close()


def _verify(con: sqlite3.Connection) -> dict[str, int]:
    def q(sql):
        return con.execute(sql).fetchall()

    def one(sql):
        return con.execute(sql).fetchone()[0]

    def values(sql):
        return sorted(r[0] for r in q(sql))

    # --- Omvang: genoeg rijen in elke tabel -----------------------------------
    counts = {t: one(f"SELECT COUNT(*) FROM {t}") for t in
              ("brands", "categories", "products", "customers", "orders", "order_items", "reviews")}
    expected = {"brands": (20, 30), "categories": (12, 20), "products": (130, 170),
                "customers": (450, 550), "orders": (3500, 4500), "order_items": (8500, 11500),
                "reviews": (1300, 1700)}
    for table, (lo, hi) in expected.items():
        assert lo <= counts[table] <= hi, (table, counts[table])

    # --- Geldige sleutels ------------------------------------------------------
    assert q("PRAGMA integrity_check") == [("ok",)]
    assert q("PRAGMA foreign_key_check") == [], "ongeldige foreign keys"

    # --- Datums als tekst YYYY-MM-DD, gespreid over ongeveer drie jaar ----------
    for table, column in DATE_COLUMNS:
        bad = one(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL AND "
                  f"({column} NOT GLOB '[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]' "
                  f"OR date({column}) IS NOT {column})")
        assert bad == 0, f"{table}.{column}: {bad} waarden zijn geen datum YYYY-MM-DD"
    span = one("SELECT julianday(MAX(order_date)) - julianday(MIN(order_date)) FROM orders")
    assert span >= 1000, span
    for year in ("2024", "2025"):  # volledige jaren: elke maand bestellingen
        months = one(f"SELECT COUNT(DISTINCT substr(order_date, 6, 2)) FROM orders "
                     f"WHERE order_date LIKE '{year}-%'")
        assert months == 12, (year, months)
    assert one("SELECT COUNT(*) FROM orders WHERE order_date BETWEEN '2024-11-24' AND '2024-11-30'") \
        > 2 * one("SELECT COUNT(*) FROM orders WHERE order_date BETWEEN '2024-06-01' AND '2024-06-07'")
    assert one("SELECT COUNT(DISTINCT substr(release_date, 1, 4)) FROM products") >= 5
    assert one("SELECT COUNT(*) FROM customers WHERE birth_date BETWEEN '2000-01-01' AND '2009-12-31'") >= 30

    # --- LIKE: terugkerende woorden, vaste modelcodes, e-maildomeinen ----------
    for word in ("Pro", "Mini", "Max", "Lite"):
        n = one(f"SELECT COUNT(*) FROM products WHERE name LIKE '% {word}'")
        assert n >= 5, (word, n)
    # Valkuilen: LIKE '%Pro%' en '%Max%' vinden meer dan de varianten alleen.
    assert one("SELECT COUNT(*) FROM products WHERE name LIKE '%Pro%'") \
        > one("SELECT COUNT(*) FROM products WHERE name LIKE '% Pro' OR name LIKE '% Pro %'")
    assert one("SELECT COUNT(*) FROM products WHERE name LIKE '%Max%' AND name NOT LIKE '% Max'") >= 1
    assert q("SELECT DISTINCT length(model_code) FROM products") == [(6,)]
    assert one("SELECT COUNT(*) FROM products WHERE model_code NOT LIKE '__-___'") == 0
    assert one("SELECT COUNT(DISTINCT substr(model_code, 1, 2)) FROM products") >= 10
    domains = values("SELECT DISTINCT substr(email, instr(email, '@') + 1) FROM customers "
                     "WHERE email IS NOT NULL")
    assert len(domains) >= 6, domains
    assert 0 < one("SELECT COUNT(*) FROM customers WHERE email LIKE '%.be'") \
        < one("SELECT COUNT(*) FROM customers WHERE email IS NOT NULL")
    assert one("SELECT COUNT(*) FROM customers WHERE first_name LIKE 'A%'") >= 10
    assert one("SELECT COUNT(DISTINCT last_name) FROM customers WHERE last_name LIKE '___'") >= 3
    assert one("SELECT COUNT(*) FROM customers WHERE city LIKE 'Sint-%'") >= 3
    assert one("SELECT COUNT(*) FROM customers WHERE postal_code NOT GLOB '[1-9][0-9][0-9][0-9]'") == 0
    assert one("SELECT COUNT(*) FROM customers WHERE phone IS NOT NULL AND length(phone) <> 13") == 0
    assert one("SELECT COUNT(*) FROM reviews WHERE title LIKE '%batterij%'") >= 10

    # --- NULL met betekenis, in meerdere kolommen -----------------------------
    nulls = {
        "products.color": ("SELECT COUNT(*) FROM products WHERE color IS NULL", 10),
        "products.battery_hours": ("SELECT COUNT(*) FROM products WHERE battery_hours IS NULL", 30),
        "customers.email": ("SELECT COUNT(*) FROM customers WHERE email IS NULL", 15),
        "customers.phone": ("SELECT COUNT(*) FROM customers WHERE phone IS NULL", 50),
        "customers.birth_date": ("SELECT COUNT(*) FROM customers WHERE birth_date IS NULL", 40),
        "orders.shipped_date": ("SELECT COUNT(*) FROM orders WHERE shipped_date IS NULL", 100),
        "orders.coupon_code": ("SELECT COUNT(*) FROM orders WHERE coupon_code IS NULL", 2500),
        "reviews.title": ("SELECT COUNT(*) FROM reviews WHERE title IS NULL", 50),
        "brands.founded_year": ("SELECT COUNT(*) FROM brands WHERE founded_year IS NULL", 1),
    }
    for column, (sql, minimum) in nulls.items():
        assert one(sql) >= minimum, (column, one(sql))
    # ... en telkens ook genoeg waarden die niet NULL zijn.
    assert one("SELECT COUNT(*) FROM products WHERE battery_hours IS NOT NULL") >= 60
    assert one("SELECT COUNT(*) FROM orders WHERE coupon_code IS NOT NULL") >= 300
    # Kabels hebben geen kleur en geen batterij.
    assert one("SELECT COUNT(*) FROM products WHERE category_id = 15 "
               "AND (color IS NOT NULL OR battery_hours IS NOT NULL)") == 0
    # Geen lege tekst in plaats van NULL (dan werkt IS NULL niet).
    for table, column in [("products", "color"), ("customers", "email"), ("customers", "phone"),
                          ("orders", "coupon_code"), ("reviews", "title")]:
        assert one(f"SELECT COUNT(*) FROM {table} WHERE trim({column}) = ''") == 0, (table, column)
    # Verzonden of niet: shipped_date is NULL precies bij pending, processing en cancelled.
    assert one("SELECT COUNT(*) FROM orders WHERE (shipped_date IS NULL) <> "
               "(status IN ('pending', 'processing', 'cancelled'))") == 0

    # --- Getallen met een breed bereik -----------------------------------------
    lo_price, hi_price = q("SELECT MIN(price), MAX(price) FROM products")[0]
    assert 5 <= lo_price <= 6 and 2400 <= hi_price <= 2500, (lo_price, hi_price)
    lo_w, hi_w = q("SELECT MIN(weight_g), MAX(weight_g) FROM products")[0]
    assert lo_w <= 20 and hi_w >= 5000, (lo_w, hi_w)
    lo_b, hi_b = q("SELECT MIN(battery_hours), MAX(battery_hours) FROM products")[0]
    assert lo_b <= 5 and hi_b >= 300, (lo_b, hi_b)
    assert one("SELECT COUNT(*) FROM products WHERE price > 1000") >= 5
    assert one("SELECT COUNT(*) FROM products WHERE price BETWEEN 50 AND 100") >= 10
    assert one("SELECT COUNT(*) FROM products WHERE stock = 0") >= 5
    assert values("SELECT DISTINCT rating FROM reviews") == [1, 2, 3, 4, 5]
    assert set(values("SELECT DISTINCT discount_pct FROM order_items")) \
        == {0} | set(PROMO_DISCOUNTS) | set(COUPONS.values())
    assert one("SELECT COUNT(*) FROM order_items WHERE discount_pct > 0") >= 500
    assert one("SELECT COUNT(*) FROM order_items oi JOIN products p ON p.product_id = oi.product_id "
               "WHERE oi.unit_price <> p.price") >= 100
    assert one("SELECT MAX(quantity) FROM order_items") == 40  # de bulkbestelling

    # --- Weinig verschillende waarden: IN / NOT IN en DISTINCT -----------------
    assert values("SELECT DISTINCT status FROM orders") == sorted(STATUSES)
    assert values("SELECT DISTINCT payment_method FROM orders") == sorted(p for p, _ in PAYMENT_METHODS)
    assert values("SELECT DISTINCT shipping_method FROM orders") == sorted(s for s, _ in SHIPPING_METHODS)
    assert values("SELECT DISTINCT coupon_code FROM orders WHERE coupon_code IS NOT NULL") == sorted(COUPONS)
    assert 8 <= one("SELECT COUNT(DISTINCT country) FROM brands") <= 12
    assert 6 <= one("SELECT COUNT(DISTINCT color) FROM products") <= 10
    for value in STATUSES:  # elke status komt genoeg voor om mee te filteren
        assert one(f"SELECT COUNT(*) FROM orders WHERE status = '{value}'") >= 5, value

    # --- "Vuile" records --------------------------------------------------------
    assert one("SELECT COUNT(*) FROM customers WHERE city <> upper(substr(city, 1, 1)) || substr(city, 2)") == 2
    assert one("SELECT COUNT(*) FROM customers WHERE LOWER(city) = 'gent'") \
        == one("SELECT COUNT(*) FROM customers WHERE city = 'Gent'") + 1
    assert len(q("SELECT email FROM customers WHERE email IS NOT NULL "
                 "GROUP BY email HAVING COUNT(*) > 1")) == 1

    # --- Voor latere overhoringen: JOIN, GROUP BY, HAVING -----------------------
    assert one("SELECT COUNT(*) FROM customers WHERE customer_id NOT IN "
               "(SELECT customer_id FROM orders)") >= 30
    assert one("SELECT COUNT(*) FROM products WHERE product_id NOT IN "
               "(SELECT product_id FROM order_items)") >= 3
    assert one("SELECT COUNT(*) FROM products WHERE product_id NOT IN "
               "(SELECT product_id FROM reviews)") >= 10
    assert one("SELECT COUNT(*) FROM products WHERE product_id NOT IN (SELECT product_id FROM order_items) "
               "AND product_id NOT IN (SELECT product_id FROM reviews)") >= 2
    assert one("SELECT COUNT(*) FROM brands WHERE brand_id NOT IN "
               "(SELECT brand_id FROM products)") == len(BRANDS_WITHOUT_PRODUCTS)
    assert one("SELECT COUNT(*) FROM categories WHERE parent_category_id IS NULL") >= 4
    assert one("SELECT COUNT(*) FROM categories c WHERE parent_category_id IS NOT NULL "
               "AND category_id NOT IN (SELECT category_id FROM products)") >= 1
    assert one("SELECT COUNT(*) FROM products p JOIN categories c ON c.category_id = p.category_id "
               "WHERE c.parent_category_id IS NULL") == 0  # producten hangen onder een subcategorie
    assert one("SELECT COUNT(*) FROM reviews WHERE verified_purchase = 0") >= 150
    assert one("SELECT COUNT(*) FROM (SELECT customer_id FROM orders GROUP BY customer_id "
               "HAVING COUNT(*) = 1)") >= 30
    assert one("SELECT COUNT(*) FROM (SELECT customer_id FROM orders GROUP BY customer_id "
               "HAVING COUNT(*) >= 20)") >= 10
    assert one("SELECT COUNT(*) FROM orders WHERE order_id NOT IN (SELECT order_id FROM order_items)") == 0

    # --- Samenhang ----------------------------------------------------------------
    # verified_purchase = 1: de klant kreeg het product geleverd voor de review.
    assert one("""
        SELECT COUNT(*) FROM reviews r WHERE r.verified_purchase = 1 AND NOT EXISTS (
          SELECT 1 FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
          WHERE o.customer_id = r.customer_id AND oi.product_id = r.product_id
            AND o.status IN ('delivered', 'returned') AND o.shipped_date <= r.review_date)
    """) == 0
    # verified_purchase = 0: de klant kocht het product hier nooit.
    assert one("""
        SELECT COUNT(*) FROM reviews r WHERE r.verified_purchase = 0 AND EXISTS (
          SELECT 1 FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
          WHERE o.customer_id = r.customer_id AND oi.product_id = r.product_id)
    """) == 0
    assert not q("SELECT product_id, customer_id FROM reviews GROUP BY product_id, customer_id "
                 "HAVING COUNT(*) > 1")
    assert one("SELECT COUNT(*) FROM orders o JOIN customers c ON c.customer_id = o.customer_id "
               "WHERE o.order_date < c.join_date") == 0
    assert one("SELECT COUNT(*) FROM orders WHERE shipped_date < order_date") == 0
    assert one("SELECT COUNT(*) FROM order_items oi JOIN orders o ON o.order_id = oi.order_id "
               "JOIN products p ON p.product_id = oi.product_id WHERE o.order_date < p.release_date") == 0
    assert one("SELECT COUNT(*) FROM reviews r JOIN customers c ON c.customer_id = r.customer_id "
               "JOIN products p ON p.product_id = r.product_id "
               "WHERE r.review_date < c.join_date OR r.review_date < p.release_date") == 0
    assert one("SELECT COUNT(*) FROM customers WHERE birth_date >= join_date") == 0
    assert one("SELECT MAX(order_date) FROM orders") <= END_DATE.isoformat()
    assert one("SELECT MAX(review_date) FROM reviews") <= END_DATE.isoformat()
    assert one("SELECT COUNT(*) FROM products WHERE discontinued = 1 AND stock <> 0") == 0
    return counts


def build(path: Path = DB_PATH) -> dict[str, int]:
    """Genereer de databank in `path` en controleer ze. Geeft het aantal rijen per tabel."""
    write_db(path, generate())
    return verify(path)


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    counts = build(path)
    con = sqlite3.connect(path)
    first, last = con.execute("SELECT MIN(order_date), MAX(order_date) FROM orders").fetchone()
    con.close()
    print("OK: " + ", ".join(f"{t} {n}" for t, n in counts.items()))
    print(f"    bestellingen: {first} .. {last}")
    print(f"    bestand: {path} ({path.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
