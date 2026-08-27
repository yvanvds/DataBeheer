#!/usr/bin/env python3
"""Genereert book/_static/db/facturatie.db (issue #4).

Gebruik:
    python scripts/generate_facturatie_db.py

Het script is deterministisch (vaste seed): elke run produceert exact dezelfde
data. Pas de constantes hieronder aan en run opnieuw om de dataset te wijzigen.

De context: Kantoorplus bv, een fictieve groothandel in kantoormateriaal uit
Gent. Kantoorplus verkoopt aan Vlaamse bedrijven, scholen en verenigingen en
factureert met verschillende btw-tarieven (21%, 6% en vrijgesteld). Deze
database is de "andere economische context" naast webshop.db en
adventureworks.db, en wordt gebruikt in de herhalingsles
(book/chapters/SQL/06_Herhaling.ipynb).

Onderaan het script staan controles (asserts) die de verwachtingen van de
oefeningen bewaken:

- klanten zonder facturen (LEFT JOIN-oefening)
- twee producten die nooit gefactureerd werden (LEFT JOIN-oefening)
- openstaande facturen (betaald_op IS NULL) en te laat betaalde facturen
- klanten zonder btw-nummer (vzw's en scholen) en zonder e-mail
- voldoende spreiding over gemeenten (GROUP BY / HAVING)
- klanten met veel en met weinig facturen (HAVING)
- alle drie de btw-codes worden gebruikt in producten
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SEED = 20260827
DB_PATH = Path(__file__).resolve().parent.parent / "book" / "_static" / "db" / "facturatie.db"

# Periode waarin gefactureerd wordt.
START_DATE = date(2024, 1, 2)
END_DATE = date(2025, 8, 20)   # "vandaag" voor deze dataset

BETAALTERMIJN = 30  # dagen tussen factuurdatum en vervaldatum

# ---------------------------------------------------------------------------
# Btw-tarieven: een opzoektabel, zoals dat in echte facturatiepakketten werkt.
# ---------------------------------------------------------------------------

BTW_TARIEVEN = [
    # (btw_code, omschrijving, tarief)
    ("STD", "Standaardtarief", 21.0),
    ("VERL", "Verlaagd tarief (voeding en dranken)", 6.0),
    ("VRIJ", "Vrijgesteld (opleidingen)", 0.0),
]

# ---------------------------------------------------------------------------
# Producten: kantoormateriaal (21%), koffiehoek (6%) en opleidingen (0%).
# ---------------------------------------------------------------------------

PRODUCTEN = [
    # (product_id, naam, categorie, eenheidsprijs excl. btw, btw_code)
    (1, "Kopieerpapier A4 (doos 5x500)", "Papier", 24.95, "STD"),
    (2, "Enveloppen C5 (doos 500)", "Papier", 19.50, "STD"),
    (3, "Archiefdozen (pak 25)", "Papier", 32.00, "STD"),
    (4, "Balpennen blauw (doos 50)", "Schrijfwaren", 14.75, "STD"),
    (5, "Markeerstiften (set 6)", "Schrijfwaren", 8.90, "STD"),
    (6, "Post-its (pak 12)", "Schrijfwaren", 11.40, "STD"),
    (7, "Ordners A4 (pak 10)", "Schrijfwaren", 27.50, "STD"),
    (8, "Toner zwart XL", "Printen", 89.00, "STD"),
    (9, "Toner kleurenset", "Printen", 189.00, "STD"),
    (10, "Multifunctionele printer", "Printen", 449.00, "STD"),
    (11, "Bureaustoel ergonomisch", "Meubilair", 279.00, "STD"),
    (12, "Zit-sta bureau", "Meubilair", 595.00, "STD"),
    (13, "Vergadertafel 8 personen", "Meubilair", 849.00, "STD"),
    (14, "Whiteboard 120x90", "Meubilair", 74.50, "STD"),
    (15, "Koffiemachine professioneel", "Dranken", 1249.00, "STD"),
    (16, "Koffiebonen huisblend 1 kg", "Dranken", 16.80, "VERL"),
    (17, "Thee assortiment (doos 100)", "Dranken", 9.95, "VERL"),
    (18, "Bruiswater (krat 24)", "Dranken", 11.20, "VERL"),
    (19, "Plat water (krat 24)", "Dranken", 9.60, "VERL"),
    (20, "Koekjes assortiment (doos)", "Dranken", 13.50, "VERL"),
    (21, "Opleiding: Excel voor starters", "Opleidingen", 350.00, "VRIJ"),
    (22, "Opleiding: ergonomisch werken", "Opleidingen", 295.00, "VRIJ"),
    # Nooit gefactureerd (LEFT JOIN-oefening: producten zonder verkoop)
    (23, "Flipchart op wielen", "Meubilair", 129.00, "STD"),
    (24, "Workshop: duurzaam kantoor", "Opleidingen", 395.00, "VRIJ"),
]

NOOIT_GEFACTUREERD = {23, 24}

# ---------------------------------------------------------------------------
# Klanten: Vlaamse bedrijven, scholen en verenigingen. Scholen en vzw's
# hebben geen btw-nummer (NULL). Sommige klanten hebben (nog) geen facturen.
# ---------------------------------------------------------------------------

KLANTEN = [
    # (klant_id, bedrijfsnaam, contactpersoon, email, gemeente, postcode,
    #  btw_nummer, klant_sinds)
    (1, "Advocatenkantoor Peeters & Partners", "Els Peeters", "els@peeters-partners.be", "Gent", "9000", "BE 0451.223.887", "2021-03-15"),
    (2, "Bakkerij Vermeulen bv", "Jan Vermeulen", "info@bakkerijvermeulen.be", "Gent", "9000", "BE 0472.118.334", "2020-09-01"),
    (3, "Garage Smets bv", "Karim Smets", "karim@garagesmets.be", "Aalst", "9300", "BE 0463.554.201", "2022-01-10"),
    (4, "Boekhandel De Kaft", "Mieke Baert", "mieke@dekaft.be", "Brugge", "8000", "BE 0489.667.412", "2021-11-05"),
    (5, "IT-Consult Vlaanderen nv", "Tom Segers", "tom.segers@itconsult.be", "Antwerpen", "2000", "BE 0440.887.665", "2019-06-20"),
    (6, "Basisschool De Regenboog", "Hilde Claes", "directie@deregenboog.be", "Gent", "9000", None, "2020-02-12"),
    (7, "Sportclub Blauw-Wit vzw", "Dirk Wouters", None, "Mechelen", "2800", None, "2023-04-18"),
    (8, "Tuinaanleg Groenendaal bv", "An Groenendaal", "an@groenendaal.be", "Leuven", "3000", "BE 0455.909.118", "2022-07-01"),
    (9, "Kinesitherapie Vandamme", "Sofie Vandamme", "sofie@kinevandamme.be", "Kortrijk", "8500", "BE 0491.202.876", "2023-09-14"),
    (10, "Interieurstudio Nova bv", "Lies Nijs", "lies@studionova.be", "Antwerpen", "2018", "BE 0478.345.990", "2021-05-30"),
    (11, "Boekhoudkantoor Cijfers & Co", "Peter Maes", "peter@cijfersenco.be", "Hasselt", "3500", "BE 0446.778.123", "2020-10-22"),
    (12, "Middenschool Sint-Lievens", "Marc De Wilde", "secretariaat@sintlievens.be", "Sint-Niklaas", "9100", None, "2021-01-08"),
    (13, "Fietsen Verstraete bv", "Bart Verstraete", "bart@fietsenverstraete.be", "Brugge", "8000", "BE 0467.812.554", "2022-03-25"),
    (14, "Notariskantoor Lambrecht", "Eva Lambrecht", "eva@notarislambrecht.be", "Gent", "9000", "BE 0432.665.909", "2019-12-03"),
    (15, "Jeugdhuis De Fabriek vzw", "Senne Jacobs", "senne@defabriek.be", "Aalst", "9300", None, "2024-02-06"),
    (16, "Immo Van Hecke bv", "Griet Van Hecke", "griet@immovanhecke.be", "Antwerpen", "2000", "BE 0483.221.437", "2020-06-17"),
    (17, "Drukkerij Moderna nv", "Rudi Cools", "rudi@drukkerijmoderna.be", "Mechelen", "2800", "BE 0429.554.318", "2019-04-09"),
    (18, "Apotheek Centrum Deckers", "Ilse Deckers", None, "Leuven", "3000", "BE 0494.667.230", "2023-01-19"),
    (19, "Schildersbedrijf Kleur & Zo", "Nico Pauwels", "nico@kleurenzo.be", "Kortrijk", "8500", "BE 0475.990.612", "2022-11-11"),
    (20, "Webbureau Pixelwerk bv", "Lore Michiels", "lore@pixelwerk.be", "Gent", "9000", "BE 0487.113.845", "2021-08-24"),
    (21, "Traiteur Casteleyn", "Wim Casteleyn", "wim@traiteurcasteleyn.be", "Oostende", "8400", "BE 0459.302.771", "2022-05-16"),
    (22, "Kapsalon Hair & There", "Nadia El Amrani", "nadia@hairandthere.be", "Hasselt", "3500", "BE 0490.876.554", "2023-06-28"),
    (23, "Bouwbedrijf Verhoeven nv", "Stijn Verhoeven", "stijn@bouwverhoeven.be", "Antwerpen", "2060", "BE 0426.190.883", "2019-02-14"),
    (24, "Dansacademie Pirouette vzw", "Charlotte Lemmens", "info@pirouette.be", "Brugge", "8000", None, "2023-11-07"),
    (25, "Veeartsenpraktijk De Grote Weide", "Jef Hermans", "jef@degroteweide.be", "Turnhout", "2300", "BE 0468.445.196", "2022-09-02"),
    (26, "Brouwerij 't Vat bv", "Koen Aerts", "koen@brouwerijhetvat.be", "Leuven", "3000", "BE 0452.778.640", "2020-04-27"),
    (27, "Optiek Helder", "Tine Bogaerts", "tine@optiekhelder.be", "Sint-Niklaas", "9100", "BE 0481.556.902", "2023-03-13"),
    (28, "Zorgcentrum Avondrust vzw", "Rita Van Acker", "administratie@avondrust.be", "Mechelen", "2800", None, "2020-08-19"),
    (29, "Transport Declerck & Zonen", "Frank Declerck", "frank@transportdeclerck.be", "Roeselare", "8800", "BE 0437.209.115", "2021-06-09"),
    (30, "Architectenbureau Lijnrecht", "Astrid Smets", None, "Gent", "9000", "BE 0492.887.336", "2024-01-15"),
    (31, "Slagerij Goossens bv", "Luc Goossens", "luc@slagerijgoossens.be", "Aalst", "9300", "BE 0464.112.909", "2021-10-04"),
    (32, "Reisbureau Horizon", "Katrien Willems", "katrien@reishorizon.be", "Oostende", "8400", "BE 0477.665.148", "2022-12-08"),
    (33, "Tandartspraktijk Smile", "Bram Stevens", "bram@tandartssmile.be", "Hasselt", "3500", "BE 0488.301.552", "2023-08-21"),
    (34, "Schoonmaak Blinkend bv", "Fatma Yildiz", "fatma@blinkend.be", "Genk", "3600", "BE 0470.994.827", "2021-04-12"),
    (35, "Muziekschool Con Brio vzw", "Pieter De Ridder", "info@conbrio.be", "Kortrijk", "8500", None, "2022-02-23"),
    (36, "Fitnesscentrum PowerUp", "Sven Vercauteren", "sven@powerup.be", "Antwerpen", "2000", "BE 0485.190.663", "2023-05-02"),
    (37, "Bloemen Rozemarijn", "Marijke Segers", "marijke@rozemarijn.be", "Lier", "2500", "BE 0493.556.014", "2024-03-11"),
    (38, "Advies & Audit Van den Berg nv", "Joris Van den Berg", "joris@vdb-audit.be", "Gent", "9000", "BE 0431.887.502", "2019-09-26"),
    (39, "Kinderopvang 't Nestje vzw", "Leen Vos", "leen@hetnestje.be", "Leuven", "3000", None, "2022-06-15"),
    (40, "Elektro Janssens bv", "Dirk Janssens", "dirk@elektrojanssens.be", "Turnhout", "2300", "BE 0466.023.781", "2020-11-30"),
    # Nieuwe klanten zonder facturen (LEFT JOIN-oefening)
    (41, "Copywriting Studio Vlot", "Emma Claes", "emma@studiovlot.be", "Gent", "9000", "BE 0495.667.890", "2025-07-28"),
    (42, "Hondentrimsalon Wafwaf", "Jelle Mertens", None, "Brugge", "8000", "BE 0496.112.045", "2025-08-05"),
    (43, "Theatergroep De Spiegel vzw", "Lisa Dubois", "lisa@despiegel.be", "Mechelen", "2800", None, "2025-08-12"),
    (44, "Juwelier Goudmerk", "Omar Kaya", "omar@goudmerk.be", "Antwerpen", "2000", "BE 0497.303.518", "2025-06-19"),
]

ZONDER_FACTUREN = {41, 42, 43, 44}

# Grote klanten: bestellen bijna maandelijks (HAVING-oefeningen).
GROTE_KLANTEN = {5, 6, 12, 17, 23, 28, 38}


def make_facturen(rng: random.Random):
    """Genereer facturen per klant, na klant_sinds en binnen de periode."""
    facturen = []  # (klant_id, factuurdatum)
    for klant in KLANTEN:
        kid = klant[0]
        if kid in ZONDER_FACTUREN:
            continue
        sinds = date.fromisoformat(klant[7])
        first_possible = max(sinds, START_DATE)
        span = (END_DATE - first_possible).days
        if span <= 0:
            continue
        if kid in GROTE_KLANTEN:
            n = rng.randint(14, 24)
        else:
            r = rng.random()
            if r < 0.12:
                n = 1
            elif r < 0.75:
                n = rng.randint(2, 8)
            else:
                n = rng.randint(9, 13)
        for _ in range(n):
            d = first_possible + timedelta(days=rng.randint(0, span))
            facturen.append((kid, d))

    # Chronologisch nummeren vanaf 2401 (jaar 2024, eerste reeks).
    facturen.sort(key=lambda f: (f[1], f[0]))
    return [(2401 + i, kid, d) for i, (kid, d) in enumerate(facturen)]


def pick_betaald_op(rng: random.Random, factuurdatum: date) -> str | None:
    """Bepaal wanneer (en of) een factuur betaald werd."""
    vervaldatum = factuurdatum + timedelta(days=BETAALTERMIJN)
    leeftijd = (END_DATE - factuurdatum).days

    if leeftijd <= 20:
        # Recente facturen: meestal nog niet betaald.
        if rng.random() < 0.75:
            return None
        betaald = factuurdatum + timedelta(days=rng.randint(3, max(3, leeftijd)))
        return betaald.isoformat()

    r = rng.random()
    if r < 0.06:
        return None  # wanbetaler: vervaldatum al lang voorbij
    if r < 0.24:
        # Te laat betaald: na de vervaldatum.
        betaald = vervaldatum + timedelta(days=rng.randint(1, 45))
    else:
        # Netjes binnen de betaaltermijn.
        betaald = factuurdatum + timedelta(days=rng.randint(2, BETAALTERMIJN))
    return min(betaald, END_DATE).isoformat()


def make_factuurlijnen(rng: random.Random, facturen):
    """Factuurlijnen: 1-6 lijnen per factuur, (factuur_id, product_id) uniek."""
    catalogus = {p[0]: p for p in PRODUCTEN if p[0] not in NOOIT_GEFACTUREERD}
    ids = list(catalogus)
    # Verbruiksmateriaal wordt vaker besteld dan meubilair of opleidingen.
    gewichten = [1.0 / (catalogus[i][3] ** 0.5) for i in ids]

    lijnen = []
    lijn_id = 1
    for factuur_id, _kid, _d, _v, _b in facturen:
        n_lijnen = rng.choices([1, 2, 3, 4, 5, 6], weights=[20, 28, 24, 15, 8, 5])[0]
        gekozen = set()
        while len(gekozen) < n_lijnen:
            pid = rng.choices(ids, weights=gewichten)[0]
            gekozen.add(pid)
        for pid in sorted(gekozen):
            _, _naam, categorie, prijs, _btw = catalogus[pid]
            if categorie == "Opleidingen":
                aantal = rng.choices([1, 2], weights=[85, 15])[0]
            elif prijs < 20:
                aantal = rng.choices([2, 4, 6, 10, 20], weights=[25, 30, 22, 15, 8])[0]
            elif prijs < 100:
                aantal = rng.choices([1, 2, 3, 5], weights=[40, 30, 20, 10])[0]
            else:
                aantal = rng.choices([1, 2, 4], weights=[75, 18, 7])[0]
            # Vaste klanten krijgen af en toe korting op de catalogusprijs.
            if rng.random() < 0.12:
                prijs = round(prijs * rng.choice([0.95, 0.9]), 2)
            lijnen.append((lijn_id, factuur_id, pid, aantal, prijs))
            lijn_id += 1
    return lijnen


def build_db(facturen, lijnen):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE btw_tarieven (
      btw_code      TEXT PRIMARY KEY,
      omschrijving  TEXT NOT NULL,
      tarief        REAL NOT NULL  -- percentage, bv. 21.0
    );
    CREATE TABLE klanten (
      klant_id       INTEGER PRIMARY KEY,
      bedrijfsnaam   TEXT NOT NULL,
      contactpersoon TEXT,
      email          TEXT,
      gemeente       TEXT NOT NULL,
      postcode       TEXT NOT NULL,
      btw_nummer     TEXT,          -- NULL voor scholen en vzw's
      klant_sinds    TEXT NOT NULL  -- ISO: YYYY-MM-DD
    );
    CREATE TABLE producten (
      product_id    INTEGER PRIMARY KEY,
      naam          TEXT NOT NULL,
      categorie     TEXT NOT NULL,
      eenheidsprijs REAL NOT NULL,  -- excl. btw
      btw_code      TEXT NOT NULL,
      FOREIGN KEY (btw_code) REFERENCES btw_tarieven(btw_code)
    );
    CREATE TABLE facturen (
      factuur_id   INTEGER PRIMARY KEY,
      klant_id     INTEGER NOT NULL,
      factuurdatum TEXT NOT NULL,
      vervaldatum  TEXT NOT NULL,   -- factuurdatum + 30 dagen
      betaald_op   TEXT,            -- NULL = nog niet betaald
      FOREIGN KEY (klant_id) REFERENCES klanten(klant_id)
    );
    CREATE TABLE factuurlijnen (
      lijn_id       INTEGER PRIMARY KEY,
      factuur_id    INTEGER NOT NULL,
      product_id    INTEGER NOT NULL,
      aantal        INTEGER NOT NULL,
      eenheidsprijs REAL NOT NULL,  -- prijs op de factuur (kan korting bevatten)
      FOREIGN KEY (factuur_id) REFERENCES facturen(factuur_id),
      FOREIGN KEY (product_id) REFERENCES producten(product_id)
    );
    """)
    cur.executemany("INSERT INTO btw_tarieven VALUES (?,?,?)", BTW_TARIEVEN)
    cur.executemany("INSERT INTO klanten VALUES (?,?,?,?,?,?,?,?)", KLANTEN)
    cur.executemany("INSERT INTO producten VALUES (?,?,?,?,?)", PRODUCTEN)
    cur.executemany(
        "INSERT INTO facturen VALUES (?,?,?,?,?)",
        [(fid, kid, d.isoformat(), v.isoformat(), b) for fid, kid, d, v, b in facturen],
    )
    cur.executemany("INSERT INTO factuurlijnen VALUES (?,?,?,?,?)", lijnen)
    con.commit()
    cur.execute("VACUUM")
    con.close()


