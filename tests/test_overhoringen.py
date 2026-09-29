"""Tests voor de overhoringen (issue #60): losse pagina's in
book/overhoringen/<naam>/, gebouwd door book/_ext/overhoringen.py.

Drie lagen, net als tests/test_book_structure.py en tests/test_sql_editor.py:

- brontests: het formaat van elke overhoringnotebook (met de parser van de
  extensie zelf), de regels voor wat een pagina wordt, en dat de cursus de
  overhoringen niet kent;
- tests op de gebouwde site (book/_build/html): de pagina bestaat, heeft geen
  enkele weg naar de cursus, staat niet in de zoekindex, en haar CSS/JS staan
  alleen op overhoringpagina's;
- e2e-tests in een echte Chromium (Playwright): de achtergrond verschilt van
  de cursus (light en dark), de band blijft in beeld, en "Download mijn
  antwoorden" levert een Markdown-bestand met de drie vragen en hun antwoord.
  De Node-unittests van book/_static/overhoring-markdown.js
  (tests/overhoring-markdown.test.mjs) lopen hier ook.

De HTML- en e2e-tests worden overgeslagen zolang de build of Playwright
ontbreekt:

    pip install -r requirements-dev.txt
    playwright install chromium
    teachbooks build book
    pytest tests/test_overhoringen.py
"""
from __future__ import annotations

import functools
import html
import http.server
import json
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import expect, sync_playwright
except ImportError:  # pragma: no cover - zonder playwright worden de e2e-tests overgeslagen
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "book"
HTML = BOOK / "_build" / "html"
QUIZ_DIR = BOOK / "overhoringen"
TEMPLATE = "overhoringen/template/overhoring"  # docname van de template
TEMPLATE_PAGE = f"{TEMPLATE}.html"
COURSE_PAGE = "chapters/SQL/01_Starten_met_sql.html"
NODE_TEST = ROOT / "tests" / "overhoring-markdown.test.mjs"
NO_BUILD = "book/_build/html ontbreekt; bouw eerst met `teachbooks build book`"

sys.path.insert(0, str(BOOK / "_ext"))
import overhoringen  # noqa: E402  (de extensie zelf: parser en naamregels)


def quiz_notebooks() -> list[Path]:
    """Elke overhoringnotebook: book/overhoringen/<naam>/<pagina>.ipynb."""
    found = sorted(
        path for path in QUIZ_DIR.glob("*/*.ipynb")
        if overhoringen.is_quiz_source(path.relative_to(BOOK).as_posix())
    )
    assert found, "geen overhoringnotebooks gevonden in book/overhoringen/"
    return found


def toc_files() -> list[str]:
    import yaml

    toc = yaml.safe_load((BOOK / "_toc.yml").read_text(encoding="utf-8"))
    files = [toc["root"]]

    def walk(entries):
        for entry in entries:
            if "file" in entry:
                files.append(entry["file"])
            walk(entry.get("sections", []))

    for part in toc["parts"]:
        walk(part["chapters"])
    return files


def source_text(rel: str) -> str:
    """Volledige brontekst (ook codecellen) van een pagina uit _toc.yml."""
    rel = re.sub(r"\.(md|ipynb)$", "", rel)
    notebook = BOOK / f"{rel}.ipynb"
    if notebook.is_file():
        cells = json.loads(notebook.read_text(encoding="utf-8"))["cells"]
        return "\n".join("".join(c["source"]) for c in cells)
    return (BOOK / f"{rel}.md").read_text(encoding="utf-8")


def notebook(*cells: tuple[str, str, list[str]]) -> dict:
    """Een kleine notebook: (soort, bron, tags) per cel."""
    return {
        "cells": [
            {"cell_type": kind, "metadata": {"tags": tags} if tags else {}, "source": source}
            for kind, source, tags in cells
        ]
    }


GOOD = [
    ("code", "/_static/db/webshop.db", ["sql-db"]),
    ("markdown", "# Titel\n\nInstructie.\n\n## Doelen\n\n- doel 1\n- doel 2", []),
    ("markdown", "## Vraag 1\n\nSchrijf een query.", []),
    ("code", "-- query", ["sql-live"]),
    ("markdown", "## Vraag 2 — uitleg\n\nLeg uit.", []),
    ("code", "Schrijf hier.", ["overhoring-open"]),
    ("markdown", "## Vraag 3\n\nKies.", []),
    ("code", "`A`\nB\n\nC", ["overhoring-mc"]),
]


