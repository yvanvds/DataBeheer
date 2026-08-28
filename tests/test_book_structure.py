"""Structuurtests voor het boek: deelvolgorde, kruisverwijzingen en prev/next-flow (issue #36),
de plaats van de DB Browser-installatie (issue #33) en de verankering van de
onderzoekscompetenties in het Big Data-deel (issue #37).

Draaien met de projectomgeving (PyYAML zit in de teachbooks-installatie):

    .venv/Scripts/python.exe tests/test_book_structure.py

Het bestand is ook door pytest te verzamelen. De HTML-tests lezen de gebouwde
site in book/_build/html en worden overgeslagen zolang die ontbreekt; bouw
eerst met `teachbooks build book`.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "book"
HTML = BOOK / "_build" / "html"

# Volgorde van de delen sinds issue #36: eerst bevragen, dan analyseren
# (Power BI / Big Data), pas daarna zelf databases ontwerpen (ERD).
EXPECTED_PARTS = [
    "Databases Bevragen met SQL",
    "Big Data",
    "Databases Ontwerpen met ERD's",
]

# Grenspagina's tussen de delen, in leesvolgorde (paden relatief aan book/).
LAST_SQL = "chapters/SQL/06_Herhaling"
FIRST_BIG_DATA = "chapters/BIG_DATA/01_Inleiding"
LAST_BIG_DATA = "chapters/BIG_DATA/08_Eindopdracht"
FIRST_ERD = "chapters/ERD/01_Inleiding_tot_ERD"
LAST_ERD = "chapters/ERD/06_client_server"

# Formuleringen die de oude volgorde (Big Data als slot van het jaar) of een
# nummering van de delen veronderstellen. Beide zijn sinds de wissel fout.
STALE_PHRASES = [
    r"\bdeel [23]\b",
    r"\b(tweede|derde|laatste) deel\b",
    r"\bhet (school)?jaar af\b",
    r"\blaatste opdracht van het (school)?jaar\b",
    r"\bhele (school)?jaar door\b",
    r"\bafsluiting van het (school)?jaar\b",
]

# Woordenschat uit het ERD-deel die een Big Data-pagina niet mag veronderstellen.
ERD_VOCABULARY = [
    r"\bERD\b",
    r"normalis",  # normalisatie, genormaliseerd, ...
    r"\bforeign key",
    r"referenti[eë]le integriteit",
]

# Vooruitwijzingen die het ERD-deel niet mag maken: er komt geen deel meer na.
ERD_FORWARD_REFERENCES = [
    r"Power ?BI",
    r"Eurostat",
    r"\bbig data\b",
    r"\b(volgende|derde|laatste) deel\b",
    r"\bstraks in\b",
]

# Installatie (issue #33): het SQL-deel is volledig online. Deze formuleringen
# horen bij een lokale DB Browser-werkwijze en mogen daar niet meer voorkomen.
INSTALL_PHRASES = [
    r"DB ?Browser",
    r"sqlitebrowser",
    r"\binstalleer\b",  # "Download en installeer …"
    r"\binstallatie",
    r"\bgeïnstalleerd",
    r"Execute SQL",  # tabblad van DB Browser
    r"Open Database",
    r"\.sqlite\b",
]

# De enige downloadlink voor DB Browser for SQLite. Hij staat op de eerste
# pagina van het ERD-deel en nergens eerder in leesvolgorde.
DB_BROWSER_DOWNLOAD = r"https://sqlitebrowser\.org/dl/"
DB_BROWSER_NAME = r"DB Browser for SQLite"

# Onderzoekscompetenties (issue #37): één pagina in het Big Data-deel definieert
# zes competenties (C1..C6) met een rubric en een opbouwtabel; elk hoofdstuk
# van het deel draagt een kader dat zegt welke competenties het oefent en hoe
# zelfstandig. Kader en tabel moeten elkaar dekken.
COMPETENCY_PAGE = "chapters/BIG_DATA/01b_Onderzoekscompetenties"
COMPETENCY_TITLE = "Onderzoekscompetenties: van vraag naar conclusie"
COMPETENCIES = {
    "C1": "Onderzoeksvraag formuleren",
    "C2": "Data zoeken",
    "C3": "Data beoordelen",
    "C4": "Data klaarmaken",
    "C5": "Visualiseren",
    "C6": "Interpreteren en concluderen",
}
COMPETENCY_LEVELS = ("begeleid", "deels zelfstandig", "zelfstandig")
COMPETENCY_BOX = "Onderzoekscompetenties in dit hoofdstuk"
RUBRIC_LEVELS = ("Nog niet", "Op weg", "Beheerst")
# Hoofdstuknummer in de opbouwtabel -> pagina die het kader draagt.
FRAMED_CHAPTERS = {
    2: "chapters/BIG_DATA/02_Power_BI",
    3: "chapters/BIG_DATA/03_Onderzoeksopdracht",
    4: "chapters/BIG_DATA/04_Liegen_met_grafieken",
    5: "chapters/BIG_DATA/05_Onderzoeksopdracht",
    6: "chapters/BIG_DATA/06_Onderzoeksopdracht",
    7: "chapters/BIG_DATA/07_Overhoring",
    8: "chapters/BIG_DATA/08_Eindopdracht",
}
# Leerplancitaten waarmee de competentiepagina de leerplandoelen verankert.
# Elk moet letterlijk op de pagina staan én letterlijk in docs/leerplan.md.
LEERPLAN = ROOT / "docs" / "leerplan.md"
LEERPLAN_QUOTES = [
    "De leerlingen zoeken een dataset op basis van een onderzoeksvraag en stellen een datawarehouse (analytische database) samen.",
    "De leerlingen lichten de belangrijkste karakteristieken van big data toe en schatten het belang ervan voor een onderzoek in.",
    "Laat de leerlingen kritisch reflecteren over de betrouwbaarheid van de dataset door onder meer controle van de bron en waar mogelijk vergelijking met datasets van andere bronnen.",
    "De leerlingen maken op basis van een onderzoeksvraag visualisaties met een business intelligence tool.",
    "Je kan de leerlingen vragen om hun keuze van visualisatie te duiden.",
    "Verbanden zoeken tussen zelf verzamelde data en een (eigen) besluit trekken",
]


class Skip(Exception):
    """Test overgeslagen (zonder pytest)."""


def skip(reason: str) -> None:
    if "pytest" in sys.modules:
        import pytest

        pytest.skip(reason)
    raise Skip(reason)


def load_toc() -> dict:
    import yaml

    return yaml.safe_load((BOOK / "_toc.yml").read_text(encoding="utf-8"))


def toc_pages(part_index: int) -> list[str]:
    """Alle pagina's van één deel uit _toc.yml, in leesvolgorde (paden relatief aan book/)."""
    pages: list[str] = []

    def walk(entries):
        for entry in entries:
            if "file" in entry:
                pages.append(entry["file"])
            walk(entry.get("sections", []))

    walk(load_toc()["parts"][part_index]["chapters"])
    assert pages, f"deel {part_index} in _toc.yml heeft geen pagina's"
    return pages


