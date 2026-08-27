#!/usr/bin/env python3
"""Genereert book/_static/db/wilrijk.db (issue #19).

Gebruik:
    python scripts/generate_wilrijk_db.py

Het script is deterministisch (vaste seed): elke run produceert exact dezelfde
data. Het vertrekt van de bestaande book/_static/db/adventureworks.db en
kopieert daaruit de tabellen Product en ProductCategory (zonder de
ThumbNailPhoto-blobs, om het bestand klein te houden voor trage laptops).
Daarrond bouwt het de tweede detective-les: het fictieve Europese
distributiecentrum van Adventure Works in Wilrijk.

De les (book/chapters/SQL/05c_Detective.ipynb) is het vervolg op de
Steenberg-mystery (03c): waar die met SELECT/WHERE/LIKE/JOIN werd opgelost,
vereist deze GROUP BY en HAVING. De fraude is onzichtbaar in losse rijen en
wordt pas zichtbaar wie telt en optelt.

Het scenario (spoiler!): magazijnier Stef Vermeulen (avondploeg) boekte in het
derde kwartaal van 2025 twaalf peperdure fietsen af als 'transportschade',
telkens één per keer, netjes gespreid over het kwartaal. In werkelijkheid
verkocht hij ze als nieuw op Tweedewiel.be onder de schuilnaam
'wielrenner2610'. Het spoor:

  1. memo van 2025-10-06            -> de afboekingen liepen volledig uit de hand
  2. afboekingen + Product +
     ProductCategory (GROUP BY)     -> de waarde zit bijna volledig bij de fietsen
  3. GROUP BY medewerker + HAVING
     COUNT(*)                       -> Karim Benali boekt het vaakst af (dwaalspoor:
                                       retour en schade is letterlijk zijn job)
  4. verhoor Karim                  -> de gouden tip: tel de wáárde, niet het aantal
  5. GROUP BY medewerker + HAVING
     SUM(aantal * StandardCost)     -> enkel Stef Vermeulen boekt > 5000 euro af
  6. detail + verhoren              -> patroon: 12 topfietsen, altijd 'transportschade';
                                       Stef beweert dat alles de schrootcontainer inging
  7. zoekertjes (GROUP BY + HAVING,
     JOIN op gsm)                   -> 'wielrenner2610' verkoopt splinternieuwe
                                       fietsen; het gsm-nummer is dat van Stef
  8. controle                       -> zelfcontrole van het eindantwoord

Onderaan het script staan controles (asserts) die dit hele spoor bewaken:
elke stap moet exact het bedoelde (en enkel het bedoelde) resultaat opleveren.
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SEED = 20260827
BASE_DB = Path(__file__).resolve().parent.parent / "book" / "_static" / "db" / "adventureworks.db"
DB_PATH = Path(__file__).resolve().parent.parent / "book" / "_static" / "db" / "wilrijk.db"

# Periode van het verhaal: het derde kwartaal van 2025.
KWARTAAL_START = date(2025, 7, 1)
KWARTAAL_END = date(2025, 9, 30)
MEMO_DATUM = "2025-10-06"          # de maandag waarop de memo verstuurd wordt

# ---------------------------------------------------------------------------
# Magazijnmedewerkers van het distributiecentrum in Wilrijk.
# ---------------------------------------------------------------------------

MEDEWERKERS = [
    # (medewerker_id, voornaam, achternaam, functie, ploeg, gsm)
    (1, "Rita", "Goossens", "magazijnverantwoordelijke", "dagploeg", "0475 62 18 40"),
    (2, "Karim", "Benali", "medewerker retour en schade", "dagploeg", "0486 33 90 27"),
    (3, "Stef", "Vermeulen", "magazijnier", "avondploeg", "0472 58 14 96"),
    (4, "Els", "Jacobs", "magazijnier", "dagploeg", "0498 41 77 03"),
    (5, "Youssef", "El Amrani", "magazijnier", "dagploeg", "0468 25 60 84"),
    (6, "An", "De Ridder", "teamleider expeditie", "dagploeg", "0477 90 35 12"),
    (7, "Peter", "Claeys", "magazijnier", "avondploeg", "0493 17 42 65"),
    (8, "Sandra", "Willems", "administratief bediende", "dagploeg", "0471 84 09 53"),
    (9, "Bram", "Dierckx", "heftruckchauffeur", "dagploeg", "0489 56 21 78"),
    (10, "Ilse", "Van Hoof", "teamleider avondploeg", "avondploeg", "0474 03 66 29"),
]

DADER_ID = 3        # Stef Vermeulen: weinig afboekingen, maar enorme waarde
KARIM_ID = 2        # Karim Benali: het dwaalspoor (meeste afboekingen, kleine waarde)
RITA_ID = 1
ILSE_ID = 10

GSM_VAN = {m[0]: m[5] for m in MEDEWERKERS}

# De twaalf gestolen fietsen: de duurste modellen uit de AdventureWorks-catalogus
# (Road-150 Red en Mountain-100; StandardCost 1898-2171 euro per stuk).
# De asserts onderaan bewaken dat deze ProductID's echt bestaan en topfietsen zijn.
FRAUDE_PRODUCTEN = [749, 750, 751, 752, 753,       # Road-150 Red 62/44/48/52/56
                    771, 772, 773, 774,            # Mountain-100 Silver 38/42/44/48
                    775, 776, 777]                 # Mountain-100 Black 38/42/44

FRAUDE_REDEN = "transportschade"
REDENEN = ["transportschade", "beschadigd in magazijn",
           "defect uit doos", "retour - niet verkoopbaar"]

DADER_ALIAS = "wielrenner2610"      # 2610 is de postcode van Wilrijk

# Hoe vaak elke (onschuldige) collega afboekt; Karim doet dat beroepshalve veel.
GEWONE_AANTALLEN = {1: 3, 4: 6, 5: 5, 6: 4, 7: 7, 8: 2, 9: 5, 10: 4}
KARIM_AANTAL = 34

# Aliassen voor het ruisverkeer op Tweedewiel.be (elk hoogstens 3 zoekertjes).
RUIS_VERKOPERS = [
    "koersfan_lier", "mtb_maarten", "fietsmadam", "peddelpower",
    "gravelgert", "bertje_koers", "sportzolder", "vintage_velo",
    "kettingkast", "berg_op", "tourist_tom", "spurter88",
    "renner_rudy", "tweedehands_toon",
]

RUIS_TEKSTEN = [
    "in goede staat, onderhoud gedaan",
    "weinig gebruikt, kleine krassen",
    "sportief model, rijdt perfect",
    "goed onderhouden, banden vorig jaar vervangen",
    "degelijke fiets, prijs bespreekbaar",
    "gebruikt maar verzorgd, af te halen",
]

DADER_TEKSTEN = [
    "splinternieuw, nooit gereden, doos nog dicht",
    "NIEUW in doos, nooit gebruikt",
    "gloednieuw, nog in originele verpakking",
    "nieuw, rechtstreeks uit de doos, factuur niet nodig",
]


def werkdagen(maand=None):
    dagen = []
    d = KWARTAAL_START
    while d <= KWARTAAL_END:
        if d.weekday() < 5 and (maand is None or d.month == maand):
            dagen.append(d)
        d += timedelta(days=1)
    return dagen


def lees_catalogus():
    """Haalt de productgegevens uit de originele adventureworks.db."""
    con = sqlite3.connect(BASE_DB)
    rows = con.execute(
        "SELECT p.ProductID, p.Name, p.StandardCost, p.ListPrice, c.Name, "
        "       c.ParentProductCategoryID "
        "FROM Product p "
        "JOIN ProductCategory c ON p.ProductCategoryID = c.ProductCategoryID"
    ).fetchall()
    con.close()
    catalogus = {r[0]: {"naam": r[1], "kost": r[2], "lijstprijs": r[3],
                        "categorie": r[4], "parent": r[5]} for r in rows}
    return catalogus


def make_afboekingen(rng: random.Random, catalogus):
    """Het logboek van kwartaal 3: gewone schade + de twaalf fraudelijnen."""
    klein = sorted(pid for pid, p in catalogus.items() if p["kost"] < 12)
    middel = sorted(pid for pid, p in catalogus.items()
                    if 3 <= p["kost"] < 60 and p["parent"] != 1)  # geen fietsen

    rows = []  # (datum, product_id, aantal, reden, medewerker_id)

    # Karim (retour en schade): veel afboekingen, allemaal klein spul.
    for _ in range(KARIM_AANTAL):
        d = rng.choice(werkdagen())
        pid = rng.choice(klein)
        aantal = rng.choices([1, 2, 3, 4], weights=[55, 30, 10, 5])[0]
        rows.append((d.isoformat(), pid, aantal, rng.choice(REDENEN), KARIM_ID))

    # De andere collega's: af en toe een afboeking, nooit iets duurs.
    for mid, n in GEWONE_AANTALLEN.items():
        for _ in range(n):
            d = rng.choice(werkdagen())
            pid = rng.choice(middel)
            aantal = rng.choices([1, 2], weights=[75, 25])[0]
            rows.append((d.isoformat(), pid, aantal, rng.choice(REDENEN), mid))

    # De fraude: twaalf topfietsen, altijd één per keer, altijd 'transportschade',
    # netjes gespreid over de drie maanden (vier per maand).
    fraude_dagen = sorted(rng.sample(werkdagen(7), 4)
                          + rng.sample(werkdagen(8), 4)
                          + rng.sample(werkdagen(9), 4))
    gestolen = FRAUDE_PRODUCTEN[:]
    rng.shuffle(gestolen)
    fraude_rows = []
    for d, pid in zip(fraude_dagen, gestolen):
        fraude_rows.append((d.isoformat(), pid, 1, FRAUDE_REDEN, DADER_ID))
    rows.extend(fraude_rows)

    rows.sort(key=lambda r: (r[0], r[4], r[1]))
    return ([(i + 1, datum, pid, aantal, reden, mid)
             for i, (datum, pid, aantal, reden, mid) in enumerate(rows)],
            fraude_rows)


def make_zoekertjes(rng: random.Random, catalogus, fraude_rows):
    """Zoekertjes op Tweedewiel.be: ruis van echte tweedehandsverkopers
    plus de negen verdachte zoekertjes van de dader."""
    fietsen = sorted(pid for pid, p in catalogus.items() if p["parent"] == 1)

    rows = []  # (verkoper, omschrijving, prijs, datum, gsm)

    # Ruis: gewone verkopers met gewone tweedehandsfietsen.
    ruis_start = date(2025, 8, 1)
    ruis_span = (date(2025, 10, 20) - ruis_start).days
    gebruikte_gsms = set(GSM_VAN.values())
    for verkoper in RUIS_VERKOPERS:
        gsm = None
        while gsm is None or gsm in gebruikte_gsms:
            gsm = ("04" + str(rng.randint(60, 99)) + " "
                   + f"{rng.randint(0, 99):02d} {rng.randint(0, 99):02d} "
                   + f"{rng.randint(0, 99):02d}")
        gebruikte_gsms.add(gsm)
        for _ in range(rng.randint(1, 3)):
            pid = rng.choice(fietsen)
            p = catalogus[pid]
            prijs = int(round(p["lijstprijs"] * rng.uniform(0.25, 0.45), -1))
            d = ruis_start + timedelta(days=rng.randint(0, ruis_span))
            rows.append((verkoper, f"{p['naam']} - {rng.choice(RUIS_TEKSTEN)}",
                         prijs, d.isoformat(), gsm))

    # De dader: negen van de twaalf gestolen fietsen, verkocht als nieuw,
    # telkens enkele dagen tot weken na de afboeking.
    for datum, pid, _aantal, _reden, _mid in rng.sample(fraude_rows, 9):
        p = catalogus[pid]
        prijs = int(round(p["lijstprijs"] * 0.55, -1))
        d = date.fromisoformat(datum) + timedelta(days=rng.randint(5, 25))
        d = min(d, date(2025, 10, 20))
        rows.append((DADER_ALIAS, f"{p['naam']} - {rng.choice(DADER_TEKSTEN)}",
                     prijs, d.isoformat(), GSM_VAN[DADER_ID]))

    rows.sort(key=lambda r: (r[3], r[0], r[1]))
    return [(i + 1, verkoper, omschrijving, prijs, datum, gsm)
            for i, (verkoper, omschrijving, prijs, datum, gsm) in enumerate(rows)]


def make_memos(totaal_str):
    return [
        (1, "2025-07-14", "Rita Goossens", "Verlofplanning zomer",
         "Geef je verlofaanvragen voor augustus ten laatste vrijdag door. De "
         "avondploeg draait in de bouwvakantie met een beperkte bezetting."),
        (2, "2025-08-18", "An De Ridder", "Nieuwe steekwagens expeditie",
         "De zes nieuwe steekwagens staan aan dock 3. De oude gaan volgende "
         "week naar de schroothandel."),
        (3, "2025-09-08", "Rita Goossens", "Brandoefening 12 september",
         "Vrijdag om 10u is er een brandoefening. Verzamelen op de parking, "
         "badge meenemen."),
        (4, MEMO_DATUM, "Finance, Adventure Works Europe",
         "Afboekingen derde kwartaal",
         f"Bij het afsluiten van het derde kwartaal zien we in Wilrijk voor "
         f"{totaal_str} euro aan voorraad die werd afgeboekt wegens schade of "
         f"verlies. In een normaal kwartaal is dat twee- tot drieduizend euro. "
         f"Geen enkel ander distributiecentrum komt zelfs maar in de buurt van "
         f"zulke cijfers. Elke afboeking staat in de tabel afboekingen, met "
         f"datum, product, aantal, reden en de medewerker die ze registreerde. "
         f"Wij verwachten tegen eind deze maand een verklaring."),
        (5, "2025-10-13", "Sandra Willems", "Bestelling kantoormateriaal",
         "Wie iets nodig heeft van kantoormateriaal: zet het voor woensdag op "
         "de lijst bij het onthaal."),
    ]


def make_verhoren():
    return [
        (1, RITA_ID, "2025-10-08",
         "Afboeken gebeurt altijd onder je eigen login, en iedereen van het "
         "magazijn kan het. Grote transportschade horen we aan te geven bij "
         "de vervoerder, voor de verzekering. Vreemd genoeg zegt die dat er "
         "dit kwartaal amper claims van ons binnenkwamen."),
        (2, KARIM_ID, "2025-10-08",
         "Natuurlijk sta ik bovenaan als je telt hoe vaak er afgeboekt wordt: "
         "elke kapotte binnenband en elk gescheurd truitje passeert bij mij, "
         "dat is letterlijk mijn job. Maar tel eens op wat al die afboekingen "
         "waard zijn in plaats van hoe vaak ze gebeuren. Een lekke band is "
         "geen mountainbike. Dan zie je meteen dat het probleem niet bij de "
         "retourafdeling ligt."),
        (3, DADER_ID, "2025-10-09",
         "Die fietsen? Allemaal echte transportschade, total loss uit de "
         "vrachtwagen gekomen. Kapot is kapot: alles is met de "
         "schrootcontainer meegegaan. Papieren van de vervoerder heb ik daar "
         "niet van, dat regelt het kantoor toch?"),
        (4, ILSE_ID, "2025-10-09",
         "Stef blijft 's avonds vaak als laatste achter, dat is niks nieuws. "
         "Hij laadt weleens dozen in zijn bestelwagen. Retours wegbrengen, "
         "zegt hij dan. Ik heb daar eerlijk gezegd nooit iets achter "
         "gezocht."),
    ]


def make_controle():
    rows = []
    for mid, voornaam, achternaam, _f, _p, _g in MEDEWERKERS:
        naam = f"{voornaam} {achternaam}"
        if mid == DADER_ID:
            uitkomst = ("Juist! Stef Vermeulen boekte twaalf topfietsen af als "
                        "transportschade, telkens eentje tegelijk zodat het "
                        "niemand opviel. In werkelijkheid verkocht hij ze "
                        "gloednieuw op Tweedewiel.be, en zijn gsm-nummer in de "
                        "zoekertjes verraadt hem. Alleen wie optelde, zag het. "
                        "Zaak gesloten - klasse speurwerk, detective!")
        else:
            uitkomst = (f"Nee. Voor {naam} is er geen sluitend bewijs. Kijk "
                        f"nog eens goed naar wat de cijfers per medewerker "
                        f"vertellen - en let op het verschil tussen tellen en "
                        f"optellen.")
        rows.append((naam, uitkomst))
    rows.sort(key=lambda r: r[0])
    return rows


def build_db(afboekingen, zoekertjes, verhoren, controle):
    """Bouwt wilrijk.db: kopie van Product en ProductCategory (zonder blobs)
    plus de tabellen van het distributiecentrum. De memo wordt pas ingevoegd
    nadat SQLite zelf de totale afgeboekte waarde heeft berekend, zodat het
    bedrag in de memo exact klopt met wat leerlingen met SUM() vinden."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    base = sqlite3.connect(BASE_DB)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Kopieer Product en ProductCategory met hun originele schema.
    for tabel in ("ProductCategory", "Product"):
        ddl = base.execute("SELECT sql FROM sqlite_master "
                           "WHERE type = 'table' AND name = ?", (tabel,)).fetchone()[0]
        cur.execute(ddl)
        kolommen = [r[1] for r in base.execute(f"PRAGMA table_info([{tabel}])")]
        rows = base.execute(f"SELECT * FROM [{tabel}]").fetchall()
        if tabel == "Product":
            blob_i = kolommen.index("ThumbNailPhoto")
            rows = [tuple(None if i == blob_i else v for i, v in enumerate(r))
                    for r in rows]
        marks = ",".join("?" * len(kolommen))
        cur.executemany(f"INSERT INTO [{tabel}] VALUES ({marks})", rows)
    base.close()

    cur.executescript("""
    CREATE TABLE magazijnmedewerkers (
      medewerker_id INTEGER PRIMARY KEY,
      voornaam      TEXT NOT NULL,
      achternaam    TEXT NOT NULL,
      functie       TEXT NOT NULL,
      ploeg         TEXT NOT NULL,   -- 'dagploeg' of 'avondploeg'
      gsm           TEXT NOT NULL
    );
    CREATE TABLE afboekingen (
      afboeking_id  INTEGER PRIMARY KEY,
      datum         TEXT NOT NULL,   -- ISO: YYYY-MM-DD
      product_id    INTEGER NOT NULL,
      aantal        INTEGER NOT NULL,
      reden         TEXT NOT NULL,
      medewerker_id INTEGER NOT NULL,
      FOREIGN KEY (product_id) REFERENCES Product(ProductID),
      FOREIGN KEY (medewerker_id) REFERENCES magazijnmedewerkers(medewerker_id)
    );
    CREATE TABLE memos (
      memo_id  INTEGER PRIMARY KEY,
      datum    TEXT NOT NULL,
      afzender TEXT NOT NULL,
      onderwerp TEXT NOT NULL,
      tekst    TEXT NOT NULL
    );
    CREATE TABLE verhoren (
      verhoor_id    INTEGER PRIMARY KEY,
      medewerker_id INTEGER NOT NULL,
      datum         TEXT NOT NULL,
      tekst         TEXT NOT NULL,
      FOREIGN KEY (medewerker_id) REFERENCES magazijnmedewerkers(medewerker_id)
    );
    CREATE TABLE zoekertjes (
      zoekertje_id INTEGER PRIMARY KEY,
      verkoper     TEXT NOT NULL,    -- schuilnaam op Tweedewiel.be
      omschrijving TEXT NOT NULL,
      prijs        INTEGER NOT NULL,
      datum        TEXT NOT NULL,
      gsm          TEXT NOT NULL
    );
    CREATE TABLE controle (
      verdachte TEXT PRIMARY KEY,
      uitkomst  TEXT NOT NULL
    );
    """)

    cur.executemany("INSERT INTO magazijnmedewerkers VALUES (?,?,?,?,?,?)",
                    MEDEWERKERS)
    cur.executemany("INSERT INTO afboekingen VALUES (?,?,?,?,?,?)", afboekingen)
    cur.executemany("INSERT INTO verhoren VALUES (?,?,?,?)", verhoren)
    cur.executemany("INSERT INTO zoekertjes VALUES (?,?,?,?,?,?)", zoekertjes)
    cur.executemany("INSERT INTO controle VALUES (?,?)", controle)

    # De totale afgeboekte waarde, berekend zoals de leerlingen dat doen.
    totaal = cur.execute(
        "SELECT ROUND(SUM(a.aantal * p.StandardCost), 2) "
        "FROM afboekingen a JOIN Product p ON a.product_id = p.ProductID"
    ).fetchone()[0]
    totaal_str = f"{totaal:,.2f}".replace(",", " ").replace(".", ",")
    cur.executemany("INSERT INTO memos VALUES (?,?,?,?,?)", make_memos(totaal_str))

    con.commit()
    cur.execute("VACUUM")
    con.close()
    return totaal, totaal_str


