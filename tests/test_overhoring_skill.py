"""Tests voor de skill /overhoring (issue #63).

/overhoring maakt per overhoring een map book/overhoringen/<naam>/ met de
pagina (overhoring.ipynb), de leerdoelen met de dekkingstabel (leerdoelen.md)
en de rubriek voor Teams (rubriek.csv). De regels van de skill mogen niet
alleen van het taalmodel afhangen, dus controleert
.claude/skills/overhoring/check_overhoring.py ze, en die tests bewaken dat
script:

- een map volgens de regels is geldig, en de links wijzen naar de site van
  main (/DataBeheer/main/..., zoals de TeachBooks-deploy ze zet);
- elke overtreding wordt opgemerkt: een formaatfout (de parser van de build),
  meer dan 10 vragen, een ontbrekend vraagtype, een vraag met minder dan 2
  leerdoelen, een leerdoel zonder vraag, een kerndoel weg terwijl een
  aanvullend doel blijft, een rubriek met andere doelen dan de getoetste,
  modeloplossingen of notities in de map, ...;
- een modelquery loopt op gadgetshop.db, alleen lezend, en een leeg resultaat
  telt als fout;
- de skill zelf: Claude Code vindt hem, en het voorbeeld van de dekkingstabel
  in SKILL.md volgt de regels die het script afdwingt;
- elke echte overhoringmap in de repo (met een leerdoelen.md) volgt de regels.

    pytest tests/test_overhoring_skill.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude" / "skills" / "overhoring"
SCRIPT = SKILL / "check_overhoring.py"
QUIZ_DIR = ROOT / "book" / "overhoringen"
QUIZ_DB = "/_static/db/gadgetshop.db"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_overhoring", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses zoeken hun module op
    spec.loader.exec_module(module)
    return module


check = load_checker()

LEERDOELEN = """\
# Leerdoelen — SQL 1 en 2

## SQL 1 — Starten met SQL

Bron: `book/chapters/SQL/01_Starten_met_sql.ipynb`

### SQL1.1 — Kolommen opvragen met SELECT … FROM
- Doel: De leerling kan met `SELECT … FROM` gekozen kolommen uit één tabel opvragen.
- Belang: kern
- Waar: 01_Starten_met_sql §3 Je eerste query, oef. 1–5

### SQL1.2 — Rijen filteren met één voorwaarde
- Doel: De leerling kan met `WHERE` en een vergelijking de gevraagde rijen selecteren.
- Belang: kern
- Waar: 01_Starten_met_sql §4 Filteren met WHERE, oef. 1–4

### SQL1.8 — Tekst samenvoegen met ||
- Doel: De leerling kan tekstkolommen samenvoegen met `||`.
- Belang: aanvullend
- Waar: 01_Starten_met_sql §8 Berekende kolommen + aliassen, oef. 1

## SQL 2 — Meer opties voor WHERE

Bron: `book/chapters/SQL/02_Meer_opties_voor_WHERE.ipynb`

### SQL2.1 — Ontbrekende waarden filteren
- Doel: De leerling kan met `IS NULL` en `IS NOT NULL` rijen met een ontbrekende waarde selecteren.
- Belang: kern
- Waar: 02_Meer_opties_voor_WHERE §1 NULL, oef. 1–3

### SQL2.6 — Datums filteren als tekst
- Doel: De leerling kan datums in de vorm `YYYY-MM-DD` filteren met vergelijkingen.
- Belang: aanvullend
- Waar: 02_Meer_opties_voor_WHERE Datum filteren, oef. 1–2

## Dekking

Beoordeel per leerdoel (een rij) over de aangeduide vragen heen.

| Leerdoel | V1 | V2 | V3 |
|---|---|---|---|
| SQL1.1 — Kolommen opvragen met SELECT … FROM | x | | x |
| SQL1.2 — Rijen filteren met één voorwaarde | x | x | |
| SQL1.8 — Tekst samenvoegen met \\|\\| | | x | x |
| SQL2.1 — Ontbrekende waarden filteren | x | x | x |