def pages_before(rel: str) -> list[str]:
    """intro + alle pagina's die in leesvolgorde vóór `rel` komen."""
    ordered = [page for i in range(len(load_toc()["parts"])) for page in toc_pages(i)]
    assert rel in ordered, f"{rel} staat niet in _toc.yml"
    return ["intro"] + ordered[: ordered.index(rel)]


def source_of(rel: str) -> str:
    """Markdown-brontekst van een pagina (notebook of .md), relatief aan book/."""
    notebook = BOOK / f"{rel}.ipynb"
    if notebook.is_file():
        return markdown_of(notebook)
    return (BOOK / f"{rel}.md").read_text(encoding="utf-8")


def intro_part_items() -> list[str]:
    """De genummerde deelbeschrijvingen in intro.md, elk als één regel."""
    intro = (BOOK / "intro.md").read_text(encoding="utf-8")
    return re.findall(r"^\d+\. \*\*.+$", intro, flags=re.MULTILINE)


def markdown_of(notebook: Path) -> str:
    cells = json.loads(notebook.read_text(encoding="utf-8"))["cells"]
    return "\n".join("".join(c["source"]) for c in cells if c["cell_type"] == "markdown")


def chapter_notebooks(part_dir: str) -> list[Path]:
    # Niet recursief: .ipynb_checkpoints/ hoort er niet bij.
    found = sorted((BOOK / "chapters" / part_dir).glob("*.ipynb"))
    assert found, f"geen notebooks gevonden in chapters/{part_dir}"
    return found


def find_phrases(text: str, patterns: list[str]) -> list[str]:
    hits = []
    for pattern in patterns:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            start, end = max(0, m.start() - 40), min(len(text), m.end() + 40)
            hits.append(f"/{pattern}/ -> ...{text[start:end]!r}...")
    return hits