# --- brontests -------------------------------------------------------------


def test_node_unit_tests_for_the_answers_file() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip(f"node ontbreekt (nodig voor tests/{NODE_TEST.name})")
    proc = subprocess.run(
        [node, "--test", "--test-reporter=tap", str(NODE_TEST)], capture_output=True, text=True, cwd=ROOT
    )
    assert proc.returncode == 0, f"node --test faalde:\n{proc.stdout}\n{proc.stderr}"
    assert re.search(r"^# fail 0$", proc.stdout, flags=re.MULTILINE), proc.stdout
    assert not re.search(r"^# pass 0$", proc.stdout, flags=re.MULTILINE), proc.stdout


def test_only_quiz_notebooks_become_pages() -> None:
    """Elke notebook rechtstreeks in overhoringen/<naam>/ wordt een pagina; de
    rest van zo'n map (leerdoelen.md, rubriek.csv, #62/#63) niet."""
    pages = ["overhoringen/template/overhoring.ipynb", "overhoringen/sql-h1-h2/overhoring.ipynb",
             "overhoringen/sql-h1-h2/groep-b.ipynb"]
    others = ["overhoringen/sql-h1-h2/leerdoelen.md", "overhoringen/sql-h1-h2/rubriek.csv",
              "overhoringen/README.md", "overhoringen/los.ipynb", "overhoringen/a/b/diep.ipynb",
              "overhoringen/a/.ipynb_checkpoints/overhoring-checkpoint.ipynb", "chapters/SQL/01_Starten_met_sql.ipynb",
              "Untitled.ipynb"]
    assert [p for p in pages if not overhoringen.is_quiz_source(p)] == []
    assert [p for p in others if overhoringen.is_quiz_source(p)] == []
    assert overhoringen.quiz_id("overhoringen/sql-h1-h2/overhoring") == "sql-h1-h2"
    assert overhoringen.quiz_id("overhoringen/sql-h1-h2/groep-b") == "sql-h1-h2-groep-b"


def test_quiz_pages_are_not_in_the_toc_and_the_course_does_not_link_to_them() -> None:
    files = toc_files()
    assert not [f for f in files if f.startswith("overhoringen")], files
    problems = [f for f in files if "overhoringen/" in source_text(f)]
    assert not problems, f"cursuspagina's die naar een overhoring verwijzen: {problems}"


def test_every_quiz_notebook_follows_the_format() -> None:
    """Het formaat uit book/overhoringen/README.md, met de parser van de
    extensie: titel, doelen, doorlopend genummerde vragen met elk één
    antwoordcel. /overhoring (#63) genereert pagina's volgens dit formaat."""
    problems = []
    for path in quiz_notebooks():
        _, errors = overhoringen.read_quiz(path)
        problems += [f"{path.relative_to(ROOT)}: {error}" for error in errors]
    assert not problems, "\n".join(problems)


def test_template_shows_the_three_question_types() -> None:
    quiz, errors = overhoringen.read_quiz(QUIZ_DIR / "template" / "overhoring.ipynb")
    assert not errors, errors
    assert [q["type"] for q in quiz["questions"]] == ["sql", "open", "mc"]
    cells = json.loads((QUIZ_DIR / "template" / "overhoring.ipynb").read_text(encoding="utf-8"))["cells"]
    seeds = ["".join(c["source"]).strip() for c in cells if "sql-db" in c.get("metadata", {}).get("tags", [])]
    assert len(seeds) == 1 and (BOOK / seeds[0].lstrip("/")).is_file(), seeds


def test_parser_reads_the_format() -> None:
    quiz, errors = overhoringen.parse_quiz(notebook(*GOOD))
    assert errors == []
    assert quiz["title"] == "Titel"
    assert quiz["doelen"] == "- doel 1\n- doel 2"
    assert [(q["heading"], q["type"], q["text"]) for q in quiz["questions"]] == [
        ("Vraag 1", "sql", "Schrijf een query."),
        ("Vraag 2 — uitleg", "open", "Leg uit."),
        ("Vraag 3", "mc", "Kies."),
    ]
    assert quiz["questions"][1]["placeholder"] == "Schrijf hier."
    assert quiz["questions"][2]["options"] == ["`A`", "B", "C"]