def verify():
    """Controleer de verwachtingen van de oefeningen. Faalt hard bij een gat."""
    con = sqlite3.connect(DB_PATH)
    q = lambda sql: con.execute(sql).fetchall()
    one = lambda sql: con.execute(sql).fetchone()[0]

    n_klant = one("SELECT COUNT(*) FROM klanten")
    n_fact = one("SELECT COUNT(*) FROM facturen")
    n_lijn = one("SELECT COUNT(*) FROM factuurlijnen")
    assert 40 <= n_klant <= 60, n_klant
    assert 150 <= n_fact <= 400, n_fact

    # Reeks 2: NULL-waarden en betaalgedrag
    assert one("SELECT COUNT(*) FROM klanten WHERE btw_nummer IS NULL") >= 5
    assert one("SELECT COUNT(*) FROM klanten WHERE email IS NULL") >= 3
    assert one("SELECT COUNT(*) FROM facturen WHERE betaald_op IS NULL") >= 15
    assert one("SELECT COUNT(*) FROM facturen "
               "WHERE betaald_op > vervaldatum") >= 10
    # Achterstallig: onbetaald en de vervaldatum is voorbij.
    assert one("SELECT COUNT(*) FROM facturen WHERE betaald_op IS NULL "
               f"AND vervaldatum < '{END_DATE.isoformat()}'") >= 5
    assert one("SELECT COUNT(*) FROM facturen "
               "WHERE factuurdatum LIKE '2025-06-%'") >= 5
    assert one("SELECT COUNT(*) FROM klanten "
               "WHERE bedrijfsnaam LIKE '%vzw%'") >= 5

    # Reeks 4: LEFT JOIN-oefeningen
    assert one("SELECT COUNT(*) FROM klanten k LEFT JOIN facturen f "
               "ON k.klant_id=f.klant_id WHERE f.factuur_id IS NULL") == 4
    assert one("SELECT COUNT(*) FROM producten p LEFT JOIN factuurlijnen fl "
               "ON p.product_id=fl.product_id WHERE fl.lijn_id IS NULL") == 2

    # Reeks 5/6: GROUP BY en HAVING
    assert one("SELECT COUNT(*) FROM (SELECT gemeente FROM klanten "
               "GROUP BY gemeente HAVING COUNT(*)>2)") >= 3
    assert one("SELECT COUNT(*) FROM (SELECT gemeente FROM klanten "
               "GROUP BY gemeente HAVING COUNT(*)=1)") >= 1
    n15 = one("SELECT COUNT(*) FROM (SELECT klant_id FROM facturen "
              "GROUP BY klant_id HAVING COUNT(*)>=15)")
    assert 3 <= n15 <= 12, n15  # oefening: klanten met minstens 15 facturen
    assert one("SELECT COUNT(*) FROM (SELECT klant_id FROM facturen "
               "GROUP BY klant_id HAVING COUNT(*)=1)") >= 2
    n1500 = one("SELECT COUNT(*) FROM (SELECT factuur_id FROM factuurlijnen "
                "GROUP BY factuur_id HAVING SUM(aantal*eenheidsprijs)>1500)")
    assert 5 <= n1500 <= 60, n1500  # oefening: facturen boven 1500 euro

    # Elke btw-code wordt gebruikt; elke categorie heeft minstens 2 producten.
    assert {r[0] for r in q("SELECT DISTINCT btw_code FROM producten")} == \
        {"STD", "VERL", "VRIJ"}
    assert all(r[1] >= 2 for r in q("SELECT categorie, COUNT(*) FROM producten "
                                    "GROUP BY categorie"))

    # Consistentie: geen factuur vóór klant_sinds, betaling nooit vóór factuur,
    # vervaldatum altijd factuurdatum + betaaltermijn.
    assert one("SELECT COUNT(*) FROM facturen f JOIN klanten k "
               "ON f.klant_id=k.klant_id WHERE f.factuurdatum < k.klant_sinds") == 0
    assert one("SELECT COUNT(*) FROM facturen "
               "WHERE betaald_op IS NOT NULL AND betaald_op < factuurdatum") == 0
    assert one("SELECT COUNT(*) FROM facturen WHERE "
               f"date(vervaldatum) <> date(factuurdatum, '+{BETAALTERMIJN} days')") == 0
    # Elke factuur heeft minstens één lijn; (factuur_id, product_id) is uniek.
    assert one("SELECT COUNT(*) FROM facturen f LEFT JOIN factuurlijnen fl "
               "ON f.factuur_id=fl.factuur_id WHERE fl.lijn_id IS NULL") == 0
    assert not q("SELECT factuur_id, product_id FROM factuurlijnen "
                 "GROUP BY factuur_id, product_id HAVING COUNT(*)>1")

    print(f"OK: {n_klant} klanten, {len(PRODUCTEN)} producten, "
          f"{n_fact} facturen, {n_lijn} factuurlijnen")
    print(f"    periode: {one('SELECT MIN(factuurdatum) FROM facturen')} .. "
          f"{one('SELECT MAX(factuurdatum) FROM facturen')}")
    print(f"    openstaand: {one('SELECT COUNT(*) FROM facturen WHERE betaald_op IS NULL')}, "
          f"te laat betaald: {one('SELECT COUNT(*) FROM facturen WHERE betaald_op > vervaldatum')}")
    print(f"    klanten met >= 15 facturen: {n15}, facturen > 1500 euro: {n1500}")
    print(f"    bestand: {DB_PATH} ({DB_PATH.stat().st_size / 1024:.0f} KiB)")
    con.close()


def main():
    rng = random.Random(SEED)
    facturen = make_facturen(rng)
    met_betaling = []
    for fid, kid, d in facturen:
        vervaldatum = d + timedelta(days=BETAALTERMIJN)
        met_betaling.append((fid, kid, d, vervaldatum, pick_betaald_op(rng, d)))
    lijnen = make_factuurlijnen(rng, met_betaling)
    build_db(met_betaling, lijnen)
    verify()


if __name__ == "__main__":
    main()
