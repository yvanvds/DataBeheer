"""Tests voor de skills /leerdoelen en /rubriek (issue #62).

/rubriek schrijft een rubriek als CSV die in Microsoft Teams geladen wordt.
Het formaat is streng (zie het voorbeeld van de leraar,
.claude/skills/rubriek/voorbeeld-teams.csv) en een fout merk je pas bij de
import. Daarom controleert .claude/skills/rubriek/check_rubriek.py het bestand,
en die tests bewaken dat script:

- het voorbeeld van de leraar is geldig Teams-formaat, en is ongewijzigd;
- een rubriek volgens de afspraken van /rubriek (drie niveaus, gewichten samen
  100) is geldig;
- elke afwijking die Teams kan doen struikelen, wordt opgemerkt: BOM, CRLF,
  puntkomma's van Excel, aanhalingstekens, lege of gevulde puntenkolommen,
  gewichten, de slotregel, ...;
- de skills zelf: Claude Code vindt ze (frontmatter), /rubriek beschrijft
  dezelfde niveauregel als het script afdwingt, en het voorbeeld van het
  leerdoelenformaat in /leerdoelen volgt de regels die /rubriek en
  /overhoring (#63) gebruiken.

    pytest tests/test_rubriek.py
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".claude" / "skills"
SCRIPT = SKILLS / "rubriek" / "check_rubriek.py"
VOORBEELD = SKILLS / "rubriek" / "voorbeeld-teams.csv"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_rubriek", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses zoeken hun module op
    spec.loader.exec_module(module)
    return module


check = load_checker()

#: Een kleine, geldige rubriek volgens de afspraken van /rubriek.
GELDIG = (
    '"Upload deze .csv in Microsoft Teams als een rubriek voor de beste bewerkingsmogelijkheden."\n'
    "\n"
    '"Overhoring SQL 1","100"\n'
    '"Beoordeling per leerdoel. Kerndoelen wegen zwaarder dan aanvullende doelen."\n'
    '""\n'
    ',"Volledig behaald","100","Deels behaald","50","Niet behaald","0"\n'
    '"SQL1.3 – Rijen filteren met WHERE","Filtert juist, ook met tekst tussen \'enkele\' '
    'aanhalingstekens.",,"Filtert, maar vergeet haakjes bij AND en OR.",,"Geen of een verkeerde WHERE.",\n'
    '"60"\n'
    '"SQL1.8 – Tekst samenvoegen met ||","Voegt kolommen samen met || en een spatie ertussen.",,'
    '"Voegt samen, maar zonder spatie of met +.",,"Geen samengevoegde kolom.",\n'
    '"40"\n'
    "v.11p\n"
)


def fouten(tekst: str | bytes, alleen_teams: bool = False) -> list[str]:
    data = tekst.encode("utf-8") if isinstance(tekst, str) else tekst
    return check.controleer(data, alleen_teams=alleen_teams)[1]


# --- wat geldig is -----------------------------------------------------------


def test_example_of_the_teacher_is_valid_teams_format() -> None:
    rubriek, gevonden = check.controleer(VOORBEELD.read_bytes(), alleen_teams=True)
    assert gevonden == []
    assert rubriek.titel == "Debat graffiti"
    assert rubriek.niveaus == [("Sterk", 100), ("Voldoende", 66), ("Zwak", 33), ("Onvoldoende", 0)]
    assert [int(c.gewicht) for c in rubriek.criteria] == [25, 10, 10, 20, 20, 15]
    assert all(len(c.beschrijvingen) == 4 for c in rubriek.criteria)
    assert rubriek.criteria[0].naam == "Argumentatiefiche – argumenten en onderbouwing"


def test_example_is_stored_like_teams_exports() -> None:
    """UTF-8 zonder BOM, LF, een regeleinde na v.11p (issue #62, #56)."""
    data = VOORBEELD.read_bytes()
    assert not data.startswith(check.BOM)
    assert b"\r" not in data
    assert data.endswith(b"\nv.11p\n")
    assert "é" in data.decode("utf-8")


def test_example_has_four_levels_so_the_rubriek_conventions_reject_it() -> None:
    """Zonder --alleen-teams gelden de drie niveaus van /rubriek: alleen die fout."""
    gevonden = fouten(VOORBEELD.read_bytes())
    assert len(gevonden) == 1
    assert "precies drie niveaus" in gevonden[0]


def test_rubric_following_the_conventions_is_valid() -> None:
    rubriek, gevonden = check.controleer(GELDIG.encode("utf-8"))
    assert gevonden == []
    assert rubriek.niveaus == list(check.NIVEAUS_RUBRIEK)
    assert [c.naam for c in rubriek.criteria] == [
        "SQL1.3 – Rijen filteren met WHERE",
        "SQL1.8 – Tekst samenvoegen met ||",
    ]
    assert rubriek.criteria[1].beschrijvingen[1] == "Voegt samen, maar zonder spatie of met +."


def test_doubled_quotes_and_line_breaks_inside_a_field_are_valid() -> None:
    """Een " in de tekst wordt "" (zoals in CSV hoort); Teams bewaart een regeleinde in een cel."""
    tekst = GELDIG.replace("Geen of een verkeerde WHERE.", 'Schrijft ""WHERE city = Antwerpen"",\nzonder aanhalingstekens.')
    rubriek, gevonden = check.controleer(tekst.encode("utf-8"))
    assert gevonden == []
    assert rubriek.criteria[0].beschrijvingen[2] == 'Schrijft "WHERE city = Antwerpen",\nzonder aanhalingstekens.'


def test_decimal_weights_only_in_teams_mode() -> None:
    """Teams exporteert zelf bv. 33.33; /rubriek gebruikt gehele getallen."""
    tekst = GELDIG.replace('"60"', '"59.5"').replace('"40"', '"40.5"')
    assert fouten(tekst, alleen_teams=True) == []
    assert any("geheel getal" in f for f in fouten(tekst))


# --- wat Teams kan doen struikelen -------------------------------------------

# (naam, aanpassing van GELDIG, stuk tekst uit de verwachte foutmelding)
KAPOT = [
    ("bom", lambda t: "﻿" + t, "BOM"),
    ("crlf", lambda t: t.replace("\n", "\r\n"), "CRLF"),
    ("geen slot-regeleinde", lambda t: t[:-1], "regeleinde"),
    ("excel-puntkomma", lambda t: t.replace('","', '";"').replace('",,"', '";;"'), "aanhalingsteken"),
    ("andere kopzin", lambda t: t.replace("bewerkingsmogelijkheden", "mogelijkheden"), "eerste regel"),
    ("geen lege regel", lambda t: t.replace('mogelijkheden."\n\n', 'mogelijkheden."\n'), "lege regel"),
    ("titel zonder 100", lambda t: t.replace('"Overhoring SQL 1","100"', '"Overhoring SQL 1"'), "titelregel"),
    ("titel met 20", lambda t: t.replace('"Overhoring SQL 1","100"', '"Overhoring SQL 1","20"'), '"100"'),
    ("geen lege-tekstregel", lambda t: t.replace('doelen."\n""\n', 'doelen."\n'), 'alleen ""'),
    ("niveauregel zonder lege kolom", lambda t: t.replace(',"Volledig', '"Volledig'), "lege kolom"),
    ("niveaus van laag naar hoog", lambda t: t.replace(
        ',"Volledig behaald","100","Deels behaald","50","Niet behaald","0"',
        ',"Niet behaald","0","Deels behaald","50","Volledig behaald","100"'), "van hoog naar laag"),
    ("andere niveaunamen", lambda t: t.replace("Deels behaald", "Gedeeltelijk"), "precies drie niveaus"),
    ("punten als kommagetal", lambda t: t.replace('"50"', '"50.5"'), "geheel getal"),
    ("puntenkolom met lege tekst", lambda t: t.replace('.",,"Filtert', '.","","Filtert'), "puntenkolom"),
    ("puntenkolom met punten", lambda t: t.replace('.",,"Filtert', '.",50,"Filtert'), "puntenkolom"),
    ("zonder komma op het einde", lambda t: t.replace('verkeerde WHERE.",\n', 'verkeerde WHERE."\n'), "7 velden"),
    ("lege beschrijving", lambda t: t.replace('"Geen samengevoegde kolom."', '""'), "is leeg"),
    ("criterium zonder naam", lambda t: t.replace('"SQL1.8 – Tekst samenvoegen met ||"', '""'), "naam van het criterium"),
    ("beschrijving zonder aanhalingstekens", lambda t: t.replace('"Geen samengevoegde kolom."', "Geen samengevoegde kolom."), "aanhalingstekens"),
    ("aanhalingsteken niet verdubbeld", lambda t: t.replace("Geen samengevoegde kolom.", 'Geen "kolom".'), "aanhalingsteken"),
    ("aanhalingsteken niet gesloten", lambda t: t.replace('"40"\n', '"40\n'), "nooit gesloten"),
    ("gewichtregel ontbreekt", lambda t: t.replace('"60"\n', ""), "ontbreekt de regel met het gewicht"),
    ("gewicht twee keer", lambda t: t.replace('"60"\n', '"60"\n"60"\n'), "twee gewichten"),
    ("gewicht zonder aanhalingstekens", lambda t: t.replace('"60"\n', "60\n"), "tussen aanhalingstekens"),
    ("gewicht in woorden", lambda t: t.replace('"60"\n', '"zestig"\n'), "geheel getal"),
    ("gewichten samen 99", lambda t: t.replace('"40"', '"39"'), "samen 99"),
    ("gewichten samen 110", lambda t: t.replace('"40"', '"50"'), "samen 110"),
    ("gewicht 0", lambda t: t.replace('"60"', '"100"').replace('"40"', '"0"'), "groter dan 0"),
    ("dubbel criterium", lambda t: t.replace("SQL1.8 – Tekst samenvoegen met ||", "SQL1.3 – Rijen filteren met WHERE"), "dezelfde naam"),
    ("slotregel tussen aanhalingstekens", lambda t: t.replace("v.11p\n", '"v.11p"\n'), "zonder aanhalingstekens"),
    ("slotregel ontbreekt", lambda t: t.replace("v.11p\n", ""), "v.11p"),
    ("lege regel na de slotregel", lambda t: t + "\n", "niets meer"),
    ("geen criteria", lambda t: t.split('"SQL1.3')[0] + "v.11p\n", "te weinig regels"),
]


@pytest.mark.parametrize("aanpassing,verwacht", [k[1:] for k in KAPOT], ids=[k[0] for k in KAPOT])
def test_broken_variant_is_rejected(aanpassing, verwacht: str) -> None:
    tekst = aanpassing(GELDIG)
    assert tekst != GELDIG, "de aanpassing verandert niets: de test zou niets bewijzen"
    gevonden = fouten(tekst)
    assert gevonden, "het script aanvaardt een kapotte rubriek"
    assert any(verwacht in f for f in gevonden), gevonden


def test_invalid_utf8_is_rejected() -> None:
    """Een rubriek die in Excel als 'CSV (gescheiden door lijstscheidingsteken)' bewaard werd, is cp1252."""
    gevonden = fouten(GELDIG.replace("–", "-").encode("cp1252").replace(b"Overhoring", b"Overh\xe9ring"))
    assert any("UTF-8" in f for f in gevonden), gevonden


def test_errors_name_the_line() -> None:
    gevonden = fouten(GELDIG.replace('"40"', '"veertig"'))
    assert any(f.startswith("regel 10:") for f in gevonden), gevonden


# --- het script als opdracht, zoals de skill het gebruikt --------------------


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8", cwd=ROOT, check=False
    )