@pytest.mark.parametrize(
    ("cells", "expected"),
    [
        pytest.param(GOOD[:3] + [("code", "", ["sql-live"])] + GOOD[4:], "lege antwoordcel", id="lege-antwoordcel"),
        pytest.param(GOOD[:3] + [("code", "SELECT 1;", [])] + GOOD[3:], "precies één van de tags", id="codecel-zonder-tag"),
        pytest.param(GOOD[:4] + [("code", "x", ["overhoring-open"])] + GOOD[4:], "zonder eigen '## Vraag n'-kop", id="twee-antwoordcellen"),
        pytest.param(GOOD[:3] + GOOD[4:], "'Vraag 1' heeft geen antwoordcel", id="vraag-zonder-antwoord"),
        pytest.param(GOOD[:7] + [("code", "enige optie", ["overhoring-mc"])], "minder dan twee opties", id="een-optie"),
        pytest.param(GOOD[:7] + [("code", "A\nA", ["overhoring-mc"])], "dubbele opties", id="dubbele-optie"),
        pytest.param(GOOD[:4] + [("markdown", "## Vraag 3\n\nLeg uit.", [])] + GOOD[5:], "niet doorlopend genummerd", id="nummering"),
        pytest.param([GOOD[0], ("markdown", "# Titel", [])] + GOOD[2:], "geen doelen", id="geen-doelen"),
        pytest.param([("markdown", "## Doelen\n\n- doel", [])] + GOOD[2:], "geen titel", id="geen-titel"),
    ],
)
def test_parser_reports_format_errors(cells, expected) -> None:
    _, errors = overhoringen.parse_quiz(notebook(*cells))
    assert any(expected in error for error in errors), errors


def test_parser_skips_removed_cells_and_headings_in_code_blocks() -> None:
    cells = [
        ("markdown", "## Vraag 9\n\nnotitie voor de auteur", ["remove-cell"]),
        *GOOD[:2],
        ("markdown", "## Vraag 1\n\nWat toont dit?\n\n```text\n## Vraag 7 (geen kop)\n```", []),
        *GOOD[3:],
    ]
    quiz, errors = overhoringen.parse_quiz(notebook(*cells))
    assert errors == []
    assert quiz["questions"][0]["text"] == "Wat toont dit?\n\n```text\n## Vraag 7 (geen kop)\n```"


# --- de gebouwde site --------------------------------------------------------


def built(rel: str) -> str:
    if not HTML.is_dir():
        pytest.skip(NO_BUILD)
    page = HTML / rel
    assert page.is_file(), f"gebouwde pagina ontbreekt: {page.relative_to(ROOT)}"
    return page.read_text(encoding="utf-8")


def test_html_every_quiz_notebook_is_built_with_the_quiz_template() -> None:
    for path in quiz_notebooks():
        docname = path.relative_to(BOOK).with_suffix("").as_posix()
        text = built(f"{docname}.html")
        assert '<body class="overhoring-page"' in text, docname
        assert 'document.documentElement.classList.add("overhoring")' in text, docname
        assert re.search(r'<header class="overhoring-band"[^>]*>\s*<span class="overhoring-band__label">Overhoring</span>', text), docname
        assert '<meta name="robots" content="noindex, nofollow"/>' in text, docname
        m = re.search(r'<script type="application/json" id="overhoring-data">(.*?)</script>', text, flags=re.DOTALL)
        assert m, f"{docname}: geen vragen voor overhoring.js"
        quiz, _ = overhoringen.read_quiz(path)
        assert json.loads(m.group(1)) == {"id": overhoringen.quiz_id(docname), **quiz}, docname