def assert_free_of(paths: list[Path], patterns: list[str], reader) -> None:
    problems = []
    for path in paths:
        for hit in find_phrases(reader(path), patterns):
            problems.append(f"{path.relative_to(ROOT)}: {hit}")
    assert not problems, "\n".join(problems)


def page_html(rel: str) -> str:
    page = HTML / f"{rel}.html"
    if not HTML.is_dir():
        skip("book/_build/html ontbreekt; bouw eerst met `teachbooks build book`")
    assert page.is_file(), f"gebouwde pagina ontbreekt: {page.relative_to(ROOT)}"
    return page.read_text(encoding="utf-8")


def prev_next(rel: str) -> tuple[str | None, str | None]:
    """Geef de (prev, next)-doelen van een pagina als paden relatief aan book/, zonder .html."""
    text = page_html(rel)
    page_dir = Path(rel).parent

    def target(css_class: str) -> str | None:
        m = re.search(rf'<a\s+class="{css_class}"[^>]*?href="([^"]+)"', text, flags=re.DOTALL)
        if not m:
            return None
        href = html.unescape(m.group(1)).split("#")[0]
        parts: list[str] = []
        for piece in (page_dir / href).as_posix().split("/"):
            if piece == "..":
                parts.pop()
            elif piece and piece != ".":
                parts.append(piece)
        return "/".join(parts).removesuffix(".html")

    return target("left-prev"), target("right-next")


def competency_box(rel: str) -> dict[str, str]:
    """{code: niveau} uit het kader 'Onderzoekscompetenties in dit hoofdstuk' van een pagina."""
    text = source_of(rel)
    m = re.search(rf":::\{{admonition\}} {COMPETENCY_BOX}\n(.*?)\n:::", text, flags=re.DOTALL)
    assert m, f"{rel}: geen kader '{COMPETENCY_BOX}'"
    body = m.group(1)
    assert f"]({Path(COMPETENCY_PAGE).name}.ipynb)" in body, f"{rel}: het kader linkt niet naar de competentiepagina"
    levels: dict[str, str] = {}
    for code, name, level in re.findall(r"^- \*\*(C\d) ([^*]+)\*\* — \*([^*]+)\*:", body, flags=re.MULTILINE):
        assert COMPETENCIES.get(code) == name, f"{rel}: {code} heet '{name}', verwacht '{COMPETENCIES.get(code)}'"
        assert level in COMPETENCY_LEVELS, f"{rel}: onbekend niveau '{level}' bij {code}"
        levels[code] = level
    assert levels, f"{rel}: het kader noemt geen enkele competentie"
    return levels


def build_up_table() -> dict[int, dict[str, str]]:
    """De tabel 'Waar oefen je wat?' op de competentiepagina: hoofdstuknummer -> {code: niveau of '—'}."""
    rows: dict[int, dict[str, str]] = {}
    for m in re.finditer(r"^\| (\d)\. [^|]+\| (.+) \|$", source_of(COMPETENCY_PAGE), flags=re.MULTILINE):
        cells = [c.strip() for c in m.group(2).split("|")]
        assert len(cells) == len(COMPETENCIES), f"rij {m.group(0)!r} heeft {len(cells)} cellen"
        rows[int(m.group(1))] = dict(zip(COMPETENCIES, cells))
    assert rows, "geen opbouwtabel gevonden op de competentiepagina"
    return rows


def article_html(rel: str) -> str:
    """Alleen de inhoud van een gebouwde pagina (zonder zijbalk, prev/next en de rest van het thema)."""
    m = re.search(r"<article[^>]*>(.*?)</article>", page_html(rel), flags=re.DOTALL)
    assert m, f"{rel}: geen <article> in de gebouwde pagina"
    return m.group(1)


# --- brontests ------------------------------------------------------------


def test_toc_part_order() -> None:
    captions = [part["caption"] for part in load_toc()["parts"]]
    assert captions == EXPECTED_PARTS, f"volgorde in _toc.yml: {captions}"


def test_toc_files_exist() -> None:
    missing = []

    def walk(entries):
        for entry in entries:
            if "file" in entry:
                path = BOOK / entry["file"]
                if not (path.with_suffix(".ipynb").is_file() or path.with_suffix(".md").is_file()):
                    missing.append(entry["file"])
            walk(entry.get("sections", []))

    for part in load_toc()["parts"]:
        walk(part["chapters"])
    assert not missing, f"in _toc.yml maar niet op schijf: {missing}"