def verify(totaal, totaal_str):
    """Bewaakt het volledige spoor van de detective-les. Faalt hard bij een gat."""
    con = sqlite3.connect(DB_PATH)
    q = lambda sql, *p: con.execute(sql, p).fetchall()
    one = lambda sql, *p: con.execute(sql, p).fetchone()[0]

    # De catalogus is correct meegekomen: alle producten, geen blobs meer.
    assert one("SELECT COUNT(*) FROM Product") == 295
    assert one("SELECT COUNT(*) FROM ProductCategory") == 41
    assert one("SELECT COUNT(*) FROM Product WHERE ThumbNailPhoto IS NOT NULL") == 0

    # De twaalf fraudeproducten zijn echte topfietsen uit AdventureWorks.
    for pid in FRAUDE_PRODUCTEN:
        kost, parent = q("SELECT p.StandardCost, c.ParentProductCategoryID "
                         "FROM Product p JOIN ProductCategory c "
                         "ON p.ProductCategoryID = c.ProductCategoryID "
                         "WHERE p.ProductID = ?", pid)[0]
        assert kost >= 1500 and parent == 1, pid

    # Stap 1: exact één memo op 6 oktober, en het genoemde bedrag klopt exact
    # met wat leerlingen in stap 2 met SUM() berekenen.
    memo = q("SELECT tekst FROM memos WHERE datum = ?", MEMO_DATUM)
    assert len(memo) == 1
    assert totaal_str in memo[0][0], (totaal_str, memo[0][0])
    assert totaal > 20000

    # Alle afboekingen vallen binnen kwartaal 3, op weekdagen.
    assert one("SELECT COUNT(*) FROM afboekingen WHERE datum < '2025-07-01' "
               "OR datum > '2025-09-30'") == 0
    for (datum,) in q("SELECT DISTINCT datum FROM afboekingen"):
        assert date.fromisoformat(datum).weekday() < 5, datum

    # Stap 2: de waarde per categorie: Road Bikes en Mountain Bikes torenen
    # boven alles uit, elke andere categorie blijft klein.
    per_cat = dict(q(
        "SELECT c.Name, ROUND(SUM(a.aantal * p.StandardCost), 2) "
        "FROM afboekingen a JOIN Product p ON a.product_id = p.ProductID "
        "JOIN ProductCategory c ON p.ProductCategoryID = c.ProductCategoryID "
        "GROUP BY c.Name"))
    assert per_cat["Road Bikes"] > 10000 and per_cat["Mountain Bikes"] > 10000
    for cat, waarde in per_cat.items():
        if cat not in ("Road Bikes", "Mountain Bikes"):
            assert waarde < 1000, (cat, waarde)
    assert abs(sum(per_cat.values()) - totaal) < 0.05

    # Stap 3: HAVING COUNT(*) >= 20 levert exact één iemand op: Karim Benali.
    telling = q("SELECT medewerker_id, COUNT(*) AS n FROM afboekingen "
                "GROUP BY medewerker_id ORDER BY n DESC")
    assert telling[0][0] == KARIM_ID and telling[0][1] >= 30
    assert all(n < 20 for mid, n in telling if mid != KARIM_ID)
    veel = q("SELECT medewerker_id FROM afboekingen GROUP BY medewerker_id "
             "HAVING COUNT(*) >= 20")
    assert veel == [(KARIM_ID,)]

    # Stap 4: Karims verhoor bevat de gouden tip (waarde i.p.v. aantal).
    assert "waard" in one("SELECT tekst FROM verhoren WHERE medewerker_id = ?",
                          KARIM_ID)

    # Stap 5: HAVING SUM(aantal * StandardCost) > 5000 levert exact één
    # iemand op: Stef Vermeulen. Iedereen anders blijft ver onder de drempel.
    waardes = dict(q(
        "SELECT a.medewerker_id, SUM(a.aantal * p.StandardCost) "
        "FROM afboekingen a JOIN Product p ON a.product_id = p.ProductID "
        "GROUP BY a.medewerker_id"))
    assert waardes[DADER_ID] > 20000
    assert all(w < 2500 for mid, w in waardes.items() if mid != DADER_ID)
    hoog = q("SELECT a.medewerker_id FROM afboekingen a "
             "JOIN Product p ON a.product_id = p.ProductID "
             "GROUP BY a.medewerker_id "
             "HAVING SUM(a.aantal * p.StandardCost) > 5000")
    assert hoog == [(DADER_ID,)]

    # Stap 6: het patroon van de dader: exact twaalf afboekingen, altijd één
    # stuk, altijd 'transportschade', gespreid over juli, augustus en september.
    stef = q("SELECT datum, product_id, aantal, reden FROM afboekingen "
             "WHERE medewerker_id = ?", DADER_ID)
    assert len(stef) == 12
    assert sorted(r[1] for r in stef) == sorted(FRAUDE_PRODUCTEN)
    assert all(r[2] == 1 and r[3] == FRAUDE_REDEN for r in stef)
    assert {date.fromisoformat(r[0]).month for r in stef} == {7, 8, 9}
    # Zijn verhoor beweert dat alles vernietigd werd; Ilse zag hem laden.
    assert "schrootcontainer" in one(
        "SELECT tekst FROM verhoren WHERE medewerker_id = ?", DADER_ID)
    assert "bestelwagen" in one(
        "SELECT tekst FROM verhoren WHERE medewerker_id = ?", ILSE_ID)

    # Stap 7: HAVING COUNT(*) >= 5 levert exact één verkoper op: de alias.
    druk = q("SELECT verkoper FROM zoekertjes GROUP BY verkoper "
             "HAVING COUNT(*) >= 5")
    assert druk == [(DADER_ALIAS,)]
    assert one("SELECT MAX(n) FROM (SELECT COUNT(*) AS n FROM zoekertjes "
               "WHERE verkoper <> ? GROUP BY verkoper)", DADER_ALIAS) <= 3

    # De zoekertjes van de alias: gestolen modellen, verkocht als nieuw,
    # allemaal met het gsm-nummer van Stef.
    alias = q("SELECT omschrijving, gsm FROM zoekertjes WHERE verkoper = ?",
              DADER_ALIAS)
    assert len(alias) == 9
    namen = {r[0] for r in q(
        "SELECT Name FROM Product WHERE ProductID IN (%s)"
        % ",".join("?" * len(FRAUDE_PRODUCTEN)), *FRAUDE_PRODUCTEN)}
    for omschrijving, gsm in alias:
        assert gsm == GSM_VAN[DADER_ID]
        assert any(omschrijving.startswith(naam) for naam in namen), omschrijving
        assert "nieuw" in omschrijving.lower()

    # Enkel de alias-zoekertjes wijzen naar een medewerker: de JOIN op gsm
    # levert uitsluitend Stef Vermeulen op.
    match = q("SELECT DISTINCT z.verkoper, m.voornaam, m.achternaam "
              "FROM zoekertjes z JOIN magazijnmedewerkers m ON z.gsm = m.gsm")
    assert match == [(DADER_ALIAS, "Stef", "Vermeulen")]
    # En geen enkel ruiszoekertje vermeldt iets als nieuw.
    assert one("SELECT COUNT(*) FROM zoekertjes WHERE verkoper <> ? "
               "AND LOWER(omschrijving) LIKE '%nieuw%'", DADER_ALIAS) == 0

    # Stap 8: de controletabel dekt iedereen en enkel Stef Vermeulen is 'Juist'.
    assert one("SELECT COUNT(*) FROM controle") == len(MEDEWERKERS)
    juist = q("SELECT verdachte FROM controle WHERE uitkomst LIKE 'Juist!%'")
    assert juist == [("Stef Vermeulen",)]

    # Algemene consistentie.
    assert one("SELECT COUNT(*) FROM afboekingen a LEFT JOIN Product p "
               "ON a.product_id = p.ProductID WHERE p.ProductID IS NULL") == 0
    assert one("SELECT COUNT(*) FROM afboekingen a LEFT JOIN magazijnmedewerkers m "
               "ON a.medewerker_id = m.medewerker_id "
               "WHERE m.medewerker_id IS NULL") == 0
    assert one("SELECT COUNT(DISTINCT medewerker_id) FROM afboekingen") \
        == len(MEDEWERKERS)
    assert one("SELECT COUNT(*) FROM magazijnmedewerkers") \
        == one("SELECT COUNT(DISTINCT gsm) FROM magazijnmedewerkers")

    n_afb = one("SELECT COUNT(*) FROM afboekingen")
    n_zoek = one("SELECT COUNT(*) FROM zoekertjes")
    print(f"OK: {len(MEDEWERKERS)} medewerkers, {n_afb} afboekingen, "
          f"{n_zoek} zoekertjes")
    print(f"    totale afgeboekte waarde: {totaal_str} euro "
          f"(waarvan dader: {waardes[DADER_ID]:.2f})")
    print(f"    dwaalspoor: Karim Benali ({telling[0][1]} afboekingen)")
    print(f"    dader: Stef Vermeulen, alias '{DADER_ALIAS}'")
    print(f"    bestand: {DB_PATH} ({DB_PATH.stat().st_size / 1024:.0f} KiB)")
    con.close()


def main():
    rng = random.Random(SEED)
    catalogus = lees_catalogus()
    afboekingen, fraude_rows = make_afboekingen(rng, catalogus)
    zoekertjes = make_zoekertjes(rng, catalogus, fraude_rows)
    verhoren = make_verhoren()
    controle = make_controle()
    totaal, totaal_str = build_db(afboekingen, zoekertjes, verhoren, controle)
    verify(totaal, totaal_str)


if __name__ == "__main__":
    main()