def test_html_quiz_page_has_no_way_to_the_course() -> None:
    """Geen zijbalk, logo, zoekveld (ook niet het Ctrl+K-venster), knoppen naar
    GitHub, vorige/volgende of rel-links: de enige verwijzingen zijn de eigen
    assets in _static en de canonieke URL van de pagina zelf."""
    text = built(TEMPLATE_PAGE)
    problems = []
    for attr, url in re.findall(r'\b(href|action)="([^"]*)"', text):
        url = html.unescape(url)
        if url.startswith(("../../_static/", "#")):
            continue
        if url in ("https://yvanvds.github.io/DataBeheer/overhoringen/template/overhoring.html",
                   "https://unpkg.com/viewerjs/dist/viewer.min.css"):  # canonieke URL, stylesheet van teachbooks_zoomies
            continue
        problems.append(f'{attr}="{url}"')
    assert not problems, "verwijzingen weg van de overhoring:\n" + "\n".join(problems)
    for needle in ("<form", "bd-sidebar", "search-button", "prev-next", "header-article", "bd-footer",
                   'rel="search"', 'rel="index"', 'rel="prev"', 'rel="next"', "github.com"):
        assert needle not in text, f"de overhoringpagina bevat nog {needle!r}"
    body = text[text.index("<body"):]
    assert not re.search(r"<a\s[^>]*href=\"(?!#)", body), "de pagina bevat een link"


def test_html_no_course_page_links_to_a_quiz() -> None:
    if not HTML.is_dir():
        pytest.skip(NO_BUILD)
    problems = [
        page.relative_to(HTML).as_posix()
        for page in HTML.rglob("*.html")
        if not page.relative_to(HTML).as_posix().startswith("overhoringen/")
        and "overhoringen/" in page.read_text(encoding="utf-8")
    ]
    assert not problems, f"pagina's die naar een overhoring verwijzen: {problems}"


def test_html_quiz_page_is_not_in_the_search_index() -> None:
    text = built("searchindex.js")
    index = json.loads(re.fullmatch(r"\s*Search\.setIndex\((.*)\)\s*", text, flags=re.DOTALL).group(1))
    assert "chapters/SQL/01_Starten_met_sql" in index["docnames"], "zoekindex zonder cursuspagina's?"
    quiz_docs = [d for d in index["docnames"] if d.startswith("overhoringen/")]
    assert not quiz_docs, f"overhoringen in de zoekindex: {quiz_docs}"
    titles = [overhoringen.read_quiz(path)[0]["title"] for path in quiz_notebooks()]
    assert not [t for t in titles if t in index["titles"] or t in index.get("alltitles", {})], titles


def test_html_other_files_in_the_quiz_folders_are_not_pages() -> None:
    if not HTML.is_dir():
        pytest.skip(NO_BUILD)
    built_pages = sorted(p.relative_to(HTML).as_posix() for p in (HTML / "overhoringen").rglob("*.html"))
    expected = sorted(p.relative_to(BOOK).with_suffix(".html").as_posix() for p in quiz_notebooks())
    assert built_pages == expected
    assert (QUIZ_DIR / "README.md").is_file()


def test_html_quiz_assets_are_only_on_quiz_pages() -> None:
    course = built(COURSE_PAGE)
    for asset in ("overhoring.css", "overhoring.js", "overhoring-markdown.js"):
        assert asset not in course, f"{asset} staat op een cursuspagina"
    quiz = built(TEMPLATE_PAGE)
    assert re.search(r'<link rel="stylesheet" type="text/css" href="\.\./\.\./_static/overhoring\.css', quiz)
    assert re.search(r'<script type="module" src="\.\./\.\./_static/overhoring\.js', quiz)
    assert re.search(r'<script type="module" src="\.\./\.\./_static/sql-editors\.js', quiz)


# --- e2e: de overhoring in een echte browser ---------------------------------


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # geen request-log in de testuitvoer
        pass


@pytest.fixture(scope="module")
def site_url():
    """Serveert de gebouwde site lokaal: modules, de worker en fetch van de
    databank werken niet vanaf file://."""
    if not HTML.is_dir():
        pytest.skip(NO_BUILD)
    handler = functools.partial(_QuietHandler, directory=str(HTML))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def browser():
    if sync_playwright is None:
        pytest.skip("playwright ontbreekt: pip install -r requirements-dev.txt && playwright install chromium")
    with sync_playwright() as pw:
        try:
            chromium = pw.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Chromium niet beschikbaar (draai `playwright install chromium`): {exc}")
        yield chromium
        chromium.close()