def test_cli_accepts_a_valid_rubric_and_summarises_it(tmp_path) -> None:
    pad = tmp_path / "rubriek.csv"
    pad.write_bytes(GELDIG.encode("utf-8"))
    proc = run(str(pad))
    assert proc.returncode == 0, proc.stderr
    assert "OK:" in proc.stdout
    assert "2 criteria, gewichten samen 100" in proc.stdout
    assert "SQL1.3 – Rijen filteren met WHERE" in proc.stdout  # UTF-8, ook doorgesluisd op Windows


def test_cli_fails_and_lists_the_errors(tmp_path) -> None:
    pad = tmp_path / "rubriek.csv"
    pad.write_bytes(GELDIG.replace('"40"', '"30"').encode("utf-8"))
    proc = run(str(pad))
    assert proc.returncode == 1
    assert "samen 90" in proc.stderr


def test_cli_teams_mode_accepts_the_example() -> None:
    assert run("--alleen-teams", str(VOORBEELD)).returncode == 0
    assert run(str(VOORBEELD)).returncode == 1


# --- de skills ----------------------------------------------------------------


def frontmatter(pad: Path) -> dict[str, str]:
    tekst = pad.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", tekst, re.DOTALL)
    assert m, f"{pad} begint niet met YAML-frontmatter tussen ---"
    velden = {}
    for regel in m.group(1).splitlines():
        sleutel, _, waarde = regel.partition(":")
        velden[sleutel.strip()] = waarde.strip()
    return velden