def test_intro_lists_parts_in_toc_order() -> None:
    intro = (BOOK / "intro.md").read_text(encoding="utf-8")
    listed = re.findall(r"^\d+\. \*\*(.+?)\*\*", intro, flags=re.MULTILINE)
    assert [t.lower() for t in listed] == [t.lower() for t in EXPECTED_PARTS], (
        f"intro.md beschrijft de delen als {listed}, _toc.yml als {EXPECTED_PARTS}"
    )


def test_sources_have_no_stale_part_references() -> None:
    notebooks = [nb for part in ("SQL", "BIG_DATA", "ERD") for nb in chapter_notebooks(part)]
    assert_free_of(notebooks, STALE_PHRASES, markdown_of)
    assert_free_of([BOOK / "intro.md"], STALE_PHRASES, lambda p: p.read_text(encoding="utf-8"))


def test_big_data_does_not_assume_erd_knowledge() -> None:
    assert_free_of(chapter_notebooks("BIG_DATA"), ERD_VOCABULARY, markdown_of)


def test_erd_does_not_point_to_a_later_part() -> None:
    assert_free_of(chapter_notebooks("ERD"), ERD_FORWARD_REFERENCES, markdown_of)


def test_sql_part_needs_no_installation() -> None:
    assert_free_of(chapter_notebooks("SQL"), INSTALL_PHRASES, markdown_of)


def test_intro_promises_no_installation_for_sql_part() -> None:
    items = intro_part_items()
    assert len(items) == len(EXPECTED_PARTS), f"intro.md beschrijft {len(items)} delen"
    hits = find_phrases(items[0], INSTALL_PHRASES)
    assert not hits, "intro.md, deel 1: " + "\n".join(hits)


def test_first_erd_page_installs_db_browser_with_motivation() -> None:
    text = source_of(FIRST_ERD)
    assert re.search(DB_BROWSER_DOWNLOAD, text), f"{FIRST_ERD}: geen downloadlink naar DB Browser"
    assert re.search(DB_BROWSER_NAME, text), f"{FIRST_ERD}: DB Browser for SQLite wordt niet benoemd"
    # De motivatie: hier wordt je databank een bestand dat je bewaart en indient.
    assert re.search(r"\bbestand\b", text, flags=re.IGNORECASE), f"{FIRST_ERD}: geen motivatie (bestand)"


def test_no_db_browser_before_first_erd_page() -> None:
    problems = []
    for rel in pages_before(FIRST_ERD):
        text = source_of(rel)
        if rel == "intro":
            text = intro_part_items()[0]  # deel 3 mag DB Browser wel aankondigen
        problems += [f"{rel}: {hit}" for hit in find_phrases(text, [DB_BROWSER_DOWNLOAD, r"DB ?Browser"])]
    assert not problems, "\n".join(problems)


def test_competency_page_is_a_section_of_big_data_intro() -> None:
    chapters = load_toc()["parts"][EXPECTED_PARTS.index("Big Data")]["chapters"]
    intro = next(c for c in chapters if c["file"] == FIRST_BIG_DATA)
    assert [s["file"] for s in intro.get("sections", [])] == [COMPETENCY_PAGE], intro
    assert (BOOK / f"{COMPETENCY_PAGE}.ipynb").is_file()
    assert source_of(COMPETENCY_PAGE).startswith(f"# {COMPETENCY_TITLE}\n")


def test_competency_page_defines_competencies_rubric_and_checklist() -> None:
    text = source_of(COMPETENCY_PAGE)
    problems = []
    for code, name in COMPETENCIES.items():
        if not re.search(rf"^### {code} — {name}$", text, flags=re.MULTILINE):
            problems.append(f"geen paragraaf '### {code} — {name}'")
        if not re.search(rf"^\| \*\*{code}\*\* {name} \|", text, flags=re.MULTILINE):
            problems.append(f"geen rubricrij voor {code}")
        if not re.search(rf"^- \[ \] \*\*{code}\*\* ", text, flags=re.MULTILINE):
            problems.append(f"geen checklistitem voor {code}")
    assert "| Competentie | " + " | ".join(RUBRIC_LEVELS) + " |" in text, "rubric mist de kop met de drie niveaus"
    # De drie ankers uit de issue: data beoordelen op bron/actualiteit/definities
    # (gekoppeld aan de 5 V's), grafiekvorm kiezen per vraagtype (gekoppeld aan
    # Liegen met grafieken, hoofdstuk 4), en hergebruik in de lessen economie.
    for pattern in (r"\*\*Bron\*\*", r"\*\*Actualiteit\*\*", r"\*\*Definities\*\*", r"5 V's",
                    r"^\| Wat wil je tonen\? \|", r"checklist uit hoofdstuk 4", r"lessen economie"):
        if not re.search(pattern, text, flags=re.MULTILINE):
            problems.append(f"ontbreekt: /{pattern}/")
    assert not problems, "\n".join(problems)


