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
    ├── leerdoelen.md         voor de leraar (geen pagina)
    └── rubriek.csv           voor Teams (geen pagina)
```

- **Welke bestanden een pagina worden:** elke notebook (`*.ipynb`) rechtstreeks
  in `book/overhoringen/<naam>/`. Al de rest (`leerdoelen.md`, `rubriek.csv`,
  notities, dieper geneste mappen) wordt geen pagina.
- **Adres:** `overhoringen/<naam>/overhoring.ipynb` wordt
  `https://yvanvds.github.io/DataBeheer/overhoringen/<naam>/overhoring.html`.
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
| databank | code, tag `sql-db` | het pad naar de databank, bv. `/_static/db/webshop.db` |
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
