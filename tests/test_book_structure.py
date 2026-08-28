"""Structuurtests voor het boek: deelvolgorde, kruisverwijzingen en prev/next-flow (issue #36),
de plaats van de DB Browser-installatie (issues #33 en #42), de bouwlessen van
het ERD-deel op de site-editor (issue #42) en de verankering van de
onderzoekscompetenties in het Big Data-deel (issue #37) en de les kritisch werken
met AI die daarnaast staat (issue #38).

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

# De enige downloadlink voor DB Browser for SQLite. Sinds issue #42 is het
# programma optioneel: de bouwlessen draaien op de site-editor, en de link
# staat alleen nog in het laatste ERD-hoofdstuk (bestand versus server), in
# een kader dat het als optioneel aankondigt — nergens eerder in leesvolgorde.
DB_BROWSER_DOWNLOAD = r"https://sqlitebrowser\.org/dl/"
DB_BROWSER_NAME = r"DB Browser for SQLite"
# Werkwijze van DB Browser (en installatiestappen) die geen enkele pagina
# vóór dat kader mag veronderstellen.
DB_BROWSER_WORKFLOW = [
    DB_BROWSER_DOWNLOAD,
    r"New Database",
    r"Open Database",
    r"Execute SQL",
    r"Write Changes",
    r"\binstalleer\b",
    r"\binstallatie",
    r"\bgeïnstalleerd",
]

# Bouwlessen (issue #42): ERD hoofdstuk 4 en 5 bouwen een databank van nul op
# de site-editor. Zo'n pagina heeft geen sql-db-cel (lege startdatabank), wel
# sql-live-cellen, en indienen gaat via "Download mijn databank", dat het
# bestand databank-<pagina>.db oplevert (naamgeving in sql-editors.js).
BUILD_LESSONS = {
    "chapters/ERD/04_de_voetbal": "databank-04_de_voetbal.db",
    "chapters/ERD/05_de_cafetaria": "databank-05_de_cafetaria.db",
}
DOWNLOAD_DB_BUTTON = "Download mijn databank"
# PRAGMA foreign_keys staat in sql.js standaard uit en overleeft geen herlaad
# van de pagina: de cafetaria-les voert de regel in een eigen cel uit en zegt
# dat je ze na het heropenen van de pagina opnieuw uitvoert.
FOREIGN_KEYS_ON = "PRAGMA foreign_keys = ON;"

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

# Kritisch werken met AI (issue #38): een les als tweede sectie onder de Big
# Data-inleiding, naast de competentiepagina. Ze is toolonafhankelijk (geen
# chatbot bij naam), werkt zonder account (de te beoordelen gesprekken staan
# uitgeschreven), draagt het competentiekader voor C1/C3/C6 en wordt gelinkt
# vanaf elke plek waar AI-gebruik ter sprake komt.
AI_PAGE = "chapters/BIG_DATA/01c_Kritisch_werken_met_AI"
AI_TITLE = "Kritisch werken met AI: hulpmiddel, geen bron"
AI_COMPETENCIES = {"C1": "deels zelfstandig", "C3": "deels zelfstandig", "C6": "deels zelfstandig"}
# Pagina's die naar de les linken: de Big Data-inleiding, de competentiepagina
# (C3: ook een AI-antwoord toets je aan de bron) en de twee opdrachten waarin AI mag.
AI_LINKED_FROM = [FIRST_BIG_DATA, COMPETENCY_PAGE, FRAMED_CHAPTERS[7], FRAMED_CHAPTERS[8]]
# Pagina's waarnaar de les zelf verwijst (opdrachten, checklist grafieken, competenties).
AI_LINKS_TO = [COMPETENCY_PAGE, FRAMED_CHAPTERS[3], FRAMED_CHAPTERS[4], FRAMED_CHAPTERS[7], FRAMED_CHAPTERS[8]]
CHATBOT_BRANDS = [r"ChatGPT", r"\bClaude\b", r"Copilot", r"\bGemini\b", r"Perplexity", r"OpenAI", r"Anthropic",
                  r"\bGPT-?\d", r"Mistral", r"\bLlama\b"]
# De echte bron van de controleoefening: het Eurostat-uittreksel op de pagina linkt naar deze tabel.
AI_EUROSTAT_TABLE = "https://ec.europa.eu/eurostat/databrowser/view/lfsa_urgaed/default/table"
AI_LEERPLAN_QUOTES = [
    "Laat de leerlingen kritisch reflecteren over de betrouwbaarheid van de dataset door onder meer controle van de bron en waar mogelijk vergelijking met datasets van andere bronnen.",
    "Toon hen dat met foute visualisaties verkeerde analyses worden gemaakt en dat dit soms bewust wordt gedaan voor desinformatie.",
    "Kritisch nadenken over en argumenten afwegen zoals in een dialoog, een gedachtewisseling, een paper",
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


def code_cells_tagged(rel: str, tag: str) -> list[str]:
    """Brontekst van de codecellen van een notebook met de gegeven tag (sql-db, sql-live)."""
    cells = json.loads((BOOK / f"{rel}.ipynb").read_text(encoding="utf-8"))["cells"]
    return [
        "".join(c["source"])
        for c in cells
        if c["cell_type"] == "code" and tag in c.get("metadata", {}).get("tags", [])
    ]


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


def test_db_browser_is_optional_and_only_offered_on_last_erd_page() -> None:
    """Sinds #42 is DB Browser optioneel: het enige installatiekader staat in
    het laatste ERD-hoofdstuk, waar het bestand-versus-server-inzicht zit, en
    laat de leerling het bestand van "Download mijn databank" openen."""
    text = source_of(LAST_ERD)
    m = re.search(r"^:::\{admonition\} (Optioneel:[^\n]*)\n(.*?)^:::$", text, flags=re.MULTILINE | re.DOTALL)
    assert m, f"{LAST_ERD}: geen kader met een titel 'Optioneel: …' voor DB Browser"
    box = m.group(2)
    assert re.search(DB_BROWSER_DOWNLOAD, box), f"{LAST_ERD}: het kader bevat geen downloadlink naar DB Browser"
    assert re.search(DB_BROWSER_NAME, box), f"{LAST_ERD}: het kader benoemt DB Browser for SQLite niet"
    # De motivatie: het gedownloade .db-bestand is een volledige databank, ook buiten de site.
    assert re.search(r"\bbestand\b", box, flags=re.IGNORECASE), f"{LAST_ERD}: geen motivatie (bestand)"
    assert BUILD_LESSONS["chapters/ERD/05_de_cafetaria"] in box, f"{LAST_ERD}: het kader opent niet de download uit hoofdstuk 5"
    assert re.search(r"zonder installatie", box), f"{LAST_ERD}: het kader zegt niet dat de cursus zonder installatie werkt"
    assert len(re.findall(DB_BROWSER_DOWNLOAD, text)) == 1, f"{LAST_ERD}: de downloadlink staat er meer dan één keer"
    # En nergens anders in het boek, ook niet in de intro.
    problems = []
    for rel in ["intro", *(page for i in range(len(load_toc()["parts"])) for page in toc_pages(i))]:
        if rel != LAST_ERD and re.search(DB_BROWSER_DOWNLOAD, source_of(rel)):
            problems.append(f"{rel}: bevat de downloadlink van DB Browser")
    assert not problems, "\n".join(problems)


def test_no_db_browser_before_first_erd_page() -> None:
    problems = []
    for rel in pages_before(FIRST_ERD):
        problems += [f"{rel}: {hit}" for hit in find_phrases(source_of(rel), [DB_BROWSER_DOWNLOAD, r"DB ?Browser"])]
    assert not problems, "\n".join(problems)


def test_erd_part_needs_no_installation_before_the_optional_box() -> None:
    """Een leerling doorloopt het hele ERD-deel zonder iets te installeren:
    geen installatiestappen en geen DB Browser-werkwijze vóór het optionele
    kader in het laatste hoofdstuk (en de intro belooft DB Browser niet meer)."""
    erd_pages = toc_pages(EXPECTED_PARTS.index("Databases Ontwerpen met ERD's"))
    assert erd_pages[-1] == LAST_ERD
    problems = []
    for rel in ["intro", *erd_pages[:-1]]:
        problems += [f"{rel}: {hit}" for hit in find_phrases(source_of(rel), DB_BROWSER_WORKFLOW)]
    problems += [f"intro: {hit}" for hit in find_phrases(source_of("intro"), [r"DB ?Browser"])]
    assert not problems, "\n".join(problems)


def test_build_lessons_run_on_the_site_editor() -> None:
    """ERD hoofdstuk 4 en 5 (#42): sql-live-cellen op een pagina zonder
    sql-db-cel, en indienen via "Download mijn databank" onder de juiste bestandsnaam."""
    problems = []
    for rel, db_file in BUILD_LESSONS.items():
        if code_cells_tagged(rel, "sql-db"):
            problems.append(f"{rel}: heeft een sql-db-cel; een bouwles start met een lege databank")
        live = code_cells_tagged(rel, "sql-live")
        if len(live) < 3:
            problems.append(f"{rel}: {len(live)} sql-live-cellen; de bouwstappen horen in interactieve cellen")
        if not any(re.search(r"^\s*CREATE TABLE\b", sql, flags=re.MULTILINE | re.IGNORECASE) for sql in live):
            problems.append(f"{rel}: geen sql-live-cel met CREATE TABLE")
        text = source_of(rel)
        if f"**{DOWNLOAD_DB_BUTTON}**" not in text:
            problems.append(f"{rel}: noemt de knop {DOWNLOAD_DB_BUTTON} niet")
        if f"`{db_file}`" not in text:
            problems.append(f"{rel}: noemt het in te dienen bestand {db_file} niet")
        if not re.search(r"\blege databank\b", text):
            problems.append(f"{rel}: zegt niet dat de pagina met een lege databank start")
    assert not problems, "\n".join(problems)


def test_cafetaria_lesson_switches_foreign_keys_on_in_a_runnable_cell() -> None:
    rel = "chapters/ERD/05_de_cafetaria"
    pragma_cells = [sql for sql in code_cells_tagged(rel, "sql-live") if FOREIGN_KEYS_ON in sql]
    assert len(pragma_cells) >= 2, f"{rel}: {FOREIGN_KEYS_ON} hoort in een eigen cel bij fase 6 én als herinnering bij fase 7"
    text = source_of(rel)
    assert re.search(
        r"opnieuw\b.{0,160}`PRAGMA foreign_keys = ON;`|`PRAGMA foreign_keys = ON;`.{0,160}\bopnieuw\b",
        text,
        flags=re.DOTALL,
    ), f"{rel}: legt niet uit dat je {FOREIGN_KEYS_ON} na het heropenen van de pagina opnieuw uitvoert"
    assert "Reset db" in text, f"{rel}: noemt Reset db niet (zet de instelling ook uit)"


def test_competency_page_is_a_section_of_big_data_intro() -> None:
    chapters = load_toc()["parts"][EXPECTED_PARTS.index("Big Data")]["chapters"]
    intro = next(c for c in chapters if c["file"] == FIRST_BIG_DATA)
    assert [s["file"] for s in intro.get("sections", [])] == [COMPETENCY_PAGE, AI_PAGE], intro
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


def test_ai_page_is_the_section_next_to_the_competency_page() -> None:
    # De toc-volgorde (competenties, dan AI) zit in test_competency_page_is_a_section_of_big_data_intro.
    assert (BOOK / f"{AI_PAGE}.ipynb").is_file()
    assert source_of(AI_PAGE).startswith(f"# {AI_TITLE}\n")


def test_ai_page_frames_its_competencies() -> None:
    assert competency_box(AI_PAGE) == AI_COMPETENCIES
    # De les is geen genummerd hoofdstuk en staat dus niet in de opbouwtabel;
    # de competentiepagina zegt zelf welke competenties ze oefent.
    assert re.search(
        rf"\[Kritisch werken met AI\]\({Path(AI_PAGE).name}\.ipynb\) draagt zo'n kader: ze oefent C1, C3 en C6",
        source_of(COMPETENCY_PAGE),
    ), "de competentiepagina legt niet uit dat de AI-les C1, C3 en C6 oefent"


def test_ai_page_is_tool_agnostic_and_works_without_account() -> None:
    text = source_of(AI_PAGE)
    hits = find_phrases(text, CHATBOT_BRANDS)
    assert not hits, "de AI-les noemt een chatbot bij naam:\n" + "\n".join(hits)
    assert re.search(r"^:::\{admonition\} Welke AI-assistent\?$", text, flags=re.MULTILINE), "geen kader 'Welke AI-assistent?'"
    assert "**zonder account**" in text, "de les zegt niet dat de oefeningen zonder account kunnen"
    assert re.search(r"Heb je die niet, dan volstaan oefeningen 1 tot 3", text), "de oefening met eigen AI-toegang is niet optioneel"


def test_ai_page_teaches_questions_verification_and_use_per_competency() -> None:
    text = source_of(AI_PAGE)
    problems = []
    # Goede vragen stellen: context, doorvragen, itereren — en een oefening zonder AI.
    for heading in ("### Geef context", "### Vraag door", "### Itereer",
                    "### Oefening 1 — Verbeter de vraag", "### Oefening 2 — De controleoefening",
                    "### Oefening 3 — Beoordeel de brainstorm", "### Oefening 4 — Met je eigen data"):
        if not re.search(rf"^{re.escape(heading)}", text, flags=re.MULTILINE):
            problems.append(f"geen kop '{heading}'")
    # Controleoefening: een uitgeschreven AI-antwoord met genummerde beweringen,
    # de echte bron met raadpleegdatum, en een oplossing die elke bewering beoordeelt.
    claims = re.findall(r"^> \((\d)\) ", text, flags=re.MULTILINE)
    if claims != [str(i) for i in range(1, 8)]:
        problems.append(f"genummerde beweringen in het transcript: {claims}")
    if AI_EUROSTAT_TABLE not in text or "geraadpleegd op" not in text:
        problems.append("de echte bron (Eurostat-tabel met raadpleegdatum) ontbreekt")
    for n in (1, 2, 3):
        if not re.search(rf"^:::\{{admonition\}} Oplossing oefening {n}\n:class: dropdown$", text, flags=re.MULTILINE):
            problems.append(f"geen dropdown 'Oplossing oefening {n}'")
    verdicts = re.findall(r"^\| (?:\d|slot) \| \*\*([^*]+)\*\* \|", text, flags=re.MULTILINE)
    kinds = {"Niet te controleren" if v.startswith("Niet te controleren") else v for v in verdicts}
    if len(verdicts) != 8 or kinds != {"Klopt", "Klopt niet", "Niet te controleren"}:
        problems.append(f"de oplossing beoordeelt niet elke bewering als klopt / klopt niet / niet te controleren: {verdicts}")
    # Wél/niet: één rij per competentie, plus de twee vaste regels.
    if "| Competentie | Wél | Niet |" not in text:
        problems.append("geen tabel 'Competentie | Wél | Niet'")
    for code, name in COMPETENCIES.items():
        if not re.search(rf"^\| \*\*{code}\*\* {name} \| .+ \| .+ \|$", text, flags=re.MULTILINE):
            problems.append(f"geen wél/niet-rij voor {code} {name}")
    for pattern in (r"Een tweede AI is geen controle", r"\*\*Je vermeldt je AI-gebruik\.\*\*", r"verantwoordingstab",
                    r"\*\*hallucineren\*\*", r"is \*\*geen bron\*\*"):
        if not re.search(pattern, text):
            problems.append(f"ontbreekt: /{pattern}/")
    assert not problems, "\n".join(problems)


def test_ai_page_quotes_resolve_in_leerplan() -> None:
    page = source_of(AI_PAGE)
    leerplan = re.sub(r"[*_]", "", LEERPLAN.read_text(encoding="utf-8"))  # **vet** weg
    missing = [q for q in AI_LEERPLAN_QUOTES if q not in page]
    assert not missing, "niet op de AI-les:\n" + "\n".join(missing)
    unresolved = [q for q in AI_LEERPLAN_QUOTES if q not in leerplan]
    assert not unresolved, "niet letterlijk in docs/leerplan.md:\n" + "\n".join(unresolved)
    # Het leerplan noemt AI niet; de les zegt dat eerlijk in plaats van een doel te verzinnen.
    assert "noemt AI-assistenten niet bij naam" in page
    assert not re.search(r"\bAI\b|intelligentie|taalmodel", LEERPLAN.read_text(encoding="utf-8")), "leerplan noemt AI nu wél: pas de leraarsnoot aan"


def test_ai_page_is_linked_wherever_ai_use_comes_up() -> None:
    link = f"]({Path(AI_PAGE).name}.ipynb)"
    problems = [f"{rel}: geen link naar de AI-les" for rel in AI_LINKED_FROM if link not in source_of(rel)]
    if f"[{AI_TITLE}]({Path(AI_PAGE).name}.ipynb)" not in source_of(FIRST_BIG_DATA):
        problems.append(f"{FIRST_BIG_DATA}: de link draagt niet de titel van de les")
    for rel in (FRAMED_CHAPTERS[7], FRAMED_CHAPTERS[8]):
        m = re.search(r"^## AI gebruiken\n(.*?)(?=^## )", source_of(rel), flags=re.MULTILINE | re.DOTALL)
        if not m or link not in m.group(1):
            problems.append(f"{rel}: de sectie 'AI gebruiken' linkt niet naar de AI-les")
    if re.search(r"tweede AI\. Een AI halucineert", source_of(FRAMED_CHAPTERS[7])):
        problems.append(f"{FRAMED_CHAPTERS[7]}: raadt nog een tweede AI aan als controle")
    if "AI-assistent gebruikte" not in source_of(FRAMED_CHAPTERS[8]):
        problems.append(f"{FRAMED_CHAPTERS[8]}: de verantwoordingstab vraagt niet naar het AI-gebruik")
    ai = source_of(AI_PAGE)
    problems += [f"{AI_PAGE}: geen link naar {rel}" for rel in AI_LINKS_TO if f"]({Path(rel).name}.ipynb)" not in ai]
    big_data_item = intro_part_items()[EXPECTED_PARTS.index("Big Data")]
    if "AI-assistent" not in big_data_item:
        problems.append("intro.md: het Big Data-deel kondigt het kritisch werken met AI niet aan")
    assert not problems, "\n".join(problems)


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


def test_html_db_browser_download_only_appears_on_last_erd_page() -> None:
    article = article_html(LAST_ERD)
    assert re.search(rf'href="{DB_BROWSER_DOWNLOAD}"', article), (
        f"{LAST_ERD}: geen downloadlink naar DB Browser in de gebouwde pagina"
    )
    assert re.search(r'<p class="admonition-title">Optioneel:[^<]*</p>', article), (
        f"{LAST_ERD}: het kader 'Optioneel: …' is niet gerenderd"
    )
    problems = []
    for rel in pages_before(LAST_ERD):
        if re.search(DB_BROWSER_DOWNLOAD, page_html(rel)):
            problems.append(f"{rel}: bevat de downloadlink van DB Browser vóór het optionele kader")
    assert not problems, "\n".join(problems)


def test_html_build_lessons_have_live_cells_and_no_seed() -> None:
    problems = []
    for rel, db_file in BUILD_LESSONS.items():
        text = page_html(rel)
        live = len(re.findall(r'class="cell tag_sql-live', text))
        if live < 3:
            problems.append(f"{rel}: {live} sql-live-cellen in de gebouwde pagina")
        if re.search(r'class="cell tag_sql-db', text):
            problems.append(f"{rel}: gebouwde pagina heeft een sql-db-cel (seed)")
        visible = visible_text(rel)
        for phrase in (DOWNLOAD_DB_BUTTON, db_file, "lege databank"):
            if phrase not in visible:
                problems.append(f"{rel}: niet zichtbaar: {phrase!r}")
        problems += [f"{rel}: {hit}" for hit in find_phrases(visible, DB_BROWSER_WORKFLOW)]
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
    for rel in [FIRST_BIG_DATA, *FRAMED_CHAPTERS.values(), AI_PAGE]:
        article = article_html(rel)
        if target not in article:
            problems.append(f"{rel}: geen link naar de competentiepagina in de tekst")
        if rel != FIRST_BIG_DATA and COMPETENCY_BOX not in html.unescape(re.sub(r"<[^>]+>", "", article)):
            problems.append(f"{rel}: kader '{COMPETENCY_BOX}' ontbreekt")
    assert not problems, "\n".join(problems)


def test_html_competency_page_follows_big_data_intro() -> None:
    assert prev_next(FIRST_BIG_DATA)[1] == COMPETENCY_PAGE, prev_next(FIRST_BIG_DATA)
    assert prev_next(COMPETENCY_PAGE) == (FIRST_BIG_DATA, AI_PAGE), prev_next(COMPETENCY_PAGE)
    sidebar = re.search(rf'href="{COMPETENCY_PAGE}\.html">([^<]*)<', page_html("intro"))
    assert sidebar and sidebar.group(1) == COMPETENCY_TITLE, "zijbalk toont de competentiepagina niet onder de Big Data-inleiding"


def test_html_ai_page_sits_between_competency_page_and_power_bi() -> None:
    assert prev_next(AI_PAGE) == (COMPETENCY_PAGE, FRAMED_CHAPTERS[2]), prev_next(AI_PAGE)
    assert prev_next(FRAMED_CHAPTERS[2])[0] == AI_PAGE, prev_next(FRAMED_CHAPTERS[2])
    sidebar = re.findall(r'href="chapters/BIG_DATA/([^"]+)\.html">([^<]*)<', page_html("intro"))
    names = [name for name, _ in sidebar]
    competencies, ai, power_bi = (Path(p).name for p in (COMPETENCY_PAGE, AI_PAGE, FRAMED_CHAPTERS[2]))
    assert ai in names, "zijbalk toont de AI-les niet"
    assert names.index(competencies) < names.index(ai) < names.index(power_bi), names
    assert dict(sidebar)[ai] == AI_TITLE, "zijbalk toont de AI-les niet met haar titel"


def test_html_ai_page_renders_lesson_and_links_resolve() -> None:
    assert re.search(rf"<h1>{re.escape(AI_TITLE)}", page_html(AI_PAGE)), "titel van de AI-les ontbreekt"
    article = article_html(AI_PAGE)
    visible = html.unescape(re.sub(r"<[^>]+>", "", article))
    problems = []
    for title in ("Welke AI-assistent?", "Leerdoelen", COMPETENCY_BOX, "Een tweede AI is geen controle",
                  "Oplossing oefening 1", "Oplossing oefening 2", "Oplossing oefening 3",
                  "Voor de leraar: link met het leerplan"):
        if f'<p class="admonition-title">{title}</p>' not in article:
            problems.append(f"kader '{title}' niet gerenderd")
    if len(re.findall(r'<div class="dropdown admonition">', article)) != 4:
        problems.append("de drie oplossingen en de leraarsnoot renderen niet als vier dropdowns")
    # Tabellen: soorten beweringen, het Eurostat-uittreksel, de oplossing van oefening 2 en wél/niet.
    if len(re.findall(r'<table class="table">', article)) < 4:
        problems.append("minder dan vier tabellen gerenderd")
    for code, name in COMPETENCIES.items():
        if not re.search(rf"<td[^>]*>(<p>)?<strong>{code}</strong> {name}", article):
            problems.append(f"wél/niet-rij {code} niet gerenderd als tabelcel")
    for phrase in ("(1) Hoe lager het opleidingsniveau", "geraadpleegd op", "zonder account", *AI_LEERPLAN_QUOTES):
        if phrase not in visible:
            problems.append(f"niet zichtbaar: {phrase[:60]!r}")
    if f'<a class="reference external" href="{AI_EUROSTAT_TABLE}">' not in article:
        problems.append("de link naar de Eurostat-tabel ontbreekt")
    internal = re.findall(r'<a class="reference internal" href="([^"#]+)', article)
    for href in internal:
        if not (HTML / Path(AI_PAGE).parent / href).is_file():
            problems.append(f"interne link naar onbestaande pagina: {href}")
    for rel in AI_LINKS_TO:
        if f"{Path(rel).name}.html" not in internal:
            problems.append(f"geen link naar {rel} in de gebouwde pagina")
    assert not problems, "\n".join(problems)


def test_html_ai_page_is_linked_from_intro_competencies_and_assignments() -> None:
    target = f'<a class="reference internal" href="{Path(AI_PAGE).name}.html">'
    problems = [f"{rel}: geen link naar de AI-les in de tekst" for rel in AI_LINKED_FROM if target not in article_html(rel)]
    assert not problems, "\n".join(problems)


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