Niet getoetst: SQL2.6 (aanvullend).
"""

KOPZIN = '"Upload deze .csv in Microsoft Teams als een rubriek voor de beste bewerkingsmogelijkheden."\n'
NIVEAUS = ',"Volledig behaald","100","Deels behaald","50","Niet behaald","0"\n'


def criterium(naam: str, gewicht: int) -> str:
    return f'"{naam}","Juist in alle vragen.",,"Juist in een deel van de vragen.",,"Niet juist.",\n"{gewicht}"\n'


def rubriek(*criteria: tuple[str, int]) -> str:
    kop = f'{KOPZIN}\n"Overhoring SQL 1 en 2","100"\n"Beoordeling per leerdoel, over alle vragen heen."\n""\n{NIVEAUS}'
    return kop + "".join(criterium(naam, gewicht) for naam, gewicht in criteria) + "v.11p\n"


RUBRIEK = rubriek(
    ("SQL1.1 – Kolommen opvragen met SELECT … FROM", 29),
    ("SQL1.2 – Rijen filteren met één voorwaarde", 29),
    ("SQL1.8 – Tekst samenvoegen met ||", 14),
    ("SQL2.1 – Ontbrekende waarden filteren", 28),
)

DOELEN = """\
# Overhoring SQL 1 en 2

Beantwoord de vragen. Klik onderaan op **Download mijn antwoorden** en dien het bestand in via Teams.

## Doelen

