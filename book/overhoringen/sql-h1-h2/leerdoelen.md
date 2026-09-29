# Leerdoelen — SQL 1 en 2

## SQL 1 — Starten met SQL

Bron: `book/chapters/SQL/01_Starten_met_sql.ipynb`, `book/chapters/SQL/01b_AdventureWorks.ipynb`

Niet opgenomen: commentaar in een query (§1: uitgelegd, maar geen oefening vraagt erom), primary en foreign keys (§2: alleen genoemd, uitgelegd in SQL 3 en de ERD-hoofdstukken), `NOT` als losse operator (§4 noemt het, geen oefening vraagt het; `NOT IN` zit in SQL 2), de uitleg over de editor (Run, Schema, Reset db, Groot scherm, Mijn werk).

### SQL1.1 — Kolommen opvragen met SELECT … FROM
- Doel: De leerling kan met `SELECT … FROM` gekozen kolommen of met `*` alle kolommen uit één tabel opvragen.
- Belang: kern
- Waar: 01_Starten_met_sql §3 Je eerste query, oef. 1–5; 01b_AdventureWorks oef. 1–2
- Leerplan: LPD 4

### SQL1.2 — Rijen filteren met één voorwaarde
- Doel: De leerling kan met `WHERE` en een vergelijking (`=`, `<>`, `<`, `>`, `<=`, `>=`) de gevraagde rijen selecteren, met tekst tussen enkele aanhalingstekens.
- Belang: kern
- Waar: 01_Starten_met_sql §4 Filteren met WHERE, oef. 1 en 4; 01b_AdventureWorks oef. 3–4
- Leerplan: LPD 4

### SQL1.3 — Voorwaarden combineren met AND en OR
- Doel: De leerling kan meerdere voorwaarden combineren met `AND` en `OR`, met haakjes waar `OR` en `AND` samen voorkomen.
- Belang: kern
- Waar: 01_Starten_met_sql §4 Filteren met WHERE, oef. 2, 3 en 5
- Leerplan: LPD 4

### SQL1.4 — Resultaten sorteren met ORDER BY
- Doel: De leerling kan het resultaat met `ORDER BY` oplopend (`ASC`) of aflopend (`DESC`) sorteren, ook op meer dan één kolom.
- Belang: kern
- Waar: 01_Starten_met_sql §5 Sorteren met ORDER BY, §6 oef. 1–3, §7 oef. 1–2; 01b_AdventureWorks oef. 2–4
- Leerplan: LPD 4

### SQL1.5 — Een top-N opvragen met LIMIT
- Doel: De leerling kan met `LIMIT`, na een `ORDER BY`, alleen de eerste rijen van een resultaat tonen (bv. de vijf duurste producten).
- Belang: kern
- Waar: 01_Starten_met_sql §6 Aantal rijen beperken met LIMIT, oef. 1–4, §7 oef. 4; 01b_AdventureWorks oef. 5 en 7
- Leerplan: LPD 4

### SQL1.6 — Unieke waarden tonen met DISTINCT
- Doel: De leerling kan met `DISTINCT` elke waarde (of combinatie van waarden) maar één keer tonen.
- Belang: kern
- Waar: 01_Starten_met_sql §7 Duplicaten verwijderen met DISTINCT, oef. 1–3; 01b_AdventureWorks oef. 6
- Leerplan: LPD 4

### SQL1.7 — Berekende kolommen maken met AS
- Doel: De leerling kan in `SELECT` rekenen met kolommen (bv. prijs maal voorraad) en de berekende kolom met `AS` een naam geven.
- Belang: kern
- Waar: 01_Starten_met_sql §8 Berekende kolommen + aliassen, oef. 2–3; 01b_AdventureWorks oef. 7
- Leerplan: LPD 4

### SQL1.8 — Tekst samenvoegen met ||
- Doel: De leerling kan tekstkolommen samenvoegen met `||` en uitleggen waarom `+` dat in SQLite niet doet.
- Belang: aanvullend
- Waar: 01_Starten_met_sql §8 Berekende kolommen + aliassen, oef. 1
- Leerplan: LPD 4

### SQL1.9 — Een onbekend schema lezen
- Doel: De leerling kan in het schema van een onbekende databank met Engelse namen de juiste tabel en kolommen vinden en er de query's uit dit hoofdstuk op schrijven.
- Belang: aanvullend
- Waar: 01b_AdventureWorks oef. 1–7
- Leerplan: LPD 4

## SQL 2 — Meer opties voor WHERE

Bron: `book/chapters/SQL/02_Meer_opties_voor_WHERE.ipynb`, `book/chapters/SQL/02b_AdventureWorks.ipynb`

