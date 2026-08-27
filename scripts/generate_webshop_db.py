#!/usr/bin/env python3
"""Genereert book/_static/db/webshop.db met realistische datavolumes (issue #3).

Gebruik:
    python scripts/generate_webshop_db.py

Het script is deterministisch (vaste seed): elke run produceert exact dezelfde
data. Pas de constantes hieronder aan en run opnieuw om de dataset te wijzigen.

De dataset is afgestemd op de oefeningen in book/chapters/SQL/ en
book/chapters/ERD/. Onderaan het script staan controles (asserts) die de
belangrijkste verwachtingen van de lessen bewaken:

- 200-400 klanten, verspreid over meerdere steden/postcodes
- enkele duizenden orders over bijna 3 jaar, met seizoenspatronen
- klanten met 0, 1 en veel bestellingen (LEFT JOIN- en HAVING-oefeningen)
- bewuste NULL-waarden en enkele "vuile" records:
    * klanten zonder e-mail (les 2: IS NULL)
    * twee klanten met NULL als postcode
    * een klant met stad 'gent' in kleine letters (les 2: LOWER()-tip)
    * een dubbel e-mailadres (ERD les 1: mini-analyse op UNIQUE)
    * drie bestellingen zonder orderregels (les 3: LEFT JOIN-oefening)
    * een orderregel met een uitschieter-hoeveelheid (bulkbestelling)
- (order_id, product_id) is uniek binnen order_lines (ERD les 1 noemt dit
  een samengestelde sleutel)
- producten die nooit besteld werden (les 3: LEFT JOIN-oefening)
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SEED = 20260827
DB_PATH = Path(__file__).resolve().parent.parent / "book" / "_static" / "db" / "webshop.db"

# Periode waarin bestellingen geplaatst worden.
START_DATE = date(2023, 1, 1)
END_DATE = date(2025, 8, 31)   # "vandaag" voor deze dataset

# ---------------------------------------------------------------------------
# Vaste basisdata: de originele 10 klanten en 12 producten blijven behouden,
# zodat voorbeelden uit de lessen (Ait, ontbrekende e-mails, ...) blijven werken.
# ---------------------------------------------------------------------------

ORIGINAL_CUSTOMERS = [
    (1, "Lena", "De Smet", "lena.ds@example.com", "Antwerpen", "2000", "2024-09-03"),
    (2, "Youssef", "Ait", "y.ait@example.com", "Gent", "9000", "2024-10-12"),
    (3, "Mila", "Verbeeck", None, "Leuven", "3000", "2025-01-15"),
    (4, "Arne", "Peeters", "arne.p@example.com", "Antwerpen", "2018", "2024-11-08"),
    (5, "Noor", "Wauters", "noor.w@example.com", "Mechelen", "2800", "2025-02-20"),
    (6, "Jasper", "Willems", "jasper.w@example.com", "Brugge", "8000", "2024-12-01"),
    (7, "Amira", "Boukhriss", "amira.b@example.com", "Hasselt", "3500", "2025-03-05"),
    (8, "Finn", "Maes", "finn.m@example.com", "Antwerpen", "2000", "2025-03-09"),
    (9, "Laura", "Goossens", None, "Kortrijk", "8500", "2024-09-21"),
    (10, "Bo", "Declercq", "bo.d@example.com", "Gent", "9000", "2025-04-02"),
]

PRODUCTS = [
    # (product_id, name, category, unit_price, stock)
    (1, "Pro Laptop 14", "Computers", 1399.0, 12),
    (2, "Gaming Laptop X", "Gaming", 1799.0, 7),
    (3, "Office Mouse", "Peripherals", 19.9, 120),
    (4, "Mechanical Keyboard", "Peripherals", 89.0, 35),
    (5, '4K Monitor 27"', "Displays", 349.0, 18),
    (6, "USB-C Dock", "Peripherals", 129.0, 15),
    (7, "Noise-Cancel Headset", "Audio", 159.0, 22),
    (8, "External SSD 1TB", "Storage", 109.0, 40),
    (9, "Pro Phone Case", "Accessories", 24.5, 60),
    (10, "Gaming Chair", "Gaming", 229.0, 8),
    (11, "Color Ink Set", "Supplies", 49.0, 25),
    (12, "Laser Printer", "Printers", 199.0, 5),
    # Uitbreiding van de catalogus
    (13, "Ultrabook 13", "Computers", 1099.0, 14),
    (14, "Pro Laptop 16", "Computers", 1899.0, 9),
    (15, "Budget Laptop 15", "Computers", 649.0, 21),
    (16, "Desktop Tower i7", "Computers", 1149.0, 6),
    (17, "Mini PC", "Computers", 519.0, 11),
    (18, "Gaming Desktop RGB", "Gaming", 2099.0, 4),
    (19, "Gaming Mouse", "Gaming", 59.0, 80),
    (20, "Gaming Headset RGB", "Gaming", 99.0, 45),
    (21, "Racing Wheel", "Gaming", 299.0, 9),
    (22, 'Curved Monitor 34"', "Displays", 549.0, 10),
    (23, 'Full HD Monitor 24"', "Displays", 149.0, 30),
    (24, 'Portable Monitor 15"', "Displays", 199.0, 12),
    (25, "Webcam 1080p", "Peripherals", 69.0, 50),
    (26, "Wireless Keyboard", "Peripherals", 49.0, 60),
    (27, "Ergonomic Mouse", "Peripherals", 44.5, 55),
    (28, "USB Hub 4-port", "Peripherals", 24.9, 90),
    (29, "Bluetooth Speaker", "Audio", 79.0, 40),
    (30, "Studio Microphone", "Audio", 129.0, 15),
    (31, "Earbuds Pro", "Audio", 199.0, 35),
    (32, "External HDD 4TB", "Storage", 129.0, 25),
    (33, "USB Stick 128GB", "Storage", 19.9, 150),
    (34, "MicroSD 256GB", "Storage", 34.9, 70),
    (35, 'Laptop Sleeve 14"', "Accessories", 29.9, 40),
    (36, "Laptop Stand", "Accessories", 39.9, 30),
    (37, "Cable Kit USB-C", "Accessories", 14.9, 120),
    (38, "Inkjet Printer", "Printers", 89.0, 8),
    (39, "A4 Paper 5x500", "Supplies", 24.9, 60),
    # Nooit besteld (LEFT JOIN-oefening: producten zonder bestellingen)
    (40, "Fax Modem 56k", "Printers", 39.0, 3),
    (41, "DVD-R Spindle 25", "Supplies", 12.5, 18),
]

NEVER_ORDERED = {40, 41}

FIRST_NAMES = [
    "Anna", "Amber", "Axel", "Adam", "Aline", "Bram", "Britt", "Cas", "Céline",
    "Daan", "Dina", "Elias", "Emma", "Ferre", "Fleur", "Gilles", "Hanne",
    "Ibrahim", "Ilias", "Jana", "Jef", "Jules", "Kato", "Kobe", "Lars", "Lien",
    "Lotte", "Lucas", "Marie", "Mathis", "Milan", "Nina", "Noa", "Omar",
    "Pieter", "Quinten", "Rania", "Robbe", "Sam", "Sara", "Senne", "Stan",
    "Thomas", "Tuur", "Victor", "Warre", "Wout", "Yana", "Zoë", "Elif",
]

LAST_NAMES = [
    "Claes", "Cox", "Vos", "Bos", "Janssens", "Peeters", "Maes", "Jacobs",
    "Mertens", "Willems", "Wouters", "De Backer", "De Clercq", "De Vos",
    "Van Damme", "Van den Berg", "Vermeulen", "Vercauteren", "Hermans",
    "Aerts", "Segers", "Pauwels", "Dubois", "Lemmens", "Michiels", "Smets",
    "Stevens", "Van Acker", "Verhoeven", "Deckers", "Yildiz", "El Amrani",
    "Nguyen", "Kaya", "Costa", "De Ridder", "Van Hoof", "Bogaerts",
]

# (stad, [postcodes], gewicht)
CITIES = [
    ("Antwerpen", ["2000", "2018", "2060"], 16),
    ("Gent", ["9000"], 12),
    ("Brussel", ["1000", "1050"], 10),
    ("Leuven", ["3000"], 8),
    ("Brugge", ["8000"], 7),
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
]

# Seizoensgewichten per maand (1-12): eindejaar piekt, zomer is kalmer.
SEASON_WEIGHT = {
    1: 1.15, 2: 0.85, 3: 0.95, 4: 1.0, 5: 1.0, 6: 0.9,
    7: 0.8, 8: 0.85, 9: 1.25, 10: 1.1, 11: 1.7, 12: 2.1,
}

# Groei van de webshop per jaar.
YEAR_WEIGHT = {2023: 0.75, 2024: 1.0, 2025: 1.3}

N_EXTRA_CUSTOMERS = 290  # totaal = 300


def month_range(start: date, end: date):
    """Alle (jaar, maand)-paren tussen start en end (inclusief)."""
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def days_in_month(year: int, month: int) -> int:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def make_customers(rng: random.Random):
    customers = list(ORIGINAL_CUSTOMERS)
    used_emails = {c[3] for c in customers if c[3]}
    city_pool = [(c, pcs) for c, pcs, w in CITIES for _ in range(w)]

    join_start = date(2022, 6, 1)
    join_end = date(2025, 8, 15)
    join_span = (join_end - join_start).days

    cid = 11
    for _ in range(N_EXTRA_CUSTOMERS):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        city, pcs = rng.choice(city_pool)
        pc = rng.choice(pcs)
        join = join_start + timedelta(days=rng.randint(0, join_span))

        if rng.random() < 0.06:
            email = None  # bewuste NULL (les 2)
        else:
            base = f"{fn.lower()}.{ln.lower().replace(' ', '')}"
            base = (base.replace("é", "e").replace("ë", "e").replace("ö", "o"))
            email = f"{base}@example.com"
            n = 2
            while email in used_emails:
                email = f"{base}{n}@example.com"
                n += 1
            used_emails.add(email)

        customers.append((cid, fn, ln, email, city, pc, join.isoformat()))
        cid += 1

    # --- Bewust "vuile" records -------------------------------------------
    # Stad in kleine letters: voer voor de LOWER()-tip in les 2.
    customers.append((cid, "Jonas", "Verstraete", "jonas.verstraete@example.com",
                      "gent", "9000", "2024-05-14"))
    cid += 1
    # Dubbel e-mailadres: twee registraties van dezelfde persoon
    # (ERD les 1: controleer of e-mails uniek zijn).
    customers.append((cid, "Jan", "Claes", "jan.claes.dup@example.com",
                      "Diksmuide", "8600", "2023-03-02"))
    cid += 1
    customers.append((cid, "Jan", "Claes", "jan.claes.dup@example.com",
                      "Diksmuide", "8600", "2024-11-19"))
    cid += 1
    # Twee klanten zonder postcode.
    customers.append((cid, "Nora", "Beckers", "nora.beckers@example.com",
                      "Leuven", None, "2023-09-30"))
    cid += 1
    customers.append((cid, "Seppe", "Moens", None, "Antwerpen", None, "2024-02-11"))
    cid += 1

    return customers


def assign_order_counts(rng: random.Random, customers):
    """Bepaal per klant hoeveel bestellingen die plaatst (0, 1 of veel)."""
    counts = {}
    for cust in customers:
        cid = cust[0]
        # De originele klanten 7 en 9 blijven zonder bestelling; klanten
        # 1-6, 8 en 10 bestellen zeker (oefeningen verwijzen naar id 1, 3, 5).
        if cid in (7, 9):
            counts[cid] = 0
            continue
        if cid <= 10:
            counts[cid] = rng.randint(2, 12)
            continue

        r = rng.random()
        if r < 0.10:
            counts[cid] = 0          # nooit besteld (LEFT JOIN)
        elif r < 0.26:
            counts[cid] = 1          # precies één bestelling
        elif r < 0.92:
            counts[cid] = rng.randint(2, 18)
        else:
            counts[cid] = rng.randint(25, 60)  # vaste klanten / kmo's
    return counts


def make_orders(rng: random.Random, customers, counts):
    """Genereer bestellingen met seizoenspatroon, na de join_date van de klant."""
    orders = []  # (customer_id, date)
    for cust in customers:
        cid, join = cust[0], date.fromisoformat(cust[6])
        n = counts[cid]
        if n == 0:
            continue
        first_possible = max(join, START_DATE)
        months = [(y, m) for (y, m) in month_range(first_possible, END_DATE)]
        if not months:
            continue
        weights = [SEASON_WEIGHT[m] * YEAR_WEIGHT[y] for (y, m) in months]
        for _ in range(n):
            y, m = rng.choices(months, weights=weights)[0]
            lo = 1
            if (y, m) == (first_possible.year, first_possible.month):
                lo = first_possible.day
            d = rng.randint(lo, days_in_month(y, m))
            orders.append((cid, date(y, m, d)))

    # Chronologisch nummeren vanaf 1001 (zoals in de oorspronkelijke database).
    orders.sort(key=lambda o: (o[1], o[0]))
    numbered = []
    for i, (cid, d) in enumerate(orders):
        numbered.append((1001 + i, cid, d))
    return numbered


def pick_status(rng: random.Random, d: date) -> str:
    if rng.random() < 0.04:
        return "cancelled"
    age = (END_DATE - d).days
    if age <= 14:
        return "processing" if rng.random() < 0.55 else "shipped"
    if age <= 31:
        return "shipped" if rng.random() < 0.6 else "delivered"
    return "delivered"


def make_order_lines(rng: random.Random, orders_with_status):
    """Orderregels: 1-5 regels per order, (order_id, product_id) uniek."""
    catalog = {p[0]: p for p in PRODUCTS if p[0] not in NEVER_ORDERED}
    ids = list(catalog)
    # Goedkope producten worden vaker verkocht dan dure.
    weights = [1.0 / (catalog[i][3] ** 0.5) for i in ids]

    # Drie geannuleerde bestellingen krijgen geen orderregels (les 3).
    cancelled = [o for o in orders_with_status if o[3] == "cancelled"]
    empty_orders = {o[0] for o in cancelled[:3]}

    lines = []
    line_id = 1
    for order_id, _cid, _d, status in orders_with_status:
        if order_id in empty_orders:
            continue
        n_lines = rng.choices([1, 2, 3, 4, 5], weights=[35, 30, 20, 10, 5])[0]
        chosen = set()
        while len(chosen) < n_lines:
            pid = rng.choices(ids, weights=weights)[0]
            chosen.add(pid)
        for pid in sorted(chosen):
            price = catalog[pid][3]
            if price < 50:
                qty = rng.choices([1, 2, 3, 4, 5], weights=[45, 30, 15, 6, 4])[0]
            elif price < 200:
                qty = rng.choices([1, 2, 3], weights=[70, 22, 8])[0]
            else:
                qty = rng.choices([1, 2], weights=[92, 8])[0]
            if rng.random() < 0.15:
                price = round(price * rng.choice([0.95, 0.9, 0.85, 0.8]), 2)
            lines.append((line_id, order_id, pid, qty, price))
            line_id += 1

    # Eén bulkbestelling als uitschieter: een school koopt 25 USB-sticks.
    bulk_candidates = [ln for ln in lines if ln[2] == 33]
    if bulk_candidates:
        ln = bulk_candidates[len(bulk_candidates) // 2]
        idx = lines.index(ln)
        lines[idx] = (ln[0], ln[1], ln[2], 25, ln[4])
    return lines, empty_orders


def build_db(customers, orders, lines):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE customers (
      customer_id   INTEGER PRIMARY KEY,
      first_name    TEXT NOT NULL,
      last_name     TEXT NOT NULL,
      email         TEXT,
      city          TEXT,
      postal_code   TEXT,
      join_date     TEXT  -- ISO: YYYY-MM-DD
    );
    CREATE TABLE products (
      product_id   INTEGER PRIMARY KEY,
      name         TEXT NOT NULL,
      category     TEXT NOT NULL,
      unit_price   REAL NOT NULL,
      stock        INTEGER NOT NULL
    );
    CREATE TABLE orders (
      order_id     INTEGER PRIMARY KEY,
      customer_id  INTEGER NOT NULL,
      order_date   TEXT NOT NULL,
      status       TEXT NOT NULL,
      FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );
    CREATE TABLE order_lines (
      order_line_id INTEGER PRIMARY KEY,
      order_id      INTEGER NOT NULL,
      product_id    INTEGER NOT NULL,
      quantity      INTEGER NOT NULL,
      unit_price    REAL NOT NULL, -- prijs bij verkoop (kan afwijken van catalogus)
      FOREIGN KEY (order_id) REFERENCES orders(order_id),
      FOREIGN KEY (product_id) REFERENCES products(product_id)
    );
    """)
    cur.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?)", customers)
    cur.executemany("INSERT INTO products VALUES (?,?,?,?,?)", PRODUCTS)
    cur.executemany(
        "INSERT INTO orders VALUES (?,?,?,?)",
        [(oid, cid, d.isoformat(), status) for oid, cid, d, status in orders],
    )
    cur.executemany("INSERT INTO order_lines VALUES (?,?,?,?,?)", lines)
    con.commit()
    cur.execute("VACUUM")
    con.close()