def test_competency_page_quotes_resolve_in_leerplan() -> None:
    page = source_of(COMPETENCY_PAGE)
    leerplan = re.sub(r"[*_]", "", LEERPLAN.read_text(encoding="utf-8"))  # **vet** weg
    missing = [q for q in LEERPLAN_QUOTES if q not in page]
    assert not missing, "niet op de competentiepagina:\n" + "\n".join(missing)
    unresolved = [q for q in LEERPLAN_QUOTES if q not in leerplan]
    assert not unresolved, "niet letterlijk in docs/leerplan.md:\n" + "\n".join(unresolved)


def test_big_data_chapters_frame_their_competencies() -> None:
    table = build_up_table()
    assert sorted(table) == sorted(FRAMED_CHAPTERS), f"opbouwtabel beschrijft hoofdstukken {sorted(table)}"
    problems = []
    for number, rel in FRAMED_CHAPTERS.items():
        expected = {code: level for code, level in table[number].items() if level != "—"}
        box = competency_box(rel)
        if box != expected:
            problems.append(f"{rel}: kader {box} != opbouwtabel {expected}")
    assert not problems, "\n".join(problems)


def test_competency_build_up_runs_from_guided_to_independent() -> None:
    table = build_up_table()
    assert "zelfstandig" not in table[3].values(), f"eerste onderzoeksopdracht is begeleid: {table[3]}"
    assert set(table[8].values()) == {"zelfstandig"}, f"eindopdracht is volledig zelfstandig: {table[8]}"
    for code in COMPETENCIES:
        levels = {table[n][code] for n in table}
        assert "zelfstandig" in levels, f"{code} wordt nergens zelfstandig geoefend"
    first_own_question = min(n for n in table if table[n]["C1"] != "—")
    assert first_own_question == 5, f"eigen onderzoeksvragen beginnen in hoofdstuk {first_own_question}"


def test_big_data_intro_and_book_intro_announce_the_competencies() -> None:
    text = source_of(FIRST_BIG_DATA)
    assert f"[{COMPETENCY_TITLE}]({Path(COMPETENCY_PAGE).name}.ipynb)" in text, f"{FIRST_BIG_DATA}: geen link naar de competentiepagina"
    assert "lessen economie" in text, f"{FIRST_BIG_DATA}: de afstemming met economie wordt niet benoemd"
    big_data_item = intro_part_items()[EXPECTED_PARTS.index("Big Data")]
    assert "onderzoekscompetenties" in big_data_item and "economie" in big_data_item, big_data_item


# --- tests op de gebouwde site (wat de leerling ziet) ----------------------


