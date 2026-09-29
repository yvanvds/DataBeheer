"""Controleert een overhoringmap van /overhoring (issue #63).

Een overhoringmap `book/overhoringen/<naam>/` bevat de overhoring
(`overhoring.ipynb`), de leerdoelen met de dekkingstabel (`leerdoelen.md`) en
de rubriek voor Teams (`rubriek.csv`). Dit script controleert de regels van
/overhoring, zodat ze niet alleen van het taalmodel afhangen:

- de notebook volgt het formaat van de overhoringpagina's: de parser
  `parse_quiz` uit `book/_ext/overhoringen.py` (dezelfde als in de build);
- hoogstens 10 vragen, en de drie vraagtypes (SQL-editor, open, meerkeuze)
  komen alle drie voor; SQL-vragen laden gadgetshop.db;
- de tabel `## Dekking` in `leerdoelen.md` (vraag x leerdoel) heeft een kolom
  per vraag; elke vraag toetst minstens 2 leerdoelen, elk leerdoel in de tabel
  wordt door minstens één vraag getoetst, en een kerndoel valt pas weg als er
  geen aanvullend doel meer getoetst wordt;
- de rubriek heeft precies één criterium per getoetst leerdoel (en is geldig
  volgens `.claude/skills/rubriek/check_rubriek.py`);
- `## Doelen` bovenaan de overhoring heeft één punt per getoetst leerdoel;
- de map bevat niets anders (geen modeloplossingen: repo en site zijn publiek)
  en de notebook geen `remove-cell`-cellen (die staan niet op de site, maar wel
  in de publieke repo).

Daarnaast voert het een modelquery uit op gadgetshop.db (alleen lezen), om te
zien dat ze werkt en een niet-leeg resultaat geeft. De query komt niet in een
bestand: modeloplossingen horen niet in de repo.

    python .claude/skills/overhoring/check_overhoring.py book/overhoringen/<naam>
    python .claude/skills/overhoring/check_overhoring.py --query "SELECT name FROM brands"

Draai het met de Python van .venv: de parser importeert Sphinx. Exitcode 0 als
alles klopt, 1 bij een fout (of een lege of mislukte query), 2 bij een fout in
de aanroep.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BOOK = ROOT / "book"
EXTENSIE = BOOK / "_ext" / "overhoringen.py"
RUBRIEK_SCRIPT = ROOT / ".claude" / "skills" / "rubriek" / "check_rubriek.py"
#: De databank van de overhoringen (#61), zoals de pagina ze laadt en op schijf.
QUIZ_DB = "/_static/db/gadgetshop.db"
DB = BOOK / QUIZ_DB.lstrip("/")

MAX_VRAGEN = 10
MIN_DOELEN_PER_VRAAG = 2
VRAAGTYPES = {"sql": "SQL", "open": "open", "mc": "meerkeuze"}
PAGINA = "overhoring"
BESTANDEN = ("leerdoelen.md", "rubriek.csv")
#: Zoveel rijen van een query tonen we.
TOON_RIJEN = 5

#: De site van main. De TeachBooks-deploy zet elke branch in een eigen map
#: (main in /main/); het adres zonder /main/ geeft een 404 die in de browser
#: pas met JavaScript doorverwijst.
SITE = "https://yvanvds.github.io/DataBeheer/main"
REPO = "yvanvds/DataBeheer"
BRANCH = "main"

NAAM = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LEERDOEL = re.compile(r"^### (?P<code>[A-Z]+\d+\.\d+) — (?P<titel>\S.*?)\s*$")
BELANG = re.compile(r"^- Belang:\s*(?P<belang>\S+)\s*$")
KOP = re.compile(r"^(?P<niveau>#{1,2}) (?P<titel>\S.*?)\s*$")
CODE = re.compile(r"^(?P<code>[A-Z]+\d+\.\d+)(?![\d.])")
VRAAGKOLOM = re.compile(r"^V(?P<nummer>\d+)$")
SCHEIDING = re.compile(r"^:?-{3,}:?$")
PIJP = re.compile(r"(?<!\\)\|")
OPSOMMING = re.compile(r"^[-*] \S")


class Aanroepfout(Exception):
    """Iets in de omgeving ontbreekt (exitcode 2)."""


def _laad(naam: str, pad: Path):
    geladen = sys.modules.get(naam)
    if geladen is not None and Path(getattr(geladen, "__file__", "") or "").resolve() == pad.resolve():
        return geladen  # bv. al geïmporteerd door de tests
    spec = importlib.util.spec_from_file_location(naam, pad)
    module = importlib.util.module_from_spec(spec)
    sys.modules[naam] = module  # dataclasses zoeken hun module op
    spec.loader.exec_module(module)
    return module


def laad_parser():
    """`book/_ext/overhoringen.py`, de extensie met `parse_quiz`."""
    try:
        return _laad("overhoringen", EXTENSIE)
    except ImportError as fout:
        raise Aanroepfout(
            f"{EXTENSIE.relative_to(ROOT)} kan niet geladen worden ({fout}); "
            "draai dit script met de Python van .venv (.venv/Scripts/python op Windows)"
        ) from fout


def laad_rubriekcontrole():
    return _laad("check_rubriek", RUBRIEK_SCRIPT)


# --- leerdoelen.md -------------------------------------------------------------


@dataclass
class Leerdoel:
    code: str
    titel: str
    belang: str | None = None


@dataclass
class Dekking:
    vragen: list[int]
    #: code -> de vragen die het doel toetsen, in de volgorde van de tabel
    rijen: dict[str, list[int]] = field(default_factory=dict)


def _cellen(regel: str) -> list[str]:
    regel = regel.strip()
    if regel.startswith("|"):
        regel = regel[1:]
    if regel.endswith("|") and not regel.endswith("\\|"):
        regel = regel[:-1]
    return [cel.strip() for cel in PIJP.split(regel)]


def lees_dekking(regels: list[str], fouten: list[str]) -> Dekking | None:
    """De eerste tabel in de sectie `## Dekking`: | Leerdoel | V1 | V2 | ... |."""
    tabel = [(nr, r) for nr, r in regels if r.lstrip().startswith("|")]
    if not tabel:
        fouten.append("leerdoelen.md: de sectie '## Dekking' bevat geen tabel")
        return None
    (kopnr, kop), *rest = tabel
    koppen = _cellen(kop)
    vragen = []
    for cel in koppen[1:]:
        m = VRAAGKOLOM.match(cel)
        if not m:
            fouten.append(f"leerdoelen.md regel {kopnr}: kolom {cel!r} in de dekkingstabel is geen vraag (V1, V2, ...)")
            return None
        vragen.append(int(m["nummer"]))
    dekking = Dekking(vragen)
    for nr, regel in rest:
        cellen = _cellen(regel)
        if all(SCHEIDING.match(c) for c in cellen):
            continue
        if len(cellen) != len(koppen):
            fouten.append(
                f"leerdoelen.md regel {nr}: {len(cellen)} cellen in plaats van {len(koppen)} "
                "(schrijf een | in een titel als \\|)"
            )
            continue
        m = CODE.match(cellen[0])
        if not m:
            fouten.append(f"leerdoelen.md regel {nr}: de rij begint niet met de code van een leerdoel: {cellen[0]!r}")
            continue
        code = m["code"]
        if code in dekking.rijen:
            fouten.append(f"leerdoelen.md regel {nr}: {code} staat twee keer in de dekkingstabel")
            continue
        getoetst = []
        for vraag, cel in zip(vragen, cellen[1:]):
            if cel.lower() == "x":
                getoetst.append(vraag)
            elif cel:
                fouten.append(f"leerdoelen.md regel {nr}: {code} bij V{vraag} is {cel!r}; gebruik x of laat leeg")
        dekking.rijen[code] = getoetst
    return dekking


def lees_leerdoelen(tekst: str) -> tuple[dict[str, Leerdoel], Dekking | None, list[str]]:
    """De leerdoelen (`### <code> — <titel>` met `- Belang:`) en de dekkingstabel."""
    fouten: list[str] = []
    doelen: dict[str, Leerdoel] = {}
    huidig: Leerdoel | None = None
    dekking_regels: list[tuple[int, str]] | None = None
    in_dekking = False
    for nr, regel in enumerate(tekst.splitlines(), start=1):
        kop = KOP.match(regel)
        if kop:
            huidig = None
            in_dekking = kop["niveau"] == "##" and kop["titel"] == "Dekking"
            if in_dekking:
                if dekking_regels is not None:
                    fouten.append(f"leerdoelen.md regel {nr}: een tweede sectie '## Dekking'")
                dekking_regels = []
            continue
        if in_dekking:
            if regel.startswith("### "):
                fouten.append(f"leerdoelen.md regel {nr}: geen ###-kop in '## Dekking' (/rubriek zou er een leerdoel in zien)")
            dekking_regels.append((nr, regel))
            continue
        doel = LEERDOEL.match(regel)
        if doel:
            if doel["code"] in doelen:
                fouten.append(f"leerdoelen.md regel {nr}: leerdoel {doel['code']} staat er twee keer")
            huidig = Leerdoel(doel["code"], doel["titel"])
            doelen[huidig.code] = huidig
            continue
        belang = BELANG.match(regel)
        if belang and huidig is not None and huidig.belang is None:
            huidig.belang = belang["belang"]
    if not doelen:
        fouten.append("leerdoelen.md: geen leerdoelen ('### <code> — <titel>')")
    for doel in doelen.values():
        if doel.belang not in ("kern", "aanvullend"):
            fouten.append(f"leerdoelen.md: {doel.code} heeft geen '- Belang: kern' of '- Belang: aanvullend'")
    if dekking_regels is None:
        fouten.append("leerdoelen.md: geen sectie '## Dekking' met de tabel vraag x leerdoel")
        return doelen, None, fouten
    return doelen, lees_dekking(dekking_regels, fouten), fouten


# --- de hele map ---------------------------------------------------------------


@dataclass
class Resultaat:
    map: Path
    pagina: str
    fouten: list[str] = field(default_factory=list)
    opmerkingen: list[str] = field(default_factory=list)
    quiz: dict | None = None
    doelen: dict[str, Leerdoel] = field(default_factory=dict)
    dekking: Dekking | None = None


def _codecellen(notebook: dict, tag: str) -> list[str]:
    return [
        "".join(c.get("source", "")).strip()
        for c in notebook.get("cells", [])
        if c.get("cell_type") == "code" and tag in c.get("metadata", {}).get("tags", [])
    ]


def controleer_notebook(notebook: dict, parser, r: Resultaat) -> None:
    quiz, fouten = parser.parse_quiz(notebook)
    r.quiz = quiz
    naam = f"{r.pagina}.ipynb"
    r.fouten += [f"{naam}: {fout}" for fout in fouten]
    vragen = quiz["questions"]
    if len(vragen) > MAX_VRAGEN:
        r.fouten.append(f"{naam}: {len(vragen)} vragen, hoogstens {MAX_VRAGEN}")
    types = {v["type"] for v in vragen}
    for soort, label in VRAAGTYPES.items():
        if soort not in types:
            r.fouten.append(f"{naam}: geen enkele vraag van het type {label}; alle drie de vraagtypes komen voor")
    if "sql" in types and _codecellen(notebook, parser.SEED_TAG) != [QUIZ_DB]:
        r.fouten.append(f"{naam}: de SQL-vragen gebruiken gadgetshop.db: één codecel met tag sql-db en inhoud {QUIZ_DB}")
    ids = [c["id"] for c in notebook.get("cells", []) if "id" in c]
    dubbel = sorted({i for i in ids if ids.count(i) > 1})
    if dubbel:
        r.fouten.append(f"{naam}: cel-id's komen meer dan eens voor: {', '.join(dubbel)}")
    for nummer, cel in enumerate(notebook.get("cells", []), start=1):
        if parser.REMOVE_TAGS.intersection(cel.get("metadata", {}).get("tags", [])):
            r.fouten.append(
                f"{naam}: cel {nummer} heeft de tag remove-cell; die staat niet op de site maar wel in de "
                "publieke repo: laat ze weg (bv. de notitie uit de template)"
            )


def controleer_dekking(r: Resultaat) -> None:
    dekking, doelen = r.dekking, r.doelen
    aantal = len(r.quiz["questions"]) if r.quiz else 0
    verwacht = list(range(1, aantal + 1))
    if dekking.vragen != verwacht:
        kolommen = ", ".join(f"V{n}" for n in dekking.vragen) or "geen"
        r.fouten.append(
            f"leerdoelen.md: de dekkingstabel heeft de kolommen {kolommen}; de overhoring heeft "
            f"{aantal} vragen (V1 tot V{aantal})"
        )
    if not dekking.rijen:
        r.fouten.append("leerdoelen.md: de dekkingstabel heeft geen leerdoelen")
    for code, vragen in dekking.rijen.items():
        if code not in doelen:
            r.fouten.append(f"leerdoelen.md: {code} staat in de dekkingstabel, maar is geen leerdoel ('### {code} — ...')")
        if not vragen:
            r.fouten.append(
                f"leerdoelen.md: {code} wordt door geen enkele vraag getoetst; voeg het toe aan een vraag, "
                "of haal het uit de tabel en uit de rubriek"
            )
    for vraag in dekking.vragen:
        getoetst = [code for code, vragen in dekking.rijen.items() if vraag in vragen]
        if len(getoetst) < MIN_DOELEN_PER_VRAAG:
            r.fouten.append(
                f"leerdoelen.md: vraag {vraag} toetst {len(getoetst)} leerdoel(en) "
                f"({', '.join(getoetst) or 'geen'}); elke vraag toetst er minstens {MIN_DOELEN_PER_VRAAG}"
            )
    kern_weg = [c for c, d in doelen.items() if d.belang == "kern" and c not in dekking.rijen]
    aanvullend = [c for c, d in doelen.items() if d.belang == "aanvullend" and c in dekking.rijen]
    if kern_weg and aanvullend:
        r.fouten.append(
            f"leerdoelen.md: kerndoel(en) {', '.join(kern_weg)} niet getoetst terwijl aanvullend(e) "
            f"doel(en) {', '.join(aanvullend)} wel getoetst worden; eerst vallen de aanvullende doelen weg"
        )
    weg = [f"{c} ({d.belang})" for c, d in doelen.items() if c not in dekking.rijen]
    if weg:
        r.opmerkingen.append(f"niet getoetst (en niet in de rubriek): {', '.join(weg)}")


def controleer_doelen_bovenaan(r: Resultaat) -> None:
    punten = [regel for regel in r.quiz["doelen"].splitlines() if OPSOMMING.match(regel)]
    getoetst = len(r.dekking.rijen)
    if len(punten) != getoetst:
        r.fouten.append(
            f"{r.pagina}.ipynb: '## Doelen' heeft {len(punten)} punt(en); de overhoring toetst {getoetst} "
            "leerdoelen: één punt per getoetst leerdoel, in leerlingentaal"
        )


def controleer_rubriek(pad: Path, r: Resultaat) -> None:
    check = laad_rubriekcontrole()
    rubriek, fouten = check.controleer(pad.read_bytes())
    r.fouten += [f"rubriek.csv: {fout}" for fout in fouten]
    if rubriek is None or r.dekking is None:
        return
    codes = []
    for criterium in rubriek.criteria:
        m = CODE.match(criterium.naam)
        if not m:
            r.fouten.append(f"rubriek.csv: criterium {criterium.naam!r} begint niet met de code van een leerdoel")
        else:
            codes.append(m["code"])
    getoetst = list(r.dekking.rijen)
    te_veel = [c for c in codes if c not in getoetst]
    ontbreekt = [c for c in getoetst if c not in codes]
    if te_veel:
        r.fouten.append(
            f"rubriek.csv: {', '.join(te_veel)} staat in de rubriek maar wordt niet getoetst "
            "(de rubriek bevat alleen de doelen uit de dekkingstabel)"
        )
    if ontbreekt:
        r.fouten.append(f"rubriek.csv: geen criterium voor {', '.join(ontbreekt)}, dat wel getoetst wordt")


def controleer_inhoud_map(map_: Path, r: Resultaat) -> None:
    for pad in sorted(map_.iterdir()):
        if pad.name.startswith(".") or pad.name == f"{r.pagina}.ipynb" or pad.name in BESTANDEN:
            continue
        if pad.suffix == ".ipynb" and pad.is_file():
            r.opmerkingen.append(f"{pad.name} wordt ook een pagina (controleer ze apart met --pagina {pad.stem})")
            continue
        r.fouten.append(
            f"{pad.name} hoort niet in de map: alleen {r.pagina}.ipynb, {' en '.join(BESTANDEN)} "
            "(geen modeloplossingen of notities: de repo en de site zijn publiek)"
        )


def controleer_map(map_: Path, pagina: str = PAGINA) -> Resultaat:
    map_ = Path(map_)
    r = Resultaat(map_, pagina)
    parser = laad_parser()
    if not map_.is_dir():
        r.fouten.append(f"{map_} is geen map")
        return r
    echt = map_.resolve()
    if echt.parent.name != parser.QUIZ_ROOT or echt.parent.parent.name != "book":
        r.fouten.append(f"{map_} staat niet rechtstreeks in book/{parser.QUIZ_ROOT}/: dan wordt het geen pagina")
    if not NAAM.match(echt.name):
        r.fouten.append(f"de naam {echt.name!r} is geen slug (kleine letters, cijfers en koppeltekens, bv. sql-h1-h2)")
    elif not parser.is_quiz_source(f"{parser.QUIZ_ROOT}/{echt.name}/{pagina}.ipynb"):
        r.fouten.append(f"{pagina}.ipynb in {echt.name}/ wordt geen overhoringpagina")

    notebook_pad = map_ / f"{pagina}.ipynb"
    if notebook_pad.is_file():
        try:
            notebook = json.loads(notebook_pad.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as fout:
            r.fouten.append(f"{notebook_pad.name} is geen geldige notebook (JSON, UTF-8): {fout}")
        else:
            controleer_notebook(notebook, parser, r)
    else:
        r.fouten.append(f"{notebook_pad.name} ontbreekt")

    leerdoelen_pad = map_ / "leerdoelen.md"
    if leerdoelen_pad.is_file():
        r.doelen, r.dekking, fouten = lees_leerdoelen(leerdoelen_pad.read_text(encoding="utf-8"))
        r.fouten += fouten
    else:
        r.fouten.append("leerdoelen.md ontbreekt")
    if r.dekking is not None and r.quiz is not None:
        controleer_dekking(r)
        controleer_doelen_bovenaan(r)

    rubriek_pad = map_ / "rubriek.csv"
    if rubriek_pad.is_file():
        controleer_rubriek(rubriek_pad, r)
    else:
        r.fouten.append("rubriek.csv ontbreekt")

    controleer_inhoud_map(map_, r)
    return r


# --- links en samenvatting -----------------------------------------------------


def links(naam: str, pagina: str = PAGINA) -> dict[str, str]:
    """De adressen zodra de map op main staat en de deploy klaar is."""
    rubriek = f"book/overhoringen/{naam}/rubriek.csv"
    return {
        "overhoring": f"{SITE}/overhoringen/{naam}/{pagina}.html",
        "rubriek_raw": f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{rubriek}",
        "rubriek_github": f"https://github.com/{REPO}/blob/{BRANCH}/{rubriek}",
    }


def samenvatting(r: Resultaat) -> str:
    vragen = r.quiz["questions"]
    per_type = ", ".join(
        f"{sum(v['type'] == soort for v in vragen)} {label}" for soort, label in VRAAGTYPES.items()
    )
    kern = sum(r.doelen[c].belang == "kern" for c in r.dekking.rijen)
    regels = [
        f"  Titel: {r.quiz['title']}",
        f"  {len(vragen)} vragen ({per_type})",
        f"  {len(r.dekking.rijen)} getoetste leerdoelen ({kern} kern, {len(r.dekking.rijen) - kern} aanvullend)",
    ]
    for vraag in vragen:
        codes = [c for c, v in r.dekking.rijen.items() if vraag["number"] in v]
        regels.append(f"    Vraag {vraag['number']} ({VRAAGTYPES.get(vraag['type'], '?')}): {', '.join(codes)}")
    regels += [f"  Let op: {o}" for o in r.opmerkingen]
    adres = links(r.map.resolve().name, r.pagina)
    regels += [
        "  Links (zodra de map op main staat en de deploy klaar is):",
        f"    Overhoring:         {adres['overhoring']}",
        f"    Rubriek (download): {adres['rubriek_raw']}",
        f"    Rubriek (GitHub):   {adres['rubriek_github']}",
        f"    Rubriek (lokaal):   {(r.map / 'rubriek.csv').resolve()}",
    ]
    return "\n".join(regels)


# --- modelquery's --------------------------------------------------------------


def voer_uit(sql: str, db: Path = DB) -> tuple[list[str], list[tuple]]:
    """Voer één query uit op de databank, alleen lezen. Geeft (kolommen, rijen)."""
    verbinding = sqlite3.connect(f"{Path(db).resolve().as_uri()}?mode=ro", uri=True)
    try:
        cursor = verbinding.execute(sql)
        if cursor.description is None:
            raise sqlite3.OperationalError("de query geeft geen resultaat (geen SELECT?)")
        return [kolom[0] for kolom in cursor.description], cursor.fetchall()
    finally:
        verbinding.close()


def toon_query(sql: str, db: Path = DB) -> tuple[bool, str]:
    try:
        kolommen, rijen = voer_uit(sql, db)
    except sqlite3.Error as fout:
        return False, f"FOUT: {fout}"
    if not rijen:
        return False, f"FOUT: leeg resultaat (kolommen: {', '.join(kolommen)}); een SQL-vraag moet een niet-leeg resultaat geven"
    regels = [f"OK: {len(rijen)} rij(en), kolommen: {', '.join(kolommen)}"]
    regels += [f"  {rij}" for rij in rijen[:TOON_RIJEN]]
    if len(rijen) > TOON_RIJEN:
        regels.append(f"  ... en nog {len(rijen) - TOON_RIJEN}")
    return True, "\n".join(regels)


def main(argv: list[str] | None = None) -> int:
    # Een doorgesluisde uitvoer is op Windows anders cp1252 (zie check_rubriek.py).
    for stroom in (sys.stdout, sys.stderr):
        try:
            stroom.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="Controleert een overhoringmap van /overhoring (issue #63).")
    parser.add_argument("map", nargs="?", type=Path, help="book/overhoringen/<naam>")
    parser.add_argument("--pagina", default=PAGINA, help=f"de notebook in de map, zonder .ipynb (standaard {PAGINA})")
    parser.add_argument(
        "--query", action="append", default=[], metavar="SQL",
        help="voer een modelquery uit op gadgetshop.db (alleen lezen); mag meermaals",
    )
    args = parser.parse_args(argv)
    if args.map is None and not args.query:
        parser.error("geef een overhoringmap, een --query, of beide")

    code = 0
    for nummer, sql in enumerate(args.query, start=1):
        gelukt, uitvoer = toon_query(sql)
        print(f"Query {nummer}: {uitvoer}", file=sys.stdout if gelukt else sys.stderr)
        code = code if gelukt else 1
    if args.map is not None:
        try:
            r = controleer_map(args.map, args.pagina)
        except Aanroepfout as fout:
            print(f"FOUT: {fout}", file=sys.stderr)
            return 2
        if r.fouten:
            print(f"FOUT: {args.map} volgt de regels van /overhoring niet:", file=sys.stderr)
            for melding in r.fouten:
                print(f"  - {melding}", file=sys.stderr)
            return 1
        print(f"OK: {args.map}")
        print(samenvatting(r))
    return code


if __name__ == "__main__":
    sys.exit(main())