def verify():
    """Controleer de verwachtingen van de lessen. Faalt hard als iets ontbreekt."""
    con = sqlite3.connect(DB_PATH)
    q = lambda sql: con.execute(sql).fetchall()
    one = lambda sql: con.execute(sql).fetchone()[0]

    n_cust = one("SELECT COUNT(*) FROM customers")
    n_ord = one("SELECT COUNT(*) FROM orders")
    n_lines = one("SELECT COUNT(*) FROM order_lines")
    assert 200 <= n_cust <= 400, n_cust
    assert 2000 <= n_ord <= 6000, n_ord

    # Les 2: NULL-waarden en patronen
    assert one("SELECT COUNT(*) FROM customers WHERE email IS NULL") >= 5
    assert one("SELECT COUNT(*) FROM customers WHERE postal_code IS NULL") == 2
    assert one("SELECT COUNT(*) FROM customers WHERE city='gent'") == 1
    assert one("SELECT COUNT(*) FROM customers WHERE last_name LIKE '___' "
               "AND length(last_name)=3") >= 2
    assert one("SELECT COUNT(*) FROM orders WHERE order_date LIKE '2025-07-%'") > 0
    assert one("SELECT COUNT(*) FROM customers WHERE city IN ('Antwerpen','Brussel')") > 5

    # Les 1: steden, Brugge, laptops > 1500 euro
    assert one("SELECT COUNT(*) FROM customers WHERE city='Brugge'") >= 1
    assert one("SELECT COUNT(*) FROM products WHERE name LIKE '%Laptop%' "
               "AND unit_price > 1500") >= 2

    # Les 3: LEFT JOIN-oefeningen
    assert one("SELECT COUNT(*) FROM customers c LEFT JOIN orders o "
               "ON c.customer_id=o.customer_id WHERE o.order_id IS NULL") >= 15
    assert one("SELECT COUNT(*) FROM products p LEFT JOIN order_lines ol "
               "ON p.product_id=ol.product_id WHERE ol.order_line_id IS NULL") == 2
    assert one("SELECT COUNT(*) FROM orders o LEFT JOIN order_lines ol "
               "ON o.order_id=ol.order_id WHERE ol.order_line_id IS NULL") == 3

    # Les 4/5: GROUP BY en HAVING
    assert one("SELECT COUNT(*) FROM (SELECT customer_id FROM orders "
               "GROUP BY customer_id HAVING COUNT(*)=1)") >= 10
    assert one("SELECT COUNT(*) FROM (SELECT customer_id FROM orders "
               "GROUP BY customer_id HAVING COUNT(*)>1)") >= 50
    n20 = one("SELECT COUNT(*) FROM (SELECT customer_id FROM orders "
              "GROUP BY customer_id HAVING COUNT(*)>=20)")
    assert 5 <= n20 <= 40, n20  # voorbeeldquery in les 5 gebruikt >= 20
    assert one("SELECT COUNT(*) FROM (SELECT city FROM customers "
               "GROUP BY city HAVING COUNT(*)>1)") >= 5
    assert one("SELECT COUNT(*) FROM (SELECT city FROM customers "
               "GROUP BY city HAVING COUNT(*)=1)") >= 1
    assert one("SELECT COUNT(*) FROM (SELECT category FROM products "
               "GROUP BY category HAVING AVG(unit_price)>500)") >= 1

    # Oefening les 2: bestellingen van klant 1, 3 en 5
    for cid in (1, 3, 5):
        assert one(f"SELECT COUNT(*) FROM orders WHERE customer_id={cid}") > 0, cid

    # ERD les 1: samengestelde sleutel + dubbel e-mailadres
    assert not q("SELECT order_id, product_id FROM order_lines "
                 "GROUP BY order_id, product_id HAVING COUNT(*)>1")
    assert len(q("SELECT email FROM customers WHERE email IS NOT NULL "
                 "GROUP BY email HAVING COUNT(*)>1")) == 1

    # Alle vier de statussen komen voor; geen bestelling vóór de join_date.
    statuses = {r[0] for r in q("SELECT DISTINCT status FROM orders")}
    assert statuses == {"processing", "shipped", "delivered", "cancelled"}, statuses
    assert one("SELECT COUNT(*) FROM orders o JOIN customers c "
               "ON o.customer_id=c.customer_id WHERE o.order_date < c.join_date") == 0

    print(f"OK: {n_cust} klanten, {n_ord} orders, {n_lines} orderregels")
    print(f"    periode: {one('SELECT MIN(order_date) FROM orders')} .. "
          f"{one('SELECT MAX(order_date) FROM orders')}")
    print(f"    klanten met >= 20 bestellingen: {n20}")
    print(f"    bestand: {DB_PATH} ({DB_PATH.stat().st_size / 1024:.0f} KiB)")
    con.close()


def main():
    rng = random.Random(SEED)
    customers = make_customers(rng)
    counts = assign_order_counts(rng, customers)
    orders = make_orders(rng, customers, counts)
    orders_with_status = [(oid, cid, d, pick_status(rng, d)) for oid, cid, d in orders]
    lines, _empty = make_order_lines(rng, orders_with_status)
    build_db(customers, orders_with_status, lines)
    verify()


if __name__ == "__main__":
    main()