def visible_text(rel: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", page_html(rel)))


def test_html_sidebar_lists_parts_in_order() -> None:
    captions = [
        html.unescape(c).strip()
        for c in re.findall(r'class="caption-text">(.*?)</span>', page_html("intro"))
    ]
    assert captions == EXPECTED_PARTS, f"zijbalk toont de delen als {captions}"


def test_html_prev_next_flow_between_parts() -> None:
    assert prev_next(LAST_SQL)[1] == FIRST_BIG_DATA, prev_next(LAST_SQL)
    assert prev_next(FIRST_BIG_DATA)[0] == LAST_SQL, prev_next(FIRST_BIG_DATA)
    assert prev_next(LAST_BIG_DATA)[1] == FIRST_ERD, prev_next(LAST_BIG_DATA)
    assert prev_next(FIRST_ERD)[0] == LAST_BIG_DATA, prev_next(FIRST_ERD)
    assert prev_next(LAST_ERD)[1] is None, "het ERD-deel sluit het boek af"


def test_html_has_no_stale_part_references() -> None:
    pages = ["intro", LAST_SQL, FIRST_BIG_DATA, LAST_BIG_DATA, FIRST_ERD, LAST_ERD]
    problems = []
    for rel in pages:
        text = re.sub(r"<[^>]+>", "", page_html(rel))  # tags weg, tekst blijft
        problems += [f"{rel}: {hit}" for hit in find_phrases(text, STALE_PHRASES)]
    assert not problems, "\n".join(problems)


def test_html_sql_part_needs_no_installation() -> None:
    problems = []
    for rel in toc_pages(0):
        problems += [f"{rel}: {hit}" for hit in find_phrases(visible_text(rel), INSTALL_PHRASES)]
    m = re.search(r'<ol class="arabic simple">\s*<li>(.*?)</li>', page_html("intro"), flags=re.DOTALL)
    assert m, "intro.html: genummerde lijst met de delen niet gevonden"
    first_item = html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
    problems += [f"intro (deel 1): {hit}" for hit in find_phrases(first_item, INSTALL_PHRASES)]
    assert not problems, "\n".join(problems)


def test_html_db_browser_download_first_appears_on_first_erd_page() -> None:
    assert re.search(rf'href="{DB_BROWSER_DOWNLOAD}"', page_html(FIRST_ERD)), (
        f"{FIRST_ERD}: geen downloadlink naar DB Browser in de gebouwde pagina"
    )
    problems = []
    for rel in pages_before(FIRST_ERD):
        if re.search(DB_BROWSER_DOWNLOAD, page_html(rel)):
            problems.append(f"{rel}: bevat de downloadlink van DB Browser vóór het ERD-deel")
    assert not problems, "\n".join(problems)


def test_html_competency_page_renders_rubric_and_leerplan() -> None:
    text = page_html(COMPETENCY_PAGE)
    assert re.search(rf"<h1>{re.escape(COMPETENCY_TITLE)}", text), "titel van de competentiepagina ontbreekt"
    visible = visible_text(COMPETENCY_PAGE)
    problems = []
    for code, name in COMPETENCIES.items():
        if f"{code} — {name}" not in visible:
            problems.append(f"paragraaf {code} — {name} niet zichtbaar")
    for level in RUBRIC_LEVELS:
        if not re.search(rf"<th[^>]*>(<p>)?{level}(</p>)?</th>", text):
            problems.append(f"rubrickolom '{level}' niet gerenderd als tabelkop")
    if not re.search(rf"<td[^>]*>(<p>)?<strong>C6</strong> {COMPETENCIES['C6']}", text):
        problems.append("rubricrij C6 niet gerenderd als tabelcel")
    for phrase in ("Dezelfde rubric in de lessen economie", "Voor de leraar: link met het leerplan", *LEERPLAN_QUOTES):
        if phrase not in visible:
            problems.append(f"niet zichtbaar: {phrase[:60]!r}")
    assert not problems, "\n".join(problems)


def test_html_big_data_chapters_show_competency_box_with_link() -> None:
    target = f'<a class="reference internal" href="{Path(COMPETENCY_PAGE).name}.html">'
    problems = []
    for rel in [FIRST_BIG_DATA, *FRAMED_CHAPTERS.values()]:
        article = article_html(rel)
        if target not in article:
            problems.append(f"{rel}: geen link naar de competentiepagina in de tekst")
        if rel != FIRST_BIG_DATA and COMPETENCY_BOX not in html.unescape(re.sub(r"<[^>]+>", "", article)):
            problems.append(f"{rel}: kader '{COMPETENCY_BOX}' ontbreekt")
    assert not problems, "\n".join(problems)


def test_html_competency_page_sits_between_big_data_intro_and_power_bi() -> None:
    assert prev_next(FIRST_BIG_DATA)[1] == COMPETENCY_PAGE, prev_next(FIRST_BIG_DATA)
    assert prev_next(COMPETENCY_PAGE) == (FIRST_BIG_DATA, FRAMED_CHAPTERS[2]), prev_next(COMPETENCY_PAGE)
    assert prev_next(FRAMED_CHAPTERS[2])[0] == COMPETENCY_PAGE, prev_next(FRAMED_CHAPTERS[2])
    sidebar = re.search(rf'href="{COMPETENCY_PAGE}\.html">([^<]*)<', page_html("intro"))
    assert sidebar and sidebar.group(1) == COMPETENCY_TITLE, "zijbalk toont de competentiepagina niet onder de Big Data-inleiding"


# --- runner zonder pytest --------------------------------------------------


def main() -> int:
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    for name, fn in tests:
        try:
            fn()
        except Skip as exc:
            counts["skipped"] += 1
            print(f"SKIP {name} - {exc}")
        except AssertionError as exc:
            counts["failed"] += 1
            print(f"FAIL {name}\n    " + str(exc).replace("\n", "\n    "))
        else:
            counts["passed"] += 1
            print(f"PASS {name}")
    print(f"{counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
