#!/usr/bin/env python3
"""Genereert book/_static/db/steenberg.db (issue #5).

Gebruik:
    python scripts/generate_steenberg_db.py

Het script is deterministisch (vaste seed): elke run produceert exact dezelfde
data. Pas de constantes hieronder aan en run opnieuw om de dataset te wijzigen.

De context: Bouwgroothandel Steenberg nv, een fictieve groothandel in
bouwmaterialen uit Aalst. Deze database hoort bij de detective-les
(book/chapters/SQL/03c_Detective.ipynb): een fraudeonderzoek dat leerlingen
met SELECT, WHERE, LIKE en JOIN stap voor stap oplossen.

Het scenario (spoiler!): vertegenwoordiger Ruben Claes gebruikte op
vrijdagavond 16 mei 2025 het account van boekhouder Sofie Persoons om op een
factuur voor het bedrijf van zijn broer (Dender Bouwmaterialen bv, contact
Davy Claes) drie eenheidsprijzen met 80% te verlagen. Het spoor:

  1. auditverslag van 2025-06-02  -> verdachte factuur
  2. facturen + klanten           -> de klant die profiteerde
  3. prijswijzigingen             -> tijdstip (na sluitingstijd) + account
  4. accounts + medewerkers       -> het account van Sofie Persoons
  5. verhoren + badge_logs        -> Sofie heeft een sluitend alibi
  6. badge_logs (die avond)       -> enkel Ruben Claes badgede nog binnen
  7. emails                       -> contact met de klant, zelfde achternaam
  8. controle                     -> zelfcontrole van het eindantwoord

Onderaan het script staan controles (asserts) die dit hele spoor bewaken:
elke stap moet exact het bedoelde (en enkel het bedoelde) resultaat opleveren.
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SEED = 20260827
DB_PATH = Path(__file__).resolve().parent.parent / "book" / "_static" / "db" / "steenberg.db"

# Periode van het verhaal.
FACTUUR_START = date(2025, 3, 3)
FACTUUR_END = date(2025, 6, 2)
BADGE_START = date(2025, 5, 5)
BADGE_END = date(2025, 6, 6)

FRAUDE_DATUM = "2025-05-16"        # een vrijdag
AUDIT_DATUM = "2025-06-02"         # de maandag van de ontdekking

# ---------------------------------------------------------------------------
# Medewerkers van Steenberg nv.
# ---------------------------------------------------------------------------

MEDEWERKERS = [
    # (medewerker_id, voornaam, achternaam, functie, afdeling)
    (1, "Marc", "Van Steen", "algemeen directeur", "directie"),
    (2, "Karin", "Baetens", "financieel directeur", "directie"),
    (3, "Sofie", "Persoons", "boekhouder", "boekhouding"),
    (4, "Tom", "Reynders", "boekhouder", "boekhouding"),
    (5, "Ruben", "Claes", "vertegenwoordiger", "verkoop"),
    (6, "Elke", "Martens", "vertegenwoordiger", "verkoop"),
    (7, "Jonas", "De Vlieger", "vertegenwoordiger", "verkoop"),
    (8, "Sara", "Ozdemir", "medewerker binnendienst", "verkoop"),
    (9, "Pieter", "Vandenberghe", "medewerker binnendienst", "verkoop"),
    (10, "Lien", "Verhaeghe", "aankoper", "aankoop"),
    (11, "Dries", "Coene", "aankoper", "aankoop"),
    (12, "Bilal", "Azzouzi", "magazijnier", "magazijn"),
    (13, "Katrien", "Deprez", "magazijnier", "magazijn"),
    (14, "Steven", "Roels", "magazijnier", "magazijn"),
    (15, "Anja", "Vermeersch", "magazijnverantwoordelijke", "magazijn"),
    (16, "Wouter", "De Backer", "IT-beheerder", "IT"),
    (17, "Nadia", "Bensalah", "onderhoudsmedewerker", "onderhoud"),
    (18, "Geert", "Callens", "chauffeur", "logistiek"),
    (19, "Inge", "Segers", "chauffeur", "logistiek"),
    (20, "Hans", "Moerman", "receptionist", "onthaal"),
    (21, "Julie", "Lambrecht", "hr-verantwoordelijke", "personeel"),
    (22, "Frederik", "Van Damme", "marketingmedewerker", "marketing"),
    (23, "Amber", "Coppens", "administratief bediende", "boekhouding"),
    (24, "Niels", "Verstraeten", "vertegenwoordiger", "verkoop"),
    (25, "Carla", "Jacobs", "administratief bediende", "verkoop"),
    (26, "Omer", "Yilmaz", "magazijnier", "magazijn"),
    (27, "Els", "De Winter", "kwaliteitsverantwoordelijke", "aankoop"),
    (28, "Bart", "Willemsen", "preventieadviseur", "personeel"),
]

DADER_ID = 5        # Ruben Claes
SOFIE_ID = 3        # Sofie Persoons (haar account wordt misbruikt)
TOM_ID = 4
AMBER_ID = 23
WOUTER_ID = 16      # IT, werkt op vrijdagavond tot 21u31
NADIA_ID = 17       # avondploeg onderhoud, tot 20u15
HANS_ID = 20

# Enkel de boekhouding mag factuurprijzen aanpassen (zie verhoor Tom Reynders).
BOEKHOUDING_IDS = [SOFIE_ID, TOM_ID, AMBER_ID]

# ---------------------------------------------------------------------------
# Producten: bouwmaterialen.
# ---------------------------------------------------------------------------

PRODUCTEN = [
    # (product_id, naam, categorie, eenheidsprijs)
    (1, "Cement CEM II 25 kg", "Ruwbouw", 8.95),
    (2, "Gevelsteen rood (pallet 500)", "Ruwbouw", 289.00),
    (3, "Isolatieplaat PIR 10 cm", "Isolatie", 42.80),
    (4, "Gipsplaat 260x120", "Afwerking", 11.25),
    (5, "Dakpan antraciet", "Dak", 2.15),
    (6, "Welfsel 4 m", "Ruwbouw", 96.50),
    (7, "Betonklinker grijs (per m2)", "Buitenaanleg", 18.40),
    (8, "Zand bigbag 1 m3", "Ruwbouw", 62.00),
    (9, "Chapezand bigbag 1 m3", "Ruwbouw", 58.50),
    (10, "Snelbouwsteen (pallet)", "Ruwbouw", 214.00),
    (11, "OSB-plaat 18 mm", "Hout", 24.60),
    (12, "Multiplex 12 mm", "Hout", 39.95),
    (13, "Dakisolatie rol 20 cm", "Isolatie", 33.70),
    (14, "Regenwaterput 5000 l", "Buitenaanleg", 1189.00),
    (15, "Geotextiel rol 50 m", "Buitenaanleg", 74.25),
    (16, "Wapeningsnet 150x150", "Ruwbouw", 31.80),
]

# De drie producten waarvan de prijs op de vervalste factuur verlaagd werd.
FRAUDE_PRODUCTEN = [2, 6, 14]
FRAUDE_KORTING = 0.2   # nieuwe prijs = 20% van de oude (80% korting)

# ---------------------------------------------------------------------------
# Klanten: bouwbedrijven uit de streek rond Aalst.
# ---------------------------------------------------------------------------

KLANTEN = [
    # (klant_id, bedrijfsnaam, contactpersoon, email, gemeente)
    (1, "Bouwbedrijf Verhelst nv", "Els Verhelst", "els@bouwverhelst.be", "Aalst"),
    (2, "Algemene Bouw Michiels", "Jan Michiels", "jan@bouwmichiels.be", "Ninove"),
    (3, "Dakwerken Delarue bv", "Piet Delarue", "piet@dakwerkendelarue.be", "Dendermonde"),
    (4, "Grondwerken Van Impe", "Marleen Van Impe", "info@vanimpe-grondwerken.be", "Erpe-Mere"),
    (5, "Renovatiebedrijf Casteels", "Kurt Casteels", "kurt@renovatiecasteels.be", "Wetteren"),
    (6, "Tuinaanleg De Groene Zoom", "Ann Praet", "ann@degroenezoom.be", "Lede"),
    (7, "Dender Bouwmaterialen bv", "Davy Claes", "davy.claes@denderbouw.be", "Aalst"),
    (8, "Wegenbouw Temmerman nv", "Rudi Temmerman", "rudi@temmermanwegenbouw.be", "Zottegem"),
    (9, "Bouwonderneming Callebaut", "Sven Callebaut", "sven@callebautbouw.be", "Gent"),
    (10, "Klinkerwerken Pauwels", "Tine Pauwels", "tine@klinkerwerkenpauwels.be", "Oudenaarde"),
    (11, "Totaalrenovatie Hendrickx bv", "Joost Hendrickx", "joost@hendrickxrenovatie.be", "Aalst"),
    (12, "Daktimmerwerken Roggeman", "Bert Roggeman", "bert@roggemandak.be", "Ninove"),
    (13, "Bouwgroep Vlaemynck nv", "Carine Vlaemynck", "carine@vlaemynckbouw.be", "Gent"),
    (14, "Gevelwerken Segher & Zoon", "Luc Segher", "luc@seghergevels.be", "Dendermonde"),
    (15, "Chapewerken De Baets", "Nico De Baets", "nico@chapedebaets.be", "Wichelen"),
    (16, "Rioleringswerken Aqualine", "Sonja Meert", "sonja@aqualine.be", "Wetteren"),
    (17, "Bouwbedrijf Otte bv", "Frank Otte", "frank@bouwotte.be", "Haaltert"),
    (18, "Verbouwingen Dhondt", "Griet Dhondt", "griet@verbouwingendhondt.be", "Geraardsbergen"),
]

DENDER_ID = 7

# De verdachte factuur krijgt (chronologisch genummerd) dit nummer.
# Het auditverslag en de controletabel worden met dit nummer opgebouwd;
# de assert onderaan bewaakt dat het nummer niet verschuift.
FRAUDE_FACTUUR_ID = None  # wordt bij het genereren ingevuld
VERWACHT_FRAUDE_FACTUUR_ID = 4101


def make_facturen(rng: random.Random):
    """Facturen per klant, chronologisch genummerd vanaf 4001."""
    facturen = []  # (klant_id, datum, bedrag)
    span = (FACTUUR_END - FACTUUR_START).days
    for klant in KLANTEN:
        kid = klant[0]
        for _ in range(rng.randint(4, 12)):
            d = FACTUUR_START + timedelta(days=rng.randint(0, span))
            if kid == DENDER_ID and d.isoformat() == FRAUDE_DATUM:
                continue  # die dag bestaat enkel de vervalste factuur
            facturen.append((kid, d, round(rng.uniform(350, 9800), 2)))

    # De vervalste factuur: opgemaakt op vrijdag 16 mei 2025.
    facturen.append((DENDER_ID, date.fromisoformat(FRAUDE_DATUM), 2216.90))

    facturen.sort(key=lambda f: (f[1], f[0]))
    rows = []
    fraude_id = None
    for i, (kid, d, bedrag) in enumerate(facturen):
        fid = 4001 + i
        if kid == DENDER_ID and d.isoformat() == FRAUDE_DATUM:
            fraude_id = fid
        rows.append((fid, kid, d.isoformat(), bedrag))
    return rows, fraude_id


def make_accounts(rng: random.Random):
    """Eén login-account per medewerker, met een niet-voorspelbaar account_id."""
    ids = rng.sample(range(101, 199), len(MEDEWERKERS))
    accounts = []
    for (mid, voornaam, achternaam, _f, _a), account_id in zip(MEDEWERKERS, ids):
        gebruikersnaam = (voornaam[0] + achternaam).lower().replace(" ", "")
        accounts.append((account_id, mid, gebruikersnaam))
    accounts.sort()
    return accounts


def make_prijswijzigingen(rng: random.Random, facturen, sofie_account):
    """Gewone prijscorrecties (kantooruren, boekhouding) + de drie fraudelijnen."""
    catalogus = {p[0]: p[3] for p in PRODUCTEN}
    gewone = [f for f in facturen if f[0] != FRAUDE_FACTUUR_ID]
    account_van = {mid: aid for aid, mid, _g in ACCOUNTS}

    rows = []
    wid = 1
    for _ in range(24):
        fid, _kid, datum, _bedrag = rng.choice(gewone)
        pid = rng.choice(list(catalogus))
        oud = catalogus[pid]
        nieuw = round(oud * rng.choice([0.95, 0.97, 1.03, 1.05]), 2)
        d = date.fromisoformat(datum) + timedelta(days=rng.randint(0, 2))
        d = min(d, FACTUUR_END)
        uur = rng.randint(8, 16)
        minuut = rng.randint(0, 59)
        if uur == 8:
            minuut = max(minuut, 31)
        tijd = f"{uur:02d}:{minuut:02d}"
        mid = rng.choices(BOEKHOUDING_IDS, weights=[55, 33, 12])[0]
        rows.append((wid, fid, pid, oud, nieuw, d.isoformat(), tijd, account_van[mid]))
        wid += 1

    # De fraude: drie prijzen op de vervalste factuur, 's avonds laat,
    # met het account van Sofie Persoons.
    for pid, tijd in zip(FRAUDE_PRODUCTEN, ["22:19", "22:21", "22:24"]):
        oud = catalogus[pid]
        nieuw = round(oud * FRAUDE_KORTING, 2)
        rows.append((wid, FRAUDE_FACTUUR_ID, pid, oud, nieuw,
                     FRAUDE_DATUM, tijd, sofie_account))
        wid += 1
    return rows


def werkdagen():
    dagen = []
    d = BADGE_START
    while d <= BADGE_END:
        if d.weekday() < 5:
            dagen.append(d)
        d += timedelta(days=1)
    return dagen


def make_badge_logs(rng: random.Random):
    """Badge in/uit per medewerker per werkdag; 16 mei 2025 wordt geregisseerd."""
    patronen = {
        "logistiek": ((6, 45, 7, 5), (15, 20, 16, 5)),
        "magazijn": ((7, 25, 7, 50), (16, 0, 16, 40)),
        "onderhoud": ((14, 55, 15, 10), (20, 5, 20, 20)),   # avondploeg
    }
    kantoor = ((8, 10, 9, 5), (16, 30, 17, 45))

    geregisseerd = {
        # medewerker_id: [(tijd, richting), ...] op FRAUDE_DATUM
        SOFIE_ID: [("08:23", "in"), ("17:04", "uit")],
        DADER_ID: [("08:41", "in"), ("17:12", "uit"),
                   ("22:12", "in"), ("23:05", "uit")],
        WOUTER_ID: [("08:56", "in"), ("21:31", "uit")],   # serverupdate
        NADIA_ID: [("15:03", "in"), ("20:15", "uit")],
    }

    rows = []
    for mid, _v, _a, _functie, afdeling in MEDEWERKERS:
        (i1, i2, i3, i4), (u1, u2, u3, u4) = patronen.get(afdeling, kantoor)
        for d in werkdagen():
            datum = d.isoformat()
            if datum == FRAUDE_DATUM and mid in geregisseerd:
                for tijd, richting in geregisseerd[mid]:
                    rows.append((mid, datum, tijd, richting))
                continue
            if rng.random() < 0.08:
                continue  # afwezig (verlof, ziekte, werf)
            t_in = rng.randint(i1 * 60 + i2, i3 * 60 + i4)
            t_uit = rng.randint(u1 * 60 + u2, u3 * 60 + u4)
            rows.append((mid, datum, f"{t_in // 60:02d}:{t_in % 60:02d}", "in"))
            rows.append((mid, datum, f"{t_uit // 60:02d}:{t_uit % 60:02d}", "uit"))

    rows.sort(key=lambda r: (r[1], r[2], r[0]))
    return [(i + 1, mid, datum, tijd, richting)
            for i, (mid, datum, tijd, richting) in enumerate(rows)]


def make_verhoren():
    return [
        (1, TOM_ID, "2025-06-03",
         "Prijzen aanpassen op een bestaande factuur? Dat kan alleen met een "
         "account van de boekhouding. De vertegenwoordigers kunnen dat niet "
         "met hun eigen login."),
        (2, SOFIE_ID, "2025-06-03",
         "Om tien uur 's avonds? Toen was ik al lang thuis. Ik badge elke dag "
         "rond vijf uur uit, controleer gerust de badge_logs. En eerlijk "
         "gezegd: half de gang weet dat mijn wachtwoord op een post-it onder "
         "mijn toetsenbord ligt."),
        (3, HANS_ID, "2025-06-03",
         "De hoofdingang gaat om 19 uur op slot, maar wie een badge heeft kan "
         "altijd binnen langs de personeelsingang. Dat wordt allemaal "
         "geregistreerd."),
        (4, NADIA_ID, "2025-06-04",
         "Ik poets elke avond tot een uur of acht. Die vrijdag was er niets "
         "bijzonders, toen ik vertrok was alleen de IT-man er nog."),
        (5, WOUTER_ID, "2025-06-04",
         "Vrijdagavond deed ik een serverupdate tot halftien. Toen ik "
         "vertrok was het gebouw leeg. Dacht ik toch."),
        (6, DADER_ID, "2025-06-04",
         "Die vrijdagavond was ik gewoon thuis. Ik zet 's avonds nooit een "
         "voet in het gebouw, dat mag je iedereen vragen."),
    ]


def make_emails(rng: random.Random):
    """E-mailmetadata: intern ruisverkeer + het spoor naar de klant."""
    adres = {m[0]: f"{m[1].lower()}.{m[2].lower().replace(' ', '')}@steenberg.be"
             for m in MEDEWERKERS}

    ruis = [
        (8, 5, "Offerte 2025-118 Bouwbedrijf Verhelst", "2025-05-06"),
        (16, 1, "Serverupdate gepland op vrijdagavond 16 mei", "2025-05-12"),
        (21, 1, "Vakantieplanning juli en augustus", "2025-05-07"),
        (2, 3, "Kwartaalcijfers Q1 nakijken", "2025-05-08"),
        (15, 12, "Levering welfsels maandagochtend", "2025-05-09"),
        (6, 9, "Teamvergadering verkoop donderdag 10u", "2025-05-13"),
        (10, 27, "Nieuwe prijslijst leverancier isolatie", "2025-05-14"),
        (22, 1, "Opendeurdag: voorstel affiche", "2025-05-15"),
        (28, 15, "Veiligheidsronde magazijn: verslag", "2025-05-19"),
        (3, 4, "Aanmaningen tweede kwartaal", "2025-05-20"),
        (7, 8, "Werfbezoek Zottegem verplaatst", "2025-05-21"),
        (20, 21, "Bezoekersparking vrijdag volzet", "2025-05-22"),
        (11, 10, "Bestelbon cement goedgekeurd", "2025-05-23"),
        (25, 6, "Klantenfiches bijgewerkt", "2025-05-26"),
        (4, 2, "Btw-aangifte klaar voor controle", "2025-05-27"),
        (9, 24, "Offerte klinkerwerken Oudenaarde", "2025-05-29"),
        (13, 15, "Voorraadtelling pallets afgerond", "2025-05-30"),
        (17, 20, "Bestelling poetsmateriaal", "2025-06-02"),
    ]
    rows = []
    eid = 1
    for van_mid, naar_mid, onderwerp, datum in ruis:
        rows.append((eid, adres[van_mid], adres[naar_mid], onderwerp, datum))
        eid += 1

    davy = "davy.claes@denderbouw.be"
    ruben = adres[DADER_ID]
    for van, naar, onderwerp, datum in [
        (ruben, davy, "Prijslijst mei - speciale voorwaarden", "2025-05-13"),
        (davy, ruben, "Re: Prijslijst mei - speciale voorwaarden", "2025-05-14"),
        (davy, ruben, "Etentje zondag bij mama?", "2025-05-25"),
    ]:
        rows.append((eid, van, naar, onderwerp, datum))
        eid += 1
    return rows


def make_auditverslagen(fraude_fid):
    return [
        (1, "2025-04-07", "voorraad",
         "Steekproef in het magazijn: voorraad stemt overeen met het systeem. "
         "Geen opmerkingen."),
        (2, "2025-04-14", "kascontrole",
         "Kascontrole hoofdkantoor: kleine kas klopt tot op de cent."),
        (3, "2025-04-28", "veiligheid",
         "Veiligheidsronde met de preventieadviseur: twee blusapparaten "
         "vervangen, verder geen opmerkingen."),
        (4, "2025-05-05", "facturatie",
         "Maandelijkse controle van de facturatie over april: geen "
         "onregelmatigheden vastgesteld."),
        (5, "2025-05-12", "voorraad",
         "Telling pallets gevelsteen: verschil van twee pallets, verklaard "
         "door een retour die nog niet was ingeboekt."),
        (6, "2025-05-26", "kascontrole",
         "Kascontrole hoofdkantoor: geen opmerkingen."),
        (7, AUDIT_DATUM, "facturatie",
         f"Maandelijkse controle van de facturatie over mei: op factuur "
         f"{fraude_fid} van 16 mei 2025 werden drie eenheidsprijzen met 80 "
         f"procent verlaagd nadat de factuur al was opgemaakt. Voor die "
         f"kortingen bestaat geen enkele goedkeuring. De aanpassingen "
         f"gebeurden buiten de kantooruren en staan in het logboek van de "
         f"prijswijzigingen."),
        (8, "2025-06-16", "veiligheid",
         "Controle personeelsingang: badgelezer werkt correct, camerabeelden "
         "worden 30 dagen bewaard."),
    ]


def make_controle(fraude_fid):
    rows = []
    for mid, voornaam, achternaam, _f, _a in MEDEWERKERS:
        naam = f"{voornaam} {achternaam}"
        if mid == DADER_ID:
            uitkomst = (f"Juist! {naam} gebruikte het account van de "
                        f"boekhouding om op factuur {fraude_fid} de prijzen te "
                        f"verlagen voor het bedrijf van zijn broer Davy. Zijn "
                        f"badge verraadt dat hij die avond in het gebouw was. "
                        f"Zaak opgelost - sterk speurwerk, detective!")
        else:
            uitkomst = (f"Nee. Voor {naam} is er geen sluitend bewijs. "
                        f"Bekijk de sporen nog eens rustig.")
        rows.append((naam, uitkomst))
    rows.sort(key=lambda r: r[0])
    return rows


def build_db(facturen, accounts, prijswijzigingen, badge_logs, verhoren,
             emails, auditverslagen, controle):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE medewerkers (
      medewerker_id INTEGER PRIMARY KEY,
      voornaam      TEXT NOT NULL,
      achternaam    TEXT NOT NULL,
      functie       TEXT NOT NULL,
      afdeling      TEXT NOT NULL
    );
    CREATE TABLE accounts (
      account_id    INTEGER PRIMARY KEY,
      medewerker_id INTEGER NOT NULL,
      gebruikersnaam TEXT NOT NULL,
      FOREIGN KEY (medewerker_id) REFERENCES medewerkers(medewerker_id)
    );
    CREATE TABLE klanten (
      klant_id       INTEGER PRIMARY KEY,
      bedrijfsnaam   TEXT NOT NULL,
      contactpersoon TEXT NOT NULL,
      email          TEXT NOT NULL,
      gemeente       TEXT NOT NULL
    );
    CREATE TABLE producten (
      product_id    INTEGER PRIMARY KEY,
      naam          TEXT NOT NULL,
      categorie     TEXT NOT NULL,
      eenheidsprijs REAL NOT NULL
    );
    CREATE TABLE facturen (
      factuur_id INTEGER PRIMARY KEY,
      klant_id   INTEGER NOT NULL,
      datum      TEXT NOT NULL,    -- ISO: YYYY-MM-DD
      bedrag     REAL NOT NULL,
      FOREIGN KEY (klant_id) REFERENCES klanten(klant_id)
    );
    CREATE TABLE prijswijzigingen (
      wijziging_id INTEGER PRIMARY KEY,
      factuur_id   INTEGER NOT NULL,
      product_id   INTEGER NOT NULL,
      oude_prijs   REAL NOT NULL,
      nieuwe_prijs REAL NOT NULL,
      datum        TEXT NOT NULL,  -- ISO: YYYY-MM-DD
      tijdstip     TEXT NOT NULL,  -- HH:MM
      account_id   INTEGER NOT NULL,
      FOREIGN KEY (factuur_id) REFERENCES facturen(factuur_id),
      FOREIGN KEY (product_id) REFERENCES producten(product_id),
      FOREIGN KEY (account_id) REFERENCES accounts(account_id)
    );
    CREATE TABLE badge_logs (
      log_id        INTEGER PRIMARY KEY,
      medewerker_id INTEGER NOT NULL,
      datum         TEXT NOT NULL,  -- ISO: YYYY-MM-DD
      tijdstip      TEXT NOT NULL,  -- HH:MM
      richting      TEXT NOT NULL,  -- 'in' of 'uit'
      FOREIGN KEY (medewerker_id) REFERENCES medewerkers(medewerker_id)
    );
    CREATE TABLE verhoren (
      verhoor_id    INTEGER PRIMARY KEY,
      medewerker_id INTEGER NOT NULL,
      datum         TEXT NOT NULL,
      tekst         TEXT NOT NULL,
      FOREIGN KEY (medewerker_id) REFERENCES medewerkers(medewerker_id)
    );
    CREATE TABLE emails (
      email_id  INTEGER PRIMARY KEY,
      afzender  TEXT NOT NULL,
      ontvanger TEXT NOT NULL,
      onderwerp TEXT NOT NULL,
      datum     TEXT NOT NULL
    );
    CREATE TABLE auditverslagen (
      verslag_id INTEGER PRIMARY KEY,
      datum      TEXT NOT NULL,
      categorie  TEXT NOT NULL,
      tekst      TEXT NOT NULL
    );
    CREATE TABLE controle (
      verdachte TEXT PRIMARY KEY,
      uitkomst  TEXT NOT NULL
    );
    """)
    cur.executemany("INSERT INTO medewerkers VALUES (?,?,?,?,?)", MEDEWERKERS)
    cur.executemany("INSERT INTO accounts VALUES (?,?,?)", accounts)
    cur.executemany("INSERT INTO klanten VALUES (?,?,?,?,?)", KLANTEN)
    cur.executemany("INSERT INTO producten VALUES (?,?,?,?)", PRODUCTEN)
    cur.executemany("INSERT INTO facturen VALUES (?,?,?,?)", facturen)
    cur.executemany("INSERT INTO prijswijzigingen VALUES (?,?,?,?,?,?,?,?)",
                    prijswijzigingen)
    cur.executemany("INSERT INTO badge_logs VALUES (?,?,?,?,?)", badge_logs)
    cur.executemany("INSERT INTO verhoren VALUES (?,?,?,?)", verhoren)
    cur.executemany("INSERT INTO emails VALUES (?,?,?,?,?)", emails)
    cur.executemany("INSERT INTO auditverslagen VALUES (?,?,?,?)", auditverslagen)
    cur.executemany("INSERT INTO controle VALUES (?,?)", controle)
    con.commit()
    cur.execute("VACUUM")
    con.close()