@pytest.mark.parametrize("naam", ["leerdoelen", "rubriek"])
def test_skill_has_frontmatter_claude_code_can_list(naam: str) -> None:
    velden = frontmatter(SKILLS / naam / "SKILL.md")
    assert velden.get("name") == naam
    assert len(velden.get("description", "")) > 40


def test_rubriek_skill_describes_what_the_script_enforces() -> None:
    tekst = (SKILLS / "rubriek" / "SKILL.md").read_text(encoding="utf-8")
    niveauregel = "," + ",".join(f'"{naam}","{punten}"' for naam, punten in check.NIVEAUS_RUBRIEK)
    assert niveauregel in tekst
    assert check.KOPZIN in tekst
    assert "check_rubriek.py" in tekst


LEERDOEL = re.compile(r"^### (?P<code>[A-Z]+\d+\.\d+) — (?P<titel>\S.*)$")
VELDEN = ["Doel", "Belang", "Waar"]


def test_leerdoelen_example_follows_the_documented_format() -> None:
    """Het voorbeeld in /leerdoelen is het contract voor /rubriek en /overhoring (#63)."""
    tekst = (SKILLS / "leerdoelen" / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"````markdown\n(.*?)````", tekst, re.DOTALL)
    assert m, "het voorbeeld van leerdoelen.md staat niet in een ````markdown-blok"
    regels = m.group(1).splitlines()
    assert regels[0].startswith("# Leerdoelen — ")
    koppen = [i for i, r in enumerate(regels) if r.startswith("### ")]
    assert len(koppen) >= 3
    codes = []
    for i in koppen:
        kop = LEERDOEL.match(regels[i])
        assert kop, f"kop van een leerdoel volgt het formaat niet: {regels[i]!r}"
        codes.append(kop["code"])
        velden = {}
        for r in regels[i + 1 : i + 6]:
            veld = re.match(r"^- (\w+): (\S.*)$", r)
            if veld:
                velden[veld[1]] = veld[2]
        assert all(v in velden for v in VELDEN), (regels[i], velden)
        assert velden["Doel"].startswith("De leerling kan ")
        assert velden["Belang"] in ("kern", "aanvullend")
    assert len(codes) == len(set(codes))
