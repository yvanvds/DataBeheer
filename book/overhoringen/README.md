# Overhoringen

Deze map bevat de overhoringen: losse pagina's die mee gepubliceerd worden op
GitHub Pages, maar niet bij de cursus horen (issue #60). Dit bestand wordt zelf
geen pagina.

Een overhoringpagina

- staat niet in `_toc.yml` en wordt nergens vanuit de cursus gelinkt;
- heeft zelf geen weg naar de cursus: geen zijbalk met inhoudstafel, geen logo,
  geen zoekveld, geen vorige/volgende, geen knoppen naar GitHub;
- staat niet in de zoekindex van de site (`searchindex.js`) en vraagt
  zoekmachines om ze niet op te nemen;
- ziet er duidelijk anders uit dan de cursus: een blauwe pagina met een vaste
  band **OVERHORING** bovenaan, in light en dark mode. Zo ziet de leraar vanop
  afstand wie de cursus opent.

## Mappen en adressen

```
book/overhoringen/
├── README.md                 dit bestand (geen pagina)
├── template/
│   └── overhoring.ipynb      de template, en de testpagina van de drie vraagtypes
└── <naam>/                   één map per overhoring, <naam> is een slug (bv. sql-h1-h2)
    ├── overhoring.ipynb      de overhoring
    ├── leerdoelen.md         voor de leraar (geen pagina): de leerdoelen en de dekkingstabel
    └── rubriek.csv           voor Teams (geen pagina), gemaakt met /rubriek
```

De skill /overhoring (`.claude/skills/overhoring/SKILL.md`, issue #63) maakt
zo'n map in één keer: de leerdoelen met /leerdoelen, de keuze van de vragen met
een dekkingstabel vraag × leerdoel (`## Dekking` in `leerdoelen.md`), de
rubriek met /rubriek en de overhoring zelf, en publiceert ze.
`.claude/skills/overhoring/check_overhoring.py` controleert de hele map. De
formaten van `leerdoelen.md` en `rubriek.csv` staan in de skills
`.claude/skills/leerdoelen/SKILL.md` en `.claude/skills/rubriek/SKILL.md`
(issue #62); `.claude/skills/rubriek/check_rubriek.py` controleert een rubriek
voor ze naar Teams gaat.

- **Welke bestanden een pagina worden:** elke notebook (`*.ipynb`) rechtstreeks
  in `book/overhoringen/<naam>/`. Al de rest (`leerdoelen.md`, `rubriek.csv`,
  notities, dieper geneste mappen) wordt geen pagina.
- **Adres:** `overhoringen/<naam>/overhoring.ipynb` wordt
  `https://yvanvds.github.io/DataBeheer/main/overhoringen/<naam>/overhoring.html`.
  De TeachBooks-deploy zet elke branch in een eigen map (main in `/main/`);
  zonder `/main/` geeft GitHub Pages een 404 die pas met JavaScript doorverwijst.
- **Antwoordbestand:** "Download mijn antwoorden" bewaart
  `<naam>-antwoorden.md`. Een tweede notebook in dezelfde map, bv. een
  parallelversie `groep-b.ipynb`, wordt `overhoringen/<naam>/groep-b.html` met
  antwoordbestand `<naam>-groep-b-antwoorden.md`.
- **Een nieuwe overhoring** vraagt geen aanpassing van de configuratie: maak de
  map, kopieer `template/overhoring.ipynb` erin en pas de cellen aan. Zet de
  pagina **niet** in `_toc.yml`.

## Formaat van de notebook

De cellen, van boven naar onder:

| cel | soort | inhoud |
|---|---|---|
| databank | code, tag `sql-db` | het pad naar de databank: `/_static/db/gadgetshop.db` (zie hieronder) |
| titel en doelen | markdown | `# <titel>`, eventueel een korte instructie, en een kop `## Doelen` met de leerdoelen in leerlingentaal (een lijst) |
| per vraag: vraagtekst | markdown | een kop `## Vraag n` (doorlopend genummerd vanaf 1, eventueel gevolgd door een titel: `## Vraag 2 — NULL`) en de vraagtekst |
| per vraag: antwoordcel | code, één tag uit de tabel hieronder | zie hieronder |

De drie vraagtypes (tag van de antwoordcel):

| tag | op de pagina | inhoud van de cel | in het antwoordbestand |
|---|---|---|---|
| `sql-live` | de SQL-editor uit de cursus | de startcode, bv. `-- Schrijf hier je query.` | de query als ` ```sql `-blok |
| `overhoring-open` | een tekstvak | de hulptekst in het lege vak | de tekst, als citaat |
| `overhoring-mc` | radioknoppen, één antwoord | de opties, één per regel; `code` tussen backticks mag | alle opties, de gekozen aangevinkt (`- [x]`) |

Regels:

- Na de kop van een vraag volgt precies één antwoordcel. Tekst ná de
  antwoordcel staat wel op de pagina, maar niet in het antwoordbestand.
- Een antwoordcel is nooit leeg: MyST-NB laat lege cellen weg uit de pagina.
- Andere codecellen dan `sql-db` en de drie antwoordtags horen er niet.
  Een voorbeeldquery in een vraag zet je in de markdown, als ` ```sql `-blok.
- Een meerkeuzevraag heeft minstens twee verschillende opties en duidt **niet**
  aan welke juist is. Er staan nergens modeloplossingen: de repo en de site zijn
  publiek.
- Een markdowncel met de tag `remove-cell` staat niet op de pagina (bv. een
  notitie voor de auteur, zoals bovenaan de template).
- Andere `##`-koppen dan `Doelen` en `Vraag n` mogen (bv. `## Instructies`);
  hun tekst staat op de pagina maar niet in het antwoordbestand.

De build geeft een waarschuwing bij een fout tegen dit formaat
(`book/_ext/overhoringen.py`), en `tests/test_overhoringen.py` controleert elke
overhoringnotebook.

## De databank: gadgetshop.db

SQL-vragen gebruiken `/_static/db/gadgetshop.db`, een webshop voor gadgets
(issue #61). De cursuslessen gebruiken die databank **niet**: zo kan een
leerling op een toets geen antwoord uit de cursus overnemen en moet hij het
schema echt lezen (knop **Schema** in de editor). `tests/test_overhoringen.py`
bewaakt dat geen enkele les ernaar verwijst.

| tabel | kolommen | rijen |
|---|---|---|
| brands | brand_id, name, country, founded_year | 25 |
| categories | category_id, name, parent_category_id | 17 |
| products | product_id, name, model_code, brand_id, category_id, price, stock, color, weight_g, battery_hours, release_date, discontinued | 148 |
| customers | customer_id, first_name, last_name, email, phone, city, postal_code, birth_date, join_date, newsletter | 500 |
| orders | order_id, customer_id, order_date, status, payment_method, shipping_method, shipped_date, coupon_code | 4.215 |
| order_items | order_id, product_id, quantity, unit_price, discount_pct | 10.463 |
| reviews | review_id, product_id, customer_id, rating, title, review_date, verified_purchase | 1.425 |

Wat er in zit voor vragen over SQL hoofdstuk 1 en 2: productnamen met Pro,
Mini, Max en Lite (en de valkuilen *Pronto Charger* en *Maxi LED Strip*),
modelcodes met een vaste lengte (`EB-312`), e-mails op verschillende domeinen,
NULL in kleur, batterij, e-mail, telefoon, geboortedatum, verzenddatum,
kortingscode en reviewtitel, datums als tekst `YYYY-MM-DD` (bestellingen van
2023-09-01 tot 2026-08-31), prijzen van € 5 tot € 2.500, kolommen met weinig
waarden (status, betaalmethode, verzendmethode, land) en twee steden in kleine
letters plus een dubbel e-mailadres. Voor latere hoofdstukken: klanten zonder
bestellingen, producten die nooit besteld of beoordeeld werden, merken en een
categorie zonder producten, hoofdcategorieën (`parent_category_id IS NULL`) en
reviews zonder aankoop (`verified_purchase = 0`). Let op: `discount_pct` is een
geheel getal (10 = 10 %).

De databank wordt gemaakt door `scripts/generate_gadgetshop_db.py`
(deterministisch; de volledige beschrijving en de controles staan in het
script). Wie iets wil veranderen, past het script aan en draait het opnieuw;
`tests/test_gadgetshop_db.py` controleert dat de gecommitte databank precies is
wat het script maakt. Controleer een modelquery altijd tegen de databank: ze
moet werken en een zinvol, niet-leeg resultaat geven.

## Het antwoordbestand

"Download mijn antwoorden" onderaan de pagina is de enige indienknop (de balk
"Mijn werk" van de editor staat niet op een overhoringpagina). Het bestand
bevat de titel, de doelen en per vraag de vraagtekst (letterlijk de Markdown uit
de notebook) en het antwoord:

````markdown
# <titel> — antwoorden

- Overhoring: <naam>
- Pagina: /DataBeheer/overhoringen/<naam>/overhoring.html
- Gedownload: 2026-10-01 10:15

## Doelen

- ...

## Vraag 1

<vraagtekst>

**Antwoord:**

```sql
SELECT ...
```

## Vraag 2

<vraagtekst>

**Antwoord:**

> de tekst van de leerling

## Vraag 3

<vraagtekst>

**Antwoord:**

- [ ] optie A
- [x] optie B
````

Een lege open vraag wordt `_(geen antwoord)_`, een meerkeuzevraag zonder keuze
krijgt `_(geen keuze gemaakt)_` onder de opties. De leerling dient het bestand in
via Teams.

Terwijl de leerling werkt, blijft alles in de browser bewaard: de queries per
cel (sleutel `sql:<pad>:<cel>`, zoals in de cursus) en de open en meerkeuze-
antwoorden per vraag (sleutel `overhoring:<pad>:<vraag>`, met de vraag vanaf 0).

## Techniek

- `book/_ext/overhoringen.py`: neemt de overhoringnotebooks weer op in de build
  (`_config.yml` sluit met `external_toc_exclude_missing: true` alles uit wat
  niet in `_toc.yml` staat), markeert ze als orphan, houdt ze uit de
  zoekindex, rendert ze met `book/_ext/templates/overhoring.html` en geeft de
  vragen als JSON mee aan de pagina.
- `book/_static/overhoring.css`, `overhoring.js` en `overhoring-markdown.js`:
  alleen op overhoringpagina's geladen (zie ook
  `book/_ext/sanitize_static_assets.py`).
- De SQL-vragen gebruiken de gewone SQL-editor (`book/_static/sql-editors.js`).