def verify():
    """Bewaakt het volledige spoor van de detective-les. Faalt hard bij een gat."""
    con = sqlite3.connect(DB_PATH)
    q = lambda sql, *p: con.execute(sql, p).fetchall()
    one = lambda sql, *p: con.execute(sql, p).fetchone()[0]
    fid = FRAUDE_FACTUUR_ID

    # Het factuurnummer mag niet verschuiven: les en verslag verwijzen ernaar.
    assert fid == VERWACHT_FRAUDE_FACTUUR_ID, fid

    # Stap 1: exact één auditverslag op 2 juni, en het noemt de factuur.
    verslagen = q("SELECT tekst FROM auditverslagen WHERE datum = ?", AUDIT_DATUM)
    assert len(verslagen) == 1
    assert str(fid) in verslagen[0][0]

    # Stap 2: de factuur hoort bij Dender Bouwmaterialen, contact Davy Claes.
    rij = q("SELECT k.bedrijfsnaam, k.contactpersoon FROM facturen f "
            "JOIN klanten k ON f.klant_id = k.klant_id "
            "WHERE f.factuur_id = ?", fid)[0]
    assert rij == ("Dender Bouwmaterialen bv", "Davy Claes")
    assert one("SELECT datum FROM facturen WHERE factuur_id = ?", fid) == FRAUDE_DATUM

    # Stap 3: exact drie prijswijzigingen op die factuur, 's avonds, 80% korting,
    # allemaal met hetzelfde account.
    wijz = q("SELECT oude_prijs, nieuwe_prijs, datum, tijdstip, account_id "
             "FROM prijswijzigingen WHERE factuur_id = ?", fid)
    assert len(wijz) == 3
    accounts_gebruikt = {w[4] for w in wijz}
    assert len(accounts_gebruikt) == 1
    for oud, nieuw, datum, tijd, _acc in wijz:
        assert datum == FRAUDE_DATUM and tijd >= "22:00"
        assert abs(nieuw - round(oud * FRAUDE_KORTING, 2)) < 0.01
    # Alle andere wijzigingen gebeurden tijdens de kantooruren.
    assert one("SELECT COUNT(*) FROM prijswijzigingen "
               "WHERE factuur_id <> ? AND (tijdstip < '08:30' OR tijdstip > '17:00')",
               fid) == 0

    # Stap 4: het gebruikte account is dat van Sofie Persoons (boekhouding).
    sofie_account = accounts_gebruikt.pop()
    naam = q("SELECT m.voornaam, m.achternaam, m.afdeling FROM accounts a "
             "JOIN medewerkers m ON a.medewerker_id = m.medewerker_id "
             "WHERE a.account_id = ?", sofie_account)[0]
    assert naam == ("Sofie", "Persoons", "boekhouding")

    # Stap 5: Sofie heeft een verhoor dat naar de badge_logs verwijst, en een
    # sluitend alibi: die dag uitgebadged om 17:04, daarna niets meer.
    assert "badge_logs" in one("SELECT tekst FROM verhoren WHERE medewerker_id = ?",
                               SOFIE_ID)
    sofie_logs = q("SELECT tijdstip, richting FROM badge_logs "
                   "WHERE medewerker_id = ? AND datum = ? ORDER BY tijdstip",
                   SOFIE_ID, FRAUDE_DATUM)
    assert sofie_logs == [("08:23", "in"), ("17:04", "uit")]

    # Stap 6: die avond na 18:00 zijn er exact vier badge-events (Nadia uit,
    # Wouter uit, Ruben in en uit) en badged exact één iemand nog binnen: Ruben.
    avond = q("SELECT medewerker_id, tijdstip, richting FROM badge_logs "
              "WHERE datum = ? AND tijdstip > '18:00' ORDER BY tijdstip",
              FRAUDE_DATUM)
    assert [(r[0], r[2]) for r in avond] == [
        (NADIA_ID, "uit"), (WOUTER_ID, "uit"), (DADER_ID, "in"), (DADER_ID, "uit")]
    binnen = q("SELECT medewerker_id FROM badge_logs "
               "WHERE datum = ? AND tijdstip > '18:00' AND richting = 'in'",
               FRAUDE_DATUM)
    assert binnen == [(DADER_ID,)]
    # Enkel de dader was binnen op het moment van de wijzigingen (22:19-22:24).
    assert one("SELECT COUNT(DISTINCT medewerker_id) FROM badge_logs WHERE datum = ? "
               "AND richting = 'in' AND tijdstip <= '22:19' AND medewerker_id IN "
               "(SELECT medewerker_id FROM badge_logs WHERE datum = ? "
               " AND richting = 'uit' AND tijdstip >= '22:19')",
               FRAUDE_DATUM, FRAUDE_DATUM) == 1
    # De dader loog tijdens zijn verhoor ("was thuis").
    assert "thuis" in one("SELECT tekst FROM verhoren WHERE medewerker_id = ?",
                          DADER_ID)

    # Stap 7: e-mails met de klant: exact drie, allemaal tussen Ruben en Davy.
    mails = q("SELECT afzender, ontvanger FROM emails "
              "WHERE afzender LIKE '%denderbouw%' OR ontvanger LIKE '%denderbouw%'")
    assert len(mails) == 3
    for van, naar in mails:
        assert {van, naar} == {"ruben.claes@steenberg.be", "davy.claes@denderbouw.be"}
    # De familieband is zichtbaar: zelfde achternaam als de contactpersoon.
    assert one("SELECT achternaam FROM medewerkers WHERE medewerker_id = ?",
               DADER_ID) == "Claes"

    # Stap 8: de controletabel dekt iedereen en enkel Ruben Claes is 'Juist'.
    assert one("SELECT COUNT(*) FROM controle") == len(MEDEWERKERS)
    juist = q("SELECT verdachte FROM controle WHERE uitkomst LIKE 'Juist!%'")
    assert juist == [("Ruben Claes",)]

    # Algemene consistentie.
    assert one("SELECT COUNT(*) FROM facturen f LEFT JOIN klanten k "
               "ON f.klant_id = k.klant_id WHERE k.klant_id IS NULL") == 0
    assert one("SELECT COUNT(*) FROM accounts a LEFT JOIN medewerkers m "
               "ON a.medewerker_id = m.medewerker_id WHERE m.medewerker_id IS NULL") == 0
    assert one("SELECT COUNT(*) FROM prijswijzigingen p LEFT JOIN accounts a "
               "ON p.account_id = a.account_id WHERE a.account_id IS NULL") == 0
    assert one("SELECT COUNT(DISTINCT medewerker_id) FROM badge_logs") == len(MEDEWERKERS)
    assert set(r[0] for r in q("SELECT DISTINCT richting FROM badge_logs")) == {"in", "uit"}

    n_badge = one("SELECT COUNT(*) FROM badge_logs")
    n_fact = one("SELECT COUNT(*) FROM facturen")
    print(f"OK: {len(MEDEWERKERS)} medewerkers, {len(KLANTEN)} klanten, "
          f"{n_fact} facturen, {n_badge} badge-events")
    print(f"    verdachte factuur: {fid} (Dender Bouwmaterialen bv, {FRAUDE_DATUM})")
    print(f"    misbruikt account: {sofie_account} (Sofie Persoons)")
    print(f"    dader: Ruben Claes")
    print(f"    bestand: {DB_PATH} ({DB_PATH.stat().st_size / 1024:.0f} KiB)")
    con.close()


ACCOUNTS = None


def main():
    global FRAUDE_FACTUUR_ID, ACCOUNTS
    rng = random.Random(SEED)
    facturen, FRAUDE_FACTUUR_ID = make_facturen(rng)
    ACCOUNTS = make_accounts(rng)
    sofie_account = next(a for a, mid, _g in ACCOUNTS if mid == SOFIE_ID)
    prijswijzigingen = make_prijswijzigingen(rng, facturen, sofie_account)
    badge_logs = make_badge_logs(rng)
    verhoren = make_verhoren()
    emails = make_emails(rng)
    auditverslagen = make_auditverslagen(FRAUDE_FACTUUR_ID)
    controle = make_controle(FRAUDE_FACTUUR_ID)
    build_db(facturen, ACCOUNTS, prijswijzigingen, badge_logs, verhoren,
             emails, auditverslagen, controle)
    verify()


if __name__ == "__main__":
    main()