- Je kan kolommen opvragen uit een tabel (SQL1.1)
- Je kan rijen kiezen met WHERE en één voorwaarde (SQL1.2)
- Je kan tekst samenvoegen met `||` (SQL1.8)
- Je kan rijen vinden waar een waarde ontbreekt (SQL2.1)"""


def vragen(*types: str) -> list[tuple[str, str, list[str]]]:
    """Per vraag een markdowncel en een antwoordcel van het gegeven type."""
    inhoud = {"sql-live": "-- Schrijf hier je query.", "overhoring-open": "Schrijf hier je uitleg.",
              "overhoring-mc": "`= NULL`\n`IS NULL`\n`= ''`"}
    cellen = []
    for nummer, tag in enumerate(types, start=1):
        cellen.append(("markdown", f"## Vraag {nummer}\n\nVraagtekst {nummer}.", []))
        cellen.append(("code", inhoud[tag], [tag]))
    return cellen


CELLEN = [("code", QUIZ_DB, ["sql-db"]), ("markdown", DOELEN, []),
          *vragen("sql-live", "overhoring-open", "overhoring-mc")]


def notebook(cellen) -> dict:
    return {
        "cells": [
            {"cell_type": soort, "id": f"{nummer:08x}", "metadata": {"tags": tags} if tags else {},
             "source": bron, **({"outputs": [], "execution_count": None} if soort == "code" else {})}
            for nummer, (soort, bron, tags) in enumerate(cellen, start=1)
        ],
        "metadata": {}, "nbformat": 4, "nbformat_minor": 5,
    }


def maak_map(tmp_path: Path, naam: str = "sql-h1-h2", leerdoelen: str = LEERDOELEN,
             cellen=CELLEN, rubriek_csv: str | None = RUBRIEK) -> Path:
    """Een overhoringmap zoals /overhoring ze maakt, in <tmp>/book/overhoringen/<naam>/."""
    pad = tmp_path / "book" / "overhoringen" / naam
    pad.mkdir(parents=True)
    (pad / "overhoring.ipynb").write_bytes(json.dumps(notebook(cellen), ensure_ascii=False, indent=1).encode("utf-8"))
    (pad / "leerdoelen.md").write_bytes(leerdoelen.encode("utf-8"))
    if rubriek_csv is not None:
        (pad / "rubriek.csv").write_bytes(rubriek_csv.encode("utf-8"))
    return pad


def fouten(pad: Path) -> list[str]:
    return check.controleer_map(pad).fouten


# --- wat geldig is -----------------------------------------------------------


def test_folder_following_the_rules_is_valid(tmp_path) -> None:
    r = check.controleer_map(maak_map(tmp_path))
    assert r.fouten == []
    assert [q["type"] for q in r.quiz["questions"]] == ["sql", "open", "mc"]
    assert r.dekking.vragen == [1, 2, 3]
    assert r.dekking.rijen == {"SQL1.1": [1, 3], "SQL1.2": [1, 2], "SQL1.8": [2, 3], "SQL2.1": [1, 2, 3]}
    assert {c: d.belang for c, d in r.doelen.items()} == {
        "SQL1.1": "kern", "SQL1.2": "kern", "SQL1.8": "aanvullend", "SQL2.1": "kern", "SQL2.6": "aanvullend"}
    assert r.opmerkingen == ["niet getoetst (en niet in de rubriek): SQL2.6 (aanvullend)"]


def test_summary_lists_questions_goals_and_the_links(tmp_path) -> None:
    tekst = check.samenvatting(check.controleer_map(maak_map(tmp_path)))
    assert "3 vragen (1 SQL, 1 open, 1 meerkeuze)" in tekst
    assert "4 getoetste leerdoelen (3 kern, 1 aanvullend)" in tekst
    assert "Vraag 2 (open): SQL1.2, SQL1.8, SQL2.1" in tekst
    assert "https://yvanvds.github.io/DataBeheer/main/overhoringen/sql-h1-h2/overhoring.html" in tekst


def test_links_point_to_the_main_site_and_to_main_on_github() -> None:
    """De TeachBooks-deploy zet main in /DataBeheer/main/; zonder /main/ geeft
    Pages een 404 die pas met JavaScript doorverwijst."""
    assert check.links("sql-h1-h2") == {
        "overhoring": "https://yvanvds.github.io/DataBeheer/main/overhoringen/sql-h1-h2/overhoring.html",
        "rubriek_raw": "https://raw.githubusercontent.com/yvanvds/DataBeheer/main/book/overhoringen/sql-h1-h2/rubriek.csv",
        "rubriek_github": "https://github.com/yvanvds/DataBeheer/blob/main/book/overhoringen/sql-h1-h2/rubriek.csv",
    }


def test_link_to_the_quiz_is_its_canonical_address() -> None:
    """De link die de skill geeft, is het canonieke adres dat de build op de
    pagina zet: html_baseurl in book/_config.yml (issue #67)."""
    import yaml

    config = yaml.safe_load((ROOT / "book" / "_config.yml").read_text(encoding="utf-8"))
    baseurl = config["sphinx"]["config"]["html_baseurl"]
    assert check.links("sql-h1-h2")["overhoring"] == f"{baseurl}overhoringen/sql-h1-h2/overhoring.html"


def test_ten_questions_is_allowed(tmp_path) -> None:
    types = ["sql-live", "overhoring-open", "overhoring-mc"] * 3 + ["sql-live"]
    kop = "| Leerdoel | " + " | ".join(f"V{n}" for n in range(1, 11)) + " |\n|---|" + "---|" * 10 + "\n"
    rij = " | x" * 10 + " |"
    dekking = (f"{kop}| SQL1.1 — a{rij}\n| SQL1.2 — b{rij}\n| SQL1.8 — c{rij}\n| SQL2.1 — d{rij}\n")
    leerdoelen = re.sub(r"\| Leerdoel \|.*?(?=\nNiet getoetst)", dekking, LEERDOELEN, flags=re.DOTALL)
    cellen = CELLEN[:2] + vragen(*types)
    assert fouten(maak_map(tmp_path, leerdoelen=leerdoelen, cellen=cellen)) == []


# --- wat de regels van /overhoring breekt ---------------------------------------


def vervang(pad: Path, oud: str, nieuw: str) -> None:
    tekst = pad.read_text(encoding="utf-8")
    assert oud in tekst, f"{oud!r} staat niet in {pad.name}: de test zou niets bewijzen"
    pad.write_bytes(tekst.replace(oud, nieuw, 1).encode("utf-8"))


def rij(code: str) -> str:
    return next(r for r in LEERDOELEN.splitlines() if r.startswith(f"| {code} "))


def cellen_aanpassen(pad: Path, aanpassing) -> None:
    nb = json.loads((pad / "overhoring.ipynb").read_text(encoding="utf-8"))
    aanpassing(nb["cells"])
    (pad / "overhoring.ipynb").write_bytes(json.dumps(nb, ensure_ascii=False).encode("utf-8"))


def extra_vraag(cellen: list) -> None:
    cellen += notebook(vragen("sql-live", "overhoring-open", "overhoring-mc", "sql-live")[-2:])["cells"]
    cellen[-2]["id"], cellen[-1]["id"] = "aaaaaaa1", "aaaaaaa2"
    cellen[-2]["source"] = "## Vraag 4\n\nNog een vraag."


# (naam, aanpassing van de map, stuk tekst uit de verwachte foutmelding)
KAPOT = [
    ("vraag toetst één doel",
     lambda p: [vervang(p / "leerdoelen.md", rij("SQL1.1"), rij("SQL1.1")[:-4] + "   |"),
                vervang(p / "leerdoelen.md", rij("SQL1.8"), rij("SQL1.8")[:-4] + "   |")],
     "vraag 3 toetst 1 leerdoel(en) (SQL2.1)"),
    ("doel zonder vraag",
     lambda p: vervang(p / "leerdoelen.md", rij("SQL1.8"), "| SQL1.8 — Tekst samenvoegen met \\|\\| | | | |"),
     "SQL1.8 wordt door geen enkele vraag getoetst"),
    ("kerndoel weg terwijl een aanvullend doel blijft",
     lambda p: vervang(p / "leerdoelen.md", rij("SQL1.1") + "\n", ""),
     "eerst vallen de aanvullende doelen weg"),
    ("vraagtype ontbreekt",
     lambda p: cellen_aanpassen(p, lambda c: c[-1]["metadata"].update(tags=["overhoring-open"])),
     "type meerkeuze"),
    ("dekking mist een vraag",
     lambda p: cellen_aanpassen(p, extra_vraag),
     "de overhoring heeft 4 vragen (V1 tot V4)"),
    ("onbekend leerdoel in de dekking",
     lambda p: vervang(p / "leerdoelen.md", "| SQL2.1 — Ontbrekende", "| SQL9.9 — Ontbrekende"),
     "SQL9.9 staat in de dekkingstabel, maar is geen leerdoel"),
    ("geen dekkingstabel",
     lambda p: vervang(p / "leerdoelen.md", "## Dekking", "## Selectie"),
     "geen sectie '## Dekking'"),
    ("dekking met iets anders dan x",
     lambda p: vervang(p / "leerdoelen.md", "| SQL1.1 — Kolommen opvragen met SELECT … FROM | x |",
                       "| SQL1.1 — Kolommen opvragen met SELECT … FROM | ja |"),
     "gebruik x of laat leeg"),
    ("pijp in een titel niet ontsnapt",
     lambda p: vervang(p / "leerdoelen.md", "met \\|\\| |", "met || |"),
     "cellen in plaats van 4"),
    ("###-kop in de dekking",
     lambda p: vervang(p / "leerdoelen.md", "Niet getoetst:", "### SQL2.6 — Datums\n\nNiet getoetst:"),
     "geen ###-kop in '## Dekking'"),
    ("belang ontbreekt",
     lambda p: vervang(p / "leerdoelen.md", "- Belang: aanvullend\n- Waar: 02", "- Belang: hoog\n- Waar: 02"),
     "SQL2.6 heeft geen '- Belang: kern'"),
    ("rubriek met een doel dat niet getoetst wordt",
     lambda p: (p / "rubriek.csv").write_bytes(rubriek(
         ("SQL1.1 – a", 25), ("SQL1.2 – b", 25), ("SQL1.8 – c", 10), ("SQL2.1 – d", 25), ("SQL2.6 – e", 15),
     ).encode("utf-8")),
     "SQL2.6 staat in de rubriek maar wordt niet getoetst"),
    ("rubriek mist een getoetst doel",
     lambda p: (p / "rubriek.csv").write_bytes(rubriek(("SQL1.1 – a", 40), ("SQL1.2 – b", 40), ("SQL1.8 – c", 20))
                                               .encode("utf-8")),
     "geen criterium voor SQL2.1"),
    ("rubriek niet in Teams-formaat",
     lambda p: vervang(p / "rubriek.csv", '"28"', '"27"'),
     "rubriek.csv: de gewichten zijn samen 99"),
    ("rubriek ontbreekt",
     lambda p: (p / "rubriek.csv").unlink(),
     "rubriek.csv ontbreekt"),
    ("doelen bovenaan tellen niet",
     lambda p: cellen_aanpassen(p, lambda c: c[1].update(source=DOELEN.rsplit("\n", 1)[0])),
     "'## Doelen' heeft 3 punt(en); de overhoring toetst 4"),
    ("notitie met remove-cell",
     lambda p: cellen_aanpassen(p, lambda c: c.insert(0, {
         "cell_type": "markdown", "id": "bbbbbbbb", "metadata": {"tags": ["remove-cell"]},
         "source": "Voor de auteur: vraag 1 is SELECT ..."})),
     "remove-cell"),
    ("modeloplossingen in de map",
     lambda p: (p / "oplossingen.md").write_bytes(b"SELECT name FROM products;\n"),
     "oplossingen.md hoort niet in de map"),
    ("formaatfout volgens de parser van de build",
     lambda p: cellen_aanpassen(p, lambda c: c[3].update(source="")),
     "lege antwoordcel"),
    ("databank uit de lessen",
     lambda p: cellen_aanpassen(p, lambda c: c[0].update(source="/_static/db/webshop.db")),
     "gebruiken gadgetshop.db"),
    ("dubbele cel-id",
     lambda p: cellen_aanpassen(p, lambda c: c[3].update(id=c[2]["id"])),
     "cel-id's komen meer dan eens voor"),
]


@pytest.mark.parametrize("aanpassing,verwacht", [k[1:] for k in KAPOT], ids=[k[0] for k in KAPOT])
def test_broken_folder_is_rejected(tmp_path, aanpassing, verwacht: str) -> None:
    pad = maak_map(tmp_path)
    aanpassing(pad)
    gevonden = fouten(pad)
    assert gevonden, "het script aanvaardt een map die de regels breekt"
    assert any(verwacht in f for f in gevonden), gevonden


def test_more_than_ten_questions_is_rejected(tmp_path) -> None:
    types = ["sql-live", "overhoring-open", "overhoring-mc"] * 3 + ["sql-live", "sql-live"]
    gevonden = fouten(maak_map(tmp_path, cellen=CELLEN[:2] + vragen(*types)))
    assert any("11 vragen, hoogstens 10" in f for f in gevonden), gevonden


def test_folder_must_be_a_slug_directly_in_book_overhoringen(tmp_path) -> None:
    assert any("geen slug" in f for f in fouten(maak_map(tmp_path, naam="SQL_H1")))
    elders = tmp_path / "elders" / "sql-h1-h2"
    elders.mkdir(parents=True)
    for bestand in maak_map(tmp_path).iterdir():
        (elders / bestand.name).write_bytes(bestand.read_bytes())
    assert any("niet rechtstreeks in book/overhoringen/" in f for f in fouten(elders))


# --- modelquery's op gadgetshop.db -------------------------------------------


def test_model_query_runs_on_the_quiz_database() -> None:
    gelukt, uitvoer = check.toon_query("SELECT name, country FROM brands ORDER BY name")
    assert gelukt, uitvoer
    assert uitvoer.startswith("OK: 25 rij(en), kolommen: name, country")
    assert "... en nog 20" in uitvoer


@pytest.mark.parametrize(
    ("sql", "verwacht"),
    [
        pytest.param("SELECT name FROM products WHERE price < 0", "leeg resultaat", id="leeg"),
        pytest.param("SELECT naam FROM products", "no such column", id="fout"),
        pytest.param("SELECT name FROM brands; SELECT name FROM products", "one statement", id="twee-queries"),
    ],
)
def test_empty_or_failing_model_query_is_rejected(sql: str, verwacht: str) -> None:
    gelukt, uitvoer = check.toon_query(sql)
    assert not gelukt
    assert verwacht in uitvoer


def test_model_query_cannot_change_the_database() -> None:
    voor = hashlib.sha256(check.DB.read_bytes()).hexdigest()
    gelukt, uitvoer = check.toon_query("DELETE FROM brands")
    assert not gelukt
    assert "readonly" in uitvoer
    assert hashlib.sha256(check.DB.read_bytes()).hexdigest() == voor


# --- het script als opdracht, zoals de skill het gebruikt --------------------


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8", cwd=ROOT, check=False
    )


