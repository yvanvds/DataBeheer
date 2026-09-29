# Databeheer

Cursus informatica voor 5BW (Bedrijfswetenschappen, derde graad) over relationele
databanken en data-analyse, door yvan vander sanden. De cursus heeft drie delen:

1. **Databases bevragen met SQL**: gegevens opvragen met SQL, rechtstreeks in de
   browser, op een webshopcasus en de AdventureWorks-database.
2. **Big data**: Eurostat-datasets analyseren en visualiseren met Power BI, in
   onderzoeksopdrachten en met kritisch gebruik van AI.
3. **Databases ontwerpen met ERD's**: normalisatie, constraints, foreign keys en
   ERD-schema's; de leerlingen ontwerpen en bouwen zelf een databank.

Het boek staat op **https://yvanvds.github.io/DataBeheer/main/**. Het leerplan
waarop de cursus steunt, staat in `docs/leerplan.md`.

## Zelf bouwen en testen

Het boek staat in `book/`: de inhoudstafel in `book/_toc.yml`, de configuratie in
`book/_config.yml`.

```
pip install -r requirements-dev.txt
playwright install chromium    # eenmalig, voor de e2e-tests in de browser
teachbooks build book          # de site komt in book/_build/html
pytest tests
```

De tests lezen de gebouwde site: bouw dus eerst. Zonder build, Node, Playwright
of Chromium slaan tests zichzelf over; in CI (`.github/workflows/tests.yml`)
draait daarom `TESTS_FAIL_ON_SKIP=1 pytest tests`, waarin een overgeslagen test
als fout telt.

De SQL-editor gebruikt een gebundelde CodeMirror in `book/_static/codemirror/`.
Pas je `scripts/codemirror-entry.mjs` of de CodeMirror-pakketten aan, bouw de
bundel dan opnieuw:

```
npm install
npm run build:editor
```

Een push die `book/` of `requirements.txt` verandert, publiceert het boek via
`.github/workflows/call-deploy-book.yml`: main op het adres hierboven, elke andere
branch in een eigen map.

## Overhoringen

Naast de cursus publiceert de site losse overhoringpagina's uit
`book/overhoringen/`, die niet in de inhoudstafel staan. Hoe ze werken en hoe je
er een maakt, staat in `book/overhoringen/README.md`. In Claude Code stellen de
skills `/leerdoelen`, `/rubriek` en `/overhoring` (in `.claude/skills/`) de
leerdoelen, een rubriek voor Teams en de overhoring zelf op.

## Licentie en bronvermelding

De cursus valt onder [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
(zie `LICENSE`): je mag hem hergebruiken en aanpassen, als je de bron vermeldt.
De citatiegegevens staan in `CITATION.cff`.

Het boek is gebouwd met [TeachBooks](https://teachbooks.io/) en vertrekt van de
[TeachBooks-template](https://github.com/TeachBooks/template).