Niet opgenomen: `LOWER()` om zonder onderscheid tussen hoofdletters en kleine letters te zoeken (§2: alleen een tip, geen oefening vraagt het), de uitleg over de editor (Schema, Data, preview).

### SQL2.1 — Ontbrekende waarden filteren met IS NULL
- Doel: De leerling kan met `IS NULL` en `IS NOT NULL` rijen selecteren waar een waarde ontbreekt of ingevuld is, en uitleggen waarom `= NULL` of `= 'null'` dat niet doet.
- Belang: kern
- Waar: 02_Meer_opties_voor_WHERE §1 Speciale waarden: NULL, oef. 1–3; 02b_AdventureWorks oef. 1, 2 en 8
- Leerplan: LPD 4

### SQL2.2 — Tekstpatronen zoeken met LIKE
- Doel: De leerling kan met `LIKE` en de jokertekens `%` (willekeurig veel tekens) en `_` (precies één teken) tekst selecteren die begint met, eindigt op of bevat, of een vast aantal tekens heeft.
- Belang: kern
- Waar: 02_Meer_opties_voor_WHERE §2 Patronen zoeken met LIKE, oef. 1–6; 02b_AdventureWorks oef. 3–4
- Leerplan: LPD 4

### SQL2.3 — Filteren op een lijst met IN
- Doel: De leerling kan met `IN` en `NOT IN` rijen selecteren waarvan een kolom (niet) gelijk is aan één van de waarden uit een lijst.
- Belang: kern
- Waar: 02_Meer_opties_voor_WHERE §3 IN, NOT IN, oef. 1–4; 02b_AdventureWorks oef. 5
- Leerplan: LPD 4

### SQL2.4 — Een bereik filteren met BETWEEN
- Doel: De leerling kan met `BETWEEN … AND …` rijen selecteren waarvan een waarde binnen een bereik ligt, de grenzen inbegrepen (tot en met).
- Belang: kern
- Waar: 02_Meer_opties_voor_WHERE §4 BETWEEN, oef. 1–3; 02b_AdventureWorks oef. 6
- Leerplan: LPD 4

### SQL2.5 — Datums filteren als tekst
- Doel: De leerling kan datums in de vorm `YYYY-MM-DD` filteren, met `LIKE` op een deel van de datum of door ze te vergelijken (`>=`, `<`).
- Belang: kern
- Waar: 02_Meer_opties_voor_WHERE §2 oef. 3, Datum filteren; 02b_AdventureWorks oef. 7
- Leerplan: LPD 4

### SQL2.6 — Clausules in de juiste volgorde
- Doel: De leerling kan `WHERE`, `ORDER BY` en `LIMIT` in één query combineren in de volgorde `SELECT – FROM – WHERE – ORDER BY – LIMIT`.
- Belang: aanvullend
- Waar: 02_Meer_opties_voor_WHERE tip na Datum filteren; 02b_AdventureWorks oef. 3, 4, 6 en 9
- Leerplan: LPD 4

## Dekking

Beoordeel per leerdoel (een rij) over de aangeduide vragen heen.

| Leerdoel | V1 | V2 | V3 | V4 | V5 | V6 | V7 | V8 | V9 | V10 |
|---|---|---|---|---|---|---|---|---|---|---|
| SQL1.1 — Kolommen opvragen met SELECT … FROM | x | x | | | | | | | | |
| SQL1.2 — Rijen filteren met één voorwaarde | x | x | | | x | | | | | |
| SQL1.3 — Voorwaarden combineren met AND en OR | | x | | | | x | | | x | |
| SQL1.4 — Resultaten sorteren met ORDER BY | x | x | x | x | x | | x | | | |
| SQL1.5 — Een top-N opvragen met LIMIT | | | x | | | | | | | |
| SQL1.6 — Unieke waarden tonen met DISTINCT | | | | x | | | | | | |
| SQL1.7 — Berekende kolommen maken met AS | | | | | x | | | x | | |
| SQL1.8 — Tekst samenvoegen met \|\| | | | | | | | | x | | |
| SQL1.9 — Een onbekend schema lezen | | | x | | | x | | | | |
| SQL2.1 — Ontbrekende waarden filteren met IS NULL | | | | | | x | | | | |
| SQL2.2 — Tekstpatronen zoeken met LIKE | | | | x | | | | | | x |
| SQL2.3 — Filteren op een lijst met IN | | | | | | | x | | | |
| SQL2.4 — Een bereik filteren met BETWEEN | | | | | | | x | | | |
| SQL2.5 — Datums filteren als tekst | | | x | | | x | | | | x |
| SQL2.6 — Clausules in de juiste volgorde | | | x | | | | | | x | |

Niet getoetst: geen; alle 15 leerdoelen worden getoetst.