def open_page(browser, url: str, *, color_scheme: str = "light", init_script: str | None = None):
    """Een verse context (lege opslag) met één pagina, en de lijst van haar pageerrors."""
    context = browser.new_context(color_scheme=color_scheme, viewport={"width": 1366, "height": 768},
                                  accept_downloads=True)
    page = context.new_page()
    if init_script:
        page.add_init_script(init_script)
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(url)
    return context, page, errors


def wait_ready(page) -> None:
    page.wait_for_function("() => window.sqlLive && window.sqlLive.dbReady === true")


def backgrounds(page) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """(achtergrond van de hele pagina, achtergrond van <body>) als RGB. Heeft
    <html> geen eigen achtergrond, dan vult die van <body> het venster (CSS)."""
    colors = page.evaluate(
        "() => [document.documentElement, document.body].map(el => getComputedStyle(el).backgroundColor)"
    )
    html_bg, body_bg = (tuple(int(float(n)) for n in re.findall(r"[\d.]+", c)) for c in colors)
    page_bg = body_bg if len(html_bg) == 4 and html_bg[3] == 0 else html_bg
    return page_bg[:3], body_bg[:3]


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_quiz_page_looks_different_from_the_course(browser, site_url, scheme) -> None:
    """Vanop afstand herkenbaar: een koel blauwe achtergrond over de hele pagina
    (de cursus is warm papier of ink) en een band "OVERHORING" bovenaan."""
    context, course, _ = open_page(browser, site_url + COURSE_PAGE, color_scheme=scheme)
    try:
        assert course.evaluate("document.documentElement.dataset.theme") == scheme
        course_bg, _ = backgrounds(course)
        quiz = context.new_page()
        quiz.goto(site_url + TEMPLATE_PAGE)
        assert quiz.evaluate("document.documentElement.dataset.theme") == scheme
        quiz_bg, quiz_body_bg = backgrounds(quiz)
        assert quiz_body_bg == quiz_bg, f"{scheme}: <body> {quiz_body_bg} en venster {quiz_bg} verschillen"
        distance = sum((a - b) ** 2 for a, b in zip(quiz_bg, course_bg)) ** 0.5
        assert distance >= 40, f"{scheme}: overhoring {quiz_bg} lijkt te veel op de cursus {course_bg}"
        red, _, blue = quiz_bg
        assert blue - red >= 25, f"{scheme}: de achtergrond van de overhoring is niet koel blauw: {quiz_bg}"
        band = quiz.locator(".overhoring-band")
        expect(band).to_be_visible()
        expect(band.locator(".overhoring-band__label")).to_have_text("OVERHORING", use_inner_text=True)
        box = band.bounding_box()
        assert box["y"] == 0 and box["width"] == 1366, box
        assert quiz.locator(".bd-sidebar-primary, .bd-sidebar-secondary, .search-button__wrapper").count() == 0
    finally:
        context.close()


def test_band_stays_in_view_on_large_screen_mode(browser, site_url) -> None:
    """"Groot scherm" (#48) zet overflow: hidden op de pagina; de band blijft
    toch bovenaan staan en de cel vult alleen de ruimte eronder."""
    context, page, errors = open_page(browser, site_url + TEMPLATE_PAGE)
    try:
        wait_ready(page)
        page.mouse.wheel(0, 1500)  # een eind naar beneden gescrold, zoals tijdens de overhoring
        page.locator(".sql-live-wrap button.fullscreen").first.click()
        band = page.locator(".overhoring-band").bounding_box()
        cell = page.locator(".sql-live-wrap.sql-live-fullscreen").bounding_box()
        assert band["y"] == 0 and band["height"] > 30, band
        assert cell["y"] == pytest.approx(band["height"], abs=1), (band, cell)
        page.keyboard.press("Escape")
        expect(page.locator(".sql-live-wrap.sql-live-fullscreen")).to_have_count(0)
        assert errors == [], errors
    finally:
        context.close()