def test_cli_accepts_a_valid_folder_and_prints_the_links(tmp_path) -> None:
    proc = run(str(maak_map(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert "OK:" in proc.stdout
    assert "https://raw.githubusercontent.com/yvanvds/DataBeheer/main/book/overhoringen/sql-h1-h2/rubriek.csv" in proc.stdout
    assert "Vraag 1 (SQL): SQL1.1, SQL1.2, SQL2.1" in proc.stdout  # UTF-8, ook doorgesluisd op Windows


def test_cli_fails_and_lists_the_errors(tmp_path) -> None:
    pad = maak_map(tmp_path)
    (pad / "oplossingen.md").write_bytes(b"SELECT 1;\n")
    proc = run(str(pad))
    assert proc.returncode == 1
    assert "oplossingen.md hoort niet in de map" in proc.stderr


def test_cli_runs_model_queries() -> None:
    assert run("--query", "SELECT name FROM brands").returncode == 0
    proc = run("--query", "SELECT name FROM brands", "--query", "SELECT name FROM brands WHERE 1 = 0")
    assert proc.returncode == 1
    assert "Query 2: FOUT: leeg resultaat" in proc.stderr


def test_cli_without_arguments_is_a_usage_error() -> None:
    assert run().returncode == 2


# --- de skill ------------------------------------------------------------------


def skill_text() -> str:
    return (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_skill_has_frontmatter_claude_code_can_list() -> None:
    m = re.match(r"---\n(.*?)\n---\n", skill_text(), re.DOTALL)
    assert m, "SKILL.md begint niet met YAML-frontmatter tussen ---"
    velden = dict(regel.split(":", 1) for regel in m.group(1).splitlines())
    assert velden["name"].strip() == "overhoring"
    assert len(velden["description"].strip()) > 40


def test_skill_names_its_checks_the_no_publish_mode_and_the_real_address() -> None:
    tekst = skill_text()
    for nodig in ("check_overhoring.py", "check_rubriek.py", "teachbooks build book", "--niet-publiceren",
                  "gh run watch", "https://yvanvds.github.io/DataBeheer/main/overhoringen/<naam>/overhoring.html"):
        assert nodig in tekst, nodig


def test_coverage_example_in_the_skill_follows_the_rules() -> None:
    """Het voorbeeld van `## Dekking` in SKILL.md is het contract met het script."""
    m = re.search(r"````markdown\n(## Dekking\n.*?)````", skill_text(), re.DOTALL)
    assert m, "het voorbeeld van de dekkingstabel staat niet in een ````markdown-blok"
    gevonden: list[str] = []
    regels = list(enumerate(m.group(1).splitlines()[1:], start=2))
    dekking = check.lees_dekking(regels, gevonden)
    assert gevonden == []
    assert dekking.vragen == list(range(1, len(dekking.vragen) + 1))
    assert len(dekking.rijen) >= 3
    assert all(dekking.rijen.values()), dekking.rijen
    for vraag in dekking.vragen:
        assert sum(vraag in v for v in dekking.rijen.values()) >= check.MIN_DOELEN_PER_VRAAG, vraag


def test_every_quiz_folder_in_the_repo_follows_the_rules() -> None:
    """Een map van /overhoring (met leerdoelen.md) blijft geldig, ook na een
    aanpassing met de hand. De template is geen overhoring van /overhoring."""
    problems = []
    for pad in sorted(QUIZ_DIR.iterdir()):
        if pad.is_dir() and (pad / "leerdoelen.md").is_file():
            problems += [f"{pad.relative_to(ROOT).as_posix()}: {f}" for f in fouten(pad)]
    assert not problems, "\n".join(problems)
