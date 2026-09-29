"""Controleert een rubriek-CSV voor Microsoft Teams (issue #62).

Teams laadt een rubriek uit een .csv in het formaat dat het zelf exporteert
("v.11p": een rubriek met punten per niveau). Dit script controleert dat
formaat, zodat de juistheid van `rubriek.csv` niet alleen van het taalmodel
afhangt. Alleen de standaardbibliotheek, Python 3.10+.

    python .claude/skills/rubriek/check_rubriek.py rubriek.csv
    python .claude/skills/rubriek/check_rubriek.py --alleen-teams voorbeeld-teams.csv

Het formaat (zie ook voorbeeld-teams.csv, het voorbeeld van de leraar):

    "Upload deze .csv in Microsoft Teams als een rubriek voor de beste bewerkingsmogelijkheden."
    <lege regel>
    "<titel>","100"
    "<beschrijving>"
    ""
    ,"<niveau 1>","<punten>","<niveau 2>","<punten>",...
    "<criterium>","<beschrijving niveau 1>",,"<beschrijving niveau 2>",,...,
    "<gewicht>"
    ...                              (per criterium die twee regels)
    v.11p

- Elk veld staat tussen dubbele aanhalingstekens; een " in de tekst wordt "".
  Uitzonderingen: de lege eerste kolom van de niveauregel, de lege
  puntenkolommen in een criteriumregel (daarom eindigt die op een komma) en de
  slotregel v.11p.
- Niveaus van hoog naar laag, punten als geheel getal.
- Gewichten (procent) samen precies 100.
- UTF-8 zonder BOM, LF-regeleinden en een regeleinde na v.11p: zo exporteert
  Teams zelf (byte voor byte vergeleken in github.com/agrimuitobom/rubric,
  HANDOFF.md). De eerste import in Teams blijft de echte test.

Zonder optie controleert het script ook de afspraken van /rubriek: precies de
drie niveaus "Volledig behaald" (100), "Deels behaald" (50) en "Niet behaald"
(0), en gewichten als geheel getal. Met --alleen-teams enkel het Teams-formaat:
elk aantal niveaus (minstens twee), gewichten met hoogstens twee decimalen
(Teams zelf exporteert bv. 33.33), en een instructiezin in een andere taal.

Exitcode 0 als alles klopt, 1 bij een fout in een bestand, 2 bij een fout in
de aanroep.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

#: Regel 1 in een Nederlandstalig Teams.
KOPZIN = "Upload deze .csv in Microsoft Teams als een rubriek voor de beste bewerkingsmogelijkheden."
#: De tweede kolom van de titelregel.
TITELPUNTEN = "100"
#: De slotregel, zonder aanhalingstekens.
SLOTREGEL = "v.11p"
#: De niveaus van /rubriek, het hoogste eerst.
NIVEAUS_RUBRIEK = (("Volledig behaald", 100), ("Deels behaald", 50), ("Niet behaald", 0))

BOM = b"\xef\xbb\xbf"
GEHEEL = re.compile(r"\d+")
DECIMAAL = re.compile(r"\d+(\.\d{1,2})?")


class CsvFout(Exception):
    """Een fout in de CSV-syntaxis zelf; verder lezen heeft dan geen zin."""

    def __init__(self, regel: int, melding: str) -> None:
        super().__init__(f"regel {regel}: {melding}")


@dataclass
class Veld:
    tekst: str
    quoted: bool


@dataclass
class Record:
    regel: int
    velden: list[Veld]

    def is_leeg(self) -> bool:
        """Een lege regel: niets, ook geen ""."""
        return len(self.velden) == 1 and not self.velden[0].quoted and self.velden[0].tekst == ""


@dataclass
class Criterium:
    naam: str
    beschrijvingen: list[str]
    gewicht: Decimal


@dataclass
class Rubriek:
    titel: str = ""
    beschrijving: str = ""
    niveaus: list[tuple[str, int]] = field(default_factory=list)
    criteria: list[Criterium] = field(default_factory=list)


def lees_records(tekst: str) -> list[Record]:
    """Splitst de tekst in records en onthoudt per veld of het tussen aanhalingstekens stond.

    Een regeleinde binnen aanhalingstekens hoort bij het veld (Teams bewaart
    zo een regeleinde in een cel).
    """
    records: list[Record] = []
    n = len(tekst)
    i = 0
    regel = 1
    while i < n:
        begin = regel
        velden: list[Veld] = []
        while True:
            if i < n and tekst[i] == '"':
                open_regel = regel
                i += 1
                stukken: list[str] = []
                while True:
                    if i >= n:
                        raise CsvFout(open_regel, "een aanhalingsteken wordt nooit gesloten")
                    c = tekst[i]
                    if c == '"':
                        if i + 1 < n and tekst[i + 1] == '"':
                            stukken.append('"')
                            i += 2
                            continue
                        i += 1
                        break
                    if c == "\n":
                        regel += 1
                    stukken.append(c)
                    i += 1
                velden.append(Veld("".join(stukken), True))
                if i < n and tekst[i] not in ",\n":
                    raise CsvFout(
                        regel,
                        f"na een afsluitend aanhalingsteken volgt {tekst[i]!r} in plaats van een komma "
                        'of het einde van de regel; een " in de tekst schrijf je als ""',
                    )
            else:
                j = i
                while j < n and tekst[j] not in ",\n":
                    j += 1
                ruw = tekst[i:j]
                if '"' in ruw:
                    raise CsvFout(
                        regel,
                        f"aanhalingsteken midden in een veld: {ruw!r}; zet het hele veld tussen "
                        'aanhalingstekens en schrijf een " in de tekst als ""',
                    )
                velden.append(Veld(ruw, False))
                i = j
            if i < n and tekst[i] == ",":
                i += 1
                continue
            break
        records.append(Record(begin, velden))
        if i < n:  # het regeleinde
            i += 1
            regel += 1
    return records


def _toon(record: Record) -> str:
    delen = [f'"{v.tekst}"' if v.quoted else v.tekst for v in record.velden]
    tekst = ",".join(delen)
    return tekst if len(tekst) <= 70 else tekst[:67] + "..."


def controleer(data: bytes, alleen_teams: bool = False) -> tuple[Rubriek | None, list[str]]:
    """Controleert de bytes van een rubriek-CSV.

    Geeft de gelezen rubriek en een lijst foutmeldingen terug; zonder fouten is
    de lijst leeg. Bij een fout in codering of CSV-syntaxis is de rubriek None.
    """
    fouten: list[str] = []

    if data.startswith(BOM):
        fouten.append(
            "het bestand begint met een BOM; bewaar het als UTF-8 zonder BOM, zoals Teams zelf "
            "exporteert (Excel voegt er een toe: open en bewaar de rubriek niet in Excel)"
        )
        data = data[len(BOM):]
    try:
        tekst = data.decode("utf-8")
    except UnicodeDecodeError as fout:
        regel = data[: fout.start].count(b"\n") + 1
        fouten.append(f"regel {regel}: geen geldige UTF-8 (bewaar het bestand als UTF-8, zonder BOM)")
        return None, fouten
    if "\r" in tekst:
        fouten.append("het bestand gebruikt CRLF- of CR-regeleinden; gebruik LF, zoals Teams zelf exporteert")
        tekst = tekst.replace("\r\n", "\n").replace("\r", "\n")
    if not tekst:
        fouten.append("het bestand is leeg")
        return None, fouten
    if not tekst.endswith("\n"):
        fouten.append(f"na {SLOTREGEL} hoort nog een regeleinde, zoals in de export van Teams")
    try:
        records = lees_records(tekst)
    except CsvFout as fout:
        fouten.append(str(fout))
        return None, fouten

    rubriek = Rubriek()

    def fout(record: Record, melding: str) -> None:
        fouten.append(f"regel {record.regel}: {melding} (nu: {_toon(record)})")

    if len(records) < 9:
        fouten.append(
            f"te weinig regels ({len(records)}): een rubriek heeft minstens de kop (5 regels), "
            f"de niveauregel, één criterium met zijn gewicht en {SLOTREGEL}"
        )
        return rubriek, fouten

    # Regel 1 en 2: de vaste instructiezin en een lege regel.
    kop = records[0]
    if len(kop.velden) != 1 or not kop.velden[0].quoted or not kop.velden[0].tekst.strip():
        fout(kop, "de eerste regel is de instructiezin van Teams, als één veld tussen aanhalingstekens")
    elif not alleen_teams and kop.velden[0].tekst != KOPZIN:
        fout(kop, f'de eerste regel is precies "{KOPZIN}"')
    if not records[1].is_leeg():
        fout(records[1], "na de instructiezin volgt een lege regel")

    # De titel, de beschrijving en "".
    titel = records[2]
    if len(titel.velden) != 2 or not all(v.quoted for v in titel.velden):
        fout(titel, f'de titelregel is "<titel>","{TITELPUNTEN}"')
    else:
        rubriek.titel = titel.velden[0].tekst
        if not rubriek.titel.strip():
            fout(titel, "de titel is leeg")
        if titel.velden[1].tekst != TITELPUNTEN:
            fout(titel, f'de tweede kolom van de titelregel is "{TITELPUNTEN}"')
    beschrijving = records[3]
    if len(beschrijving.velden) != 1 or not beschrijving.velden[0].quoted:
        fout(beschrijving, 'na de titel volgt de beschrijving als één veld: "<beschrijving>"')
    else:
        rubriek.beschrijving = beschrijving.velden[0].tekst
    leeg = records[4]
    if len(leeg.velden) != 1 or not leeg.velden[0].quoted or leeg.velden[0].tekst:
        fout(leeg, 'na de beschrijving volgt een regel met alleen ""')

    # De niveauregel: ,"<naam>","<punten>",...
    niveauregel = records[5]
    velden = niveauregel.velden
    if not velden or velden[0].quoted or velden[0].tekst:
        fout(niveauregel, 'de niveauregel begint met een lege kolom: ,"<niveau>","<punten>",...')
    paren = velden[1:]
    if len(paren) < 4 or len(paren) % 2:
        fout(niveauregel, "de niveauregel heeft na de lege kolom paren naam en punten, minstens twee niveaus")
    elif not all(v.quoted for v in paren):
        fout(niveauregel, "elke naam en elk puntental in de niveauregel staat tussen aanhalingstekens")
    else:
        for naam, punten in zip(paren[::2], paren[1::2]):
            if not naam.tekst.strip():
                fout(niveauregel, "een niveau heeft geen naam")
            if not GEHEEL.fullmatch(punten.tekst):
                fout(niveauregel, f'de punten van niveau "{naam.tekst}" zijn geen geheel getal: "{punten.tekst}"')
                continue
            rubriek.niveaus.append((naam.tekst, int(punten.tekst)))
        punten_lijst = [p for _, p in rubriek.niveaus]
        if len(punten_lijst) == len(paren) // 2 and any(a <= b for a, b in pairwise(punten_lijst)):
            fout(niveauregel, "de niveaus staan van hoog naar laag, met telkens minder punten")
        namen = [n for n, _ in rubriek.niveaus]
        if len(set(namen)) != len(namen):
            fout(niveauregel, "twee niveaus hebben dezelfde naam")
    if not alleen_teams and tuple(rubriek.niveaus) != NIVEAUS_RUBRIEK:
        verwacht = ",".join(f'"{naam}","{punten}"' for naam, punten in NIVEAUS_RUBRIEK)
        fout(niveauregel, f"een rubriek van /rubriek heeft precies drie niveaus: ,{verwacht}")
    aantal_niveaus = len(paren) // 2 if len(paren) >= 4 and len(paren) % 2 == 0 else None

    # De slotregel.
    slot = records[-1]
    if len(slot.velden) == 1 and slot.velden[0].tekst == SLOTREGEL and not slot.velden[0].quoted:
        body = records[6:-1]
    else:
        slotindex = next(
            (i for i, r in enumerate(records) if len(r.velden) == 1 and r.velden[0].tekst == SLOTREGEL), None
        )
        if slotindex is None:
            fout(slot, f"de laatste regel is {SLOTREGEL}, zonder aanhalingstekens")
            body = records[6:]
        elif records[slotindex].velden[0].quoted:
            fout(records[slotindex], f"de slotregel {SLOTREGEL} hoort zonder aanhalingstekens")
            body = records[6:slotindex]
        else:
            fout(records[slotindex + 1], f"na {SLOTREGEL} volgt niets meer (ook geen lege regel)")
            body = records[6:slotindex]

    # Per criterium twee regels: de criteriumregel en het gewicht.
    if not body:
        fouten.append("de rubriek heeft geen criteria")
    gewichtpatroon = DECIMAAL if alleen_teams else GEHEEL
    gewichten_gelezen = True  # anders heeft de som geen zin

    def is_gewichtregel(record: Record) -> bool:
        return len(record.velden) == 1 and record.velden[0].quoted and bool(DECIMAAL.fullmatch(record.velden[0].tekst))

    k = 0
    while k < len(body):
        crit = body[k]
        if is_gewichtregel(crit):
            fout(crit, "hier hoort een criteriumregel, maar dit is een gewicht: twee gewichten na elkaar?")
            gewichten_gelezen = False
            k += 1
            continue
        velden = crit.velden
        naam = velden[0].tekst if velden[0].quoted else ""
        if aantal_niveaus is not None and len(velden) != 1 + 2 * aantal_niveaus:
            fout(
                crit,
                f"een criteriumregel heeft {1 + 2 * aantal_niveaus} velden: de naam en per niveau een "
                f"beschrijving plus een lege puntenkolom, dus een komma na elke beschrijving; nu {len(velden)}",
            )
        elif not velden[0].quoted or not velden[0].tekst.strip():
            fout(crit, "een criteriumregel begint met de naam van het criterium, tussen aanhalingstekens")
        else:
            for pos, veld in enumerate(velden[1:], start=1):
                if pos % 2:  # een beschrijving
                    if not veld.quoted:
                        fout(crit, f"de beschrijving van niveau {(pos + 1) // 2} staat niet tussen aanhalingstekens")
                    elif not veld.tekst.strip():
                        fout(crit, f'"{naam}": de beschrijving van niveau {(pos + 1) // 2} is leeg')
                elif veld.quoted or veld.tekst:  # een puntenkolom
                    fout(
                        crit,
                        f'"{naam}": de puntenkolom na niveau {pos // 2} blijft helemaal leeg, ook zonder "" '
                        "(Teams haalt de punten uit de niveauregel)",
                    )

        gewichtregel = body[k + 1] if k + 1 < len(body) else None
        if gewichtregel is None or (not is_gewichtregel(gewichtregel) and len(gewichtregel.velden) > 1):
            # Geen gewicht, maar meteen het volgende criterium (of het einde).
            fout(crit, f'na criterium "{naam}" ontbreekt de regel met het gewicht, bv. "20"')
            gewichten_gelezen = False
            k += 1
            continue
        k += 2
        g = gewichtregel.velden
        if len(g) != 1 or not g[0].quoted:
            fout(gewichtregel, f'na criterium "{naam}" volgt een regel met alleen het gewicht, tussen aanhalingstekens: "20"')
            gewichten_gelezen = False
            continue
        if not gewichtpatroon.fullmatch(g[0].tekst):
            soort = "een getal (hoogstens twee decimalen)" if alleen_teams else "een geheel getal"
            fout(gewichtregel, f'het gewicht van "{naam}" moet {soort} zijn: "{g[0].tekst}"')
            gewichten_gelezen = False
            continue
        gewicht = Decimal(g[0].tekst)
        if gewicht <= 0:
            fout(gewichtregel, f'het gewicht van "{naam}" moet groter dan 0 zijn')
        rubriek.criteria.append(Criterium(naam, [v.tekst for v in velden[1::2]], gewicht))

    namen = [c.naam for c in rubriek.criteria]
    dubbel = sorted({n for n in namen if n and namen.count(n) > 1})
    if dubbel:
        fouten.append("twee criteria hebben dezelfde naam: " + ", ".join(f'"{n}"' for n in dubbel))
    if rubriek.criteria and gewichten_gelezen:
        totaal = sum(c.gewicht for c in rubriek.criteria)
        if totaal != 100:
            gewichten = " + ".join(str(c.gewicht) for c in rubriek.criteria)
            fouten.append(f"de gewichten zijn samen {totaal}, niet 100: {gewichten}")
    return rubriek, fouten


def samenvatting(rubriek: Rubriek) -> str:
    niveaus = ", ".join(f"{naam} ({punten})" for naam, punten in rubriek.niveaus)
    regels = [
        f"  Titel: {rubriek.titel}",
        f"  Niveaus: {niveaus}",
        f"  {len(rubriek.criteria)} criteria, gewichten samen {sum(c.gewicht for c in rubriek.criteria)}:",
    ]
    regels += [f"    {c.gewicht!s:>6}  {c.naam}" for c in rubriek.criteria]
    return "\n".join(regels)


def main(argv: list[str] | None = None) -> int:
    # Een doorgesluisde uitvoer (Claude Code, Git Bash) is op Windows anders
    # cp1252 en wordt als UTF-8 gelezen: dan wordt een – in een criterium een �.
    for stroom in (sys.stdout, sys.stderr):
        try:
            stroom.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        description="Controleert een rubriek-CSV voor Microsoft Teams (issue #62).",
    )
    parser.add_argument("bestanden", nargs="+", type=Path, metavar="rubriek.csv")
    parser.add_argument(
        "--alleen-teams",
        action="store_true",
        help="alleen het Teams-formaat controleren, niet de afspraken van /rubriek "
        "(drie niveaus 100/50/0, gewichten als geheel getal)",
    )
    args = parser.parse_args(argv)

    code = 0
    for pad in args.bestanden:
        try:
            data = pad.read_bytes()
        except OSError as fout:
            print(f"FOUT: {pad} kan niet gelezen worden: {fout}", file=sys.stderr)
            code = 1
            continue
        rubriek, fouten = controleer(data, alleen_teams=args.alleen_teams)
        if fouten:
            print(f"FOUT: {pad} voldoet niet aan het formaat:", file=sys.stderr)
            for melding in fouten:
                print(f"  - {melding}", file=sys.stderr)
            code = 1
        else:
            print(f"OK: {pad}")
            print(samenvatting(rubriek))
    return code


if __name__ == "__main__":
    sys.exit(main())
