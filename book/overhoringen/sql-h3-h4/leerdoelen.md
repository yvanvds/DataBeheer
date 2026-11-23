# Leerdoelen — SQL 3 en 4

## SQL 3 — JOIN

Bron: `book/chapters/SQL/03_JOIN.ipynb`, `book/chapters/SQL/03b_AdventureWorks.ipynb`, `book/chapters/SQL/03c_Detective.ipynb`

Niet opgenomen: `JOIN` zonder `INNER` (alleen gebruikt in het leerdoelenblok en in SQL 4, nergens uitgelegd), waarom een foreign key dubbele gegevens vermijdt (§1: kort uitgelegd, geen oefening; normalisatie zit in de ERD-hoofdstukken), `RIGHT JOIN` en `FULL JOIN` (niet in de cursus), de reflectievragen van 03c_Detective over wachtwoorden en sporen wissen (geen SQL-vaardigheid), de uitleg over de editor (Download mijn queries).

### SQL3.1 — Sleutels herkennen in een schema
- Doel: De leerling kan in een schema de primary key van een tabel en de foreign keys die naar een andere tabel verwijzen aanwijzen, en zo bepalen via welke kolommen twee tabellen samenhangen.
- Belang: kern
- Waar: 03_JOIN §1 Waarom JOIN?, §2 oef. 1–6; 03b_AdventureWorks inleiding, oef. 1–4; 03c_Detective stap 2–4
- Leerplan: LPD 1

### SQL3.2 — Twee tabellen combineren met INNER JOIN
- Doel: De leerling kan met `INNER JOIN … ON` twee tabellen combineren via de juiste sleutelkolommen en uitleggen dat alleen rijen met een match in beide tabellen in het resultaat komen.
- Belang: kern
- Waar: 03_JOIN §2 INNER JOIN, oef. 1–3; 03b_AdventureWorks oef. 1–3; 03c_Detective stap 2 en 4
- Leerplan: LPD 4

### SQL3.3 — Kolommen aanduiden met tabelnaam of alias
- Doel: De leerling kan in een query met JOIN een kolom aanduiden met de tabelnaam (`customers.first_name`) of met een korte alias (`FROM customers c`, `c.first_name`), zodat een kolomnaam die in meer tabellen voorkomt eenduidig is.
- Belang: aanvullend
- Waar: 03_JOIN §2 INNER JOIN (uitleg en tip), oef. 1–6, §3 oef. 1–5
- Leerplan: LPD 4

### SQL3.4 — Meer dan twee tabellen combineren
- Doel: De leerling kan met meerdere JOINs na elkaar drie of meer tabellen combineren, ook via een koppeltabel (bv. de bestelregels tussen bestellingen en producten).
- Belang: kern
- Waar: 03_JOIN §2 Meerdere JOIN's, oef. 4–6; 03b_AdventureWorks inleiding (koppeltabel), oef. 4, LEFT JOIN oef. 4
- Leerplan: LPD 4

### SQL3.5 — Gecombineerde rijen filteren en sorteren
- Doel: De leerling kan een query met JOIN aanvullen met `WHERE` en `ORDER BY` op kolommen uit de gekoppelde tabellen (bv. de bestellingen van klanten uit één stad, de recentste eerst).
- Belang: kern
- Waar: 03_JOIN §2 oef. 3–6, §3 oef. 4–5; 03c_Detective stap 2–6
- Leerplan: LPD 4

### SQL3.6 — Alle rijen tonen met LEFT JOIN
- Doel: De leerling kan met `LEFT JOIN` alle rijen van de linkertabel (na `FROM`) tonen, ook zonder match, en uitleggen dat de kolommen van de rechtertabel dan `NULL` zijn.
- Belang: kern
- Waar: 03_JOIN §3 LEFT JOIN, oef. 4; 03b_AdventureWorks LEFT JOIN oef. 1–3
- Leerplan: LPD 4

### SQL3.7 — Rijen zonder match vinden
- Doel: De leerling kan met `LEFT JOIN` en `IS NULL` op een kolom van de rechtertabel de rijen vinden die geen match hebben (bv. klanten zonder bestelling, producten die nooit besteld werden).
- Belang: kern
- Waar: 03_JOIN §3 LEFT JOIN, oef. 1–3 en 5
- Leerplan: LPD 4

### SQL3.8 — Een onderzoek in stappen oplossen
- Doel: De leerling kan een vraag over een onbekende databank in stappen beantwoorden: een waarde uit het resultaat van een query (bv. een id of een datum) gebruiken in de volgende query, tot er een besluit is.
- Belang: aanvullend
- Waar: 03c_Detective stap 1–7, De ontknoping
- Leerplan: LPD 4

## SQL 4 — Groeperen