def answer_everything(page) -> tuple[str, str, str]:
    """Vul de drie vragen van de template in zoals een leerling."""
    query = "SELECT first_name, last_name, city\nFROM customers\nWHERE city = 'Gent'\nORDER BY last_name;"
    # Via de publieke API van de editor (#14), zoals in tests/test_sql_editor.py:
    # typen zou door autocomplete en closeBrackets lopen.
    page.evaluate("sql => window.sqlLive.editors[0].setValue(sql)", query)
    page.locator(".sql-live-wrap button.run").first.click()
    expect(page.locator(".sql-live-output th").first).to_have_text("first_name")
    text = "De query toont elke stad één keer.\nDISTINCT haalt de dubbels weg."
    page.locator(".overhoring-open__input").fill(text)
    choice = "`WHERE email IS NULL`"
    page.locator(".overhoring-mc__option", has_text="WHERE email IS NULL").click()
    return query, text, choice


def download_answers(page, tmp_path: Path) -> tuple[str, str]:
    with page.expect_download() as download:
        page.get_by_role("button", name="Download mijn antwoorden").click()
    path = tmp_path / download.value.suggested_filename
    download.value.save_as(path)
    return download.value.suggested_filename, path.read_text(encoding="utf-8")


def test_download_my_answers_contains_every_question_with_its_answer(browser, site_url, tmp_path) -> None:
    """Het scenario uit #60: query, tekst en keuze invullen → "Download mijn
    antwoorden" → één Markdown-bestand met de doelen en de drie vragen, elk met
    het antwoord van de leerling. Herladen wist niets."""
    quiz, _ = overhoringen.read_quiz(QUIZ_DIR / "template" / "overhoring.ipynb")
    context, page, errors = open_page(browser, site_url + TEMPLATE_PAGE)
    try:
        wait_ready(page)
        expect(page.locator(".sql-download-bar")).to_be_hidden()  # "Mijn werk" is hier geen indienknop
        expect(page.get_by_role("button", name=re.compile("Download|Upload"))).to_have_count(1)
        expect(page.locator(".overhoring-mc__option")).to_have_count(len(quiz["questions"][2]["options"]))

        query, text, choice = answer_everything(page)
        page.reload()
        wait_ready(page)
        assert page.evaluate("() => window.sqlLive.editors[0].getValue()") == query
        expect(page.locator(".overhoring-open__input")).to_have_value(text)
        expect(page.locator(".overhoring-mc__option", has_text="WHERE email IS NULL").locator("input")).to_be_checked()

        name, md = download_answers(page, tmp_path)
        assert name == "template-antwoorden.md"
        expect(page.locator(".overhoring-submit__status")).to_have_text(f"Gedownload: {name}. Dien dit bestand in via Teams.")
        assert md.startswith(f"# {quiz['title']} — antwoorden\n"), md[:120]
        assert f"## Doelen\n\n{quiz['doelen']}\n" in md
        positions = [md.index(f"## {q['heading']}\n\n{q['text']}\n") for q in quiz["questions"]]
        assert positions == sorted(positions), "de vragen staan niet in volgorde"
        sections = re.split(r"^## Vraag \d+.*$", md, flags=re.MULTILINE)[1:]
        assert len(sections) == 3, md
        assert f"**Antwoord:**\n\n```sql\n{query}\n```" in sections[0]
        assert "**Antwoord:**\n\n> De query toont elke stad één keer.\n> DISTINCT haalt de dubbels weg." in sections[1]
        options = quiz["questions"][2]["options"]
        expected = "\n".join(f"- [{'x' if o == choice else ' '}] {o}" for o in options)
        assert f"**Antwoord:**\n\n{expected}" in sections[2]
        assert errors == [], errors
    finally:
        context.close()


def test_quiz_works_when_storage_is_blocked(browser, site_url, tmp_path) -> None:
    """Geblokkeerde localStorage (strenge privacy-instellingen, zie #29): de
    antwoorden worden dan niet bewaard, maar invullen en downloaden werken,
    zonder pageerrors."""
    blocked = (
        "Object.defineProperty(window, 'localStorage', { configurable: true, "
        "get() { throw new DOMException('localStorage is geblokkeerd', 'SecurityError'); } });"
    )
    context, page, errors = open_page(browser, site_url + TEMPLATE_PAGE, init_script=blocked)
    try:
        wait_ready(page)
        query, text, choice = answer_everything(page)
        _, md = download_answers(page, tmp_path)
        assert f"```sql\n{query}\n```" in md
        assert "> De query toont elke stad één keer." in md
        assert f"- [x] {choice}" in md
        assert errors == [], errors
    finally:
        context.close()