Bron: `book/chapters/SQL/04_GROUP_BY.ipynb`, `book/chapters/SQL/04b_AdventureWorks.ipynb`

Niet opgenomen: het gemiddelde van sommen (§2 oef. 7: vraagt een subquery of `COUNT(DISTINCT …)`, nergens uitgelegd), sorteren op een samengevatte waarde, `ROUND()` en `HAVING` (SQL 5).

### SQL4.1 — Samenvatten met aggregatiefuncties
- Doel: De leerling kan met `COUNT`, `SUM`, `AVG`, `MIN` en `MAX` één waarde over meerdere rijen berekenen en de functie kiezen die bij de vraag past.
- Belang: kern
- Waar: 04_GROUP_BY §1 Aggregatiefuncties, oef. 1–10; 04b_AdventureWorks oef. 1–5
- Leerplan: LPD 4

### SQL4.2 — COUNT(*) en COUNT(kolom) onderscheiden
- Doel: De leerling kan uitleggen dat `COUNT(*)` alle rijen telt en `COUNT(kolom)` alleen de rijen waarin die kolom ingevuld is (niet `NULL`).
- Belang: aanvullend
- Waar: 04_GROUP_BY §1 Aggregatiefuncties, oef. 3
- Leerplan: LPD 4

### SQL4.3 — Gefilterde rijen samenvatten
- Doel: De leerling kan een aggregatiefunctie combineren met `WHERE`, zodat alleen de rijen die aan de voorwaarden voldoen meetellen (bv. het aantal bestellingen uit 2024 die niet geannuleerd zijn).
- Belang: kern
- Waar: 04_GROUP_BY §1 oef. 5–10
- Leerplan: LPD 4

### SQL4.4 — Een berekening samenvatten
- Doel: De leerling kan een berekening per rij samenvatten met een aggregatiefunctie, bv. de omzet als `SUM(quantity * unit_price)`.
- Belang: kern
- Waar: 04_GROUP_BY §1 oef. 10, §2 oef. 5 en 8
- Leerplan: LPD 4

### SQL4.5 — Per groep samenvatten met GROUP BY
- Doel: De leerling kan met `GROUP BY` een aggregatiefunctie per groep berekenen (bv. het aantal klanten per stad), met de groepeerkolom in `SELECT` en in `GROUP BY`, en uitleggen waarom dezelfde query zonder `GROUP BY` maar één rij geeft.
- Belang: kern
- Waar: 04_GROUP_BY §2 GROUP BY, oef. 1–8; 04b_AdventureWorks oef. 1–5
- Leerplan: LPD 4

### SQL4.6 — Groeperen over gekoppelde tabellen
- Doel: De leerling kan tabellen eerst met JOIN combineren en daarna samenvatten of groeperen op een kolom uit een andere tabel (bv. per categorienaam in plaats van per id).
- Belang: kern
- Waar: 04_GROUP_BY §1 oef. 9–10, §2 oef. 4, 6 en 7; 04b_AdventureWorks oef. 1, 3 en 5
- Leerplan: LPD 4

## Dekking

Beoordeel per leerdoel (een rij) over de aangeduide vragen heen.

| Leerdoel | V1 | V2 | V3 | V4 | V5 | V6 | V7 | V8 | V9 | V10 |
|---|---|---|---|---|---|---|---|---|---|---|
| SQL3.1 — Sleutels herkennen in een schema | x | x | | | | | | | | |
| SQL3.2 — Twee tabellen combineren met INNER JOIN | x | x | | x | | | | | | |
| SQL3.3 — Kolommen aanduiden met tabelnaam of alias | x | x | | | | | | | | |
| SQL3.4 — Meer dan twee tabellen combineren | x | | | | x | | | | | |
| SQL3.5 — Gecombineerde rijen filteren en sorteren | x | | | | x | | | | | |
| SQL3.6 — Alle rijen tonen met LEFT JOIN | | | x | x | | | | | | |
| SQL3.7 — Rijen zonder match vinden | | | x | x | | | | | | |
| SQL3.8 — Een onderzoek in stappen oplossen | | | | | x | | | | | |
| SQL4.1 — Samenvatten met aggregatiefuncties | | | | | | x | x | x | x | |
| SQL4.2 — COUNT(*) en COUNT(kolom) onderscheiden | | | | | | | x | | | |
| SQL4.3 — Gefilterde rijen samenvatten | | | | | | x | | | | x |
| SQL4.4 — Een berekening samenvatten | | | | | | | | | | x |
| SQL4.5 — Per groep samenvatten met GROUP BY | | | | | | | | x | x | x |
| SQL4.6 — Groeperen over gekoppelde tabellen | | | | | | | | | x | x |

Niet getoetst: geen; alle 14 leerdoelen worden getoetst.
