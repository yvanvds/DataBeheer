"""Tests voor de interactieve SQL-editor: Run voert de selectie uit, of anders
het statement onder de cursor; "Run alles" voert de hele cel uit (issue #34).
"Download mijn queries" / "Upload mijn queries" bewaren het eigen werk van een
pagina als .sql-bestand en zetten het terug (issues #30/#35).

Twee lagen:

- de pure modules (statementgrenzen in book/_static/sql-statements.js, het
  .sql-bestandsformaat in book/_static/sql-queries-file.js) hebben unit-tests
  in Node — tests/*.test.mjs — die hier via ``node --test`` draaien;
- de e2e-tests openen de gebouwde site (book/_build/html) in een echte
  Chromium via Playwright en bedienen de editor zoals een leerling: klikken in
  de tekst, toetsen, knoppen. Ze worden overgeslagen zolang de build of
  Playwright ontbreekt:

      pip install -r requirements-dev.txt
      playwright install chromium
      teachbooks build book
      pytest tests
"""
from __future__ import annotations

import functools
import http.server
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import expect, sync_playwright
except ImportError:  # pragma: no cover - zonder playwright worden de e2e-tests overgeslagen
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "book" / "_build" / "html"
NODE_TESTS = [
    ROOT / "tests" / "sql-statements.test.mjs",  # statementgrenzen (#34)
    ROOT / "tests" / "sql-queries-file.test.mjs",  # .sql-bestandsformaat van download/upload (#30/#35)
]

# Eerste pagina met interactieve cellen (tag sql-live) en een seed-database.
PAGE = "chapters/SQL/01_Starten_met_sql.html"
PAGE_PATH = "/" + PAGE  # location.pathname op de lokale testserver

NO_BUILD = "book/_build/html ontbreekt; bouw eerst met `teachbooks build book`"


# --- unit-tests van de pure modules (Node) ---------------------------------


@pytest.mark.parametrize("node_test", NODE_TESTS, ids=lambda p: p.name)
def test_unit_tests_pass_in_node(node_test: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip(f"node ontbreekt (nodig voor tests/{node_test.name})")
    proc = subprocess.run(
        [node, "--test", "--test-reporter=tap", str(node_test)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, f"node --test faalde:\n{proc.stdout}\n{proc.stderr}"
    assert re.search(r"^# fail 0$", proc.stdout, flags=re.MULTILINE), proc.stdout
    assert not re.search(r"^# pass 0$", proc.stdout, flags=re.MULTILINE), proc.stdout


# --- gebouwde site: scriptinjectie ------------------------------------------


def test_html_loads_only_the_editor_module_as_page_script() -> None:
    """sql-statements.js is een ES-module die sql-editors.js importeert. Zou
    Jupyter Book hem (of een ander editorbestand) als klassiek <script>
    injecteren, dan geeft dat op elke pagina een consolefout — zie
    _ext/sanitize_static_assets.py."""
    if not HTML.is_dir():
        pytest.skip(NO_BUILD)
    for module in ("sql-statements.js", "sql-queries-file.js"):
        assert (HTML / "_static" / module).is_file(), f"{module} niet in de build"
    text = (HTML / PAGE).read_text(encoding="utf-8")
    tags = re.findall(r"<script[^>]*_static/sql-[\w-]+\.js[^>]*>", text)
    assert len(tags) == 1, f"verwachtte alleen sql-editors.js als paginascript: {tags}"
    assert "sql-editors.js" in tags[0] and 'type="module"' in tags[0], tags[0]


# --- e2e: de editor in een echte browser ------------------------------------


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # geen request-log in de testuitvoer
        pass


@pytest.fixture(scope="module")
def site_url():
    """Serveert de gebouwde site lokaal: modules, de worker en fetch van de
    seed-database werken niet vanaf file://."""
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
def page(site_url):
    """De eerste SQL-pagina, geladen tot de database klaar is."""
    if sync_playwright is None:
        pytest.skip("playwright ontbreekt: pip install -r requirements-dev.txt && playwright install chromium")
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Chromium niet beschikbaar (draai `playwright install chromium`): {exc}")
        page = browser.new_page()
        page.goto(site_url + PAGE)
        page.wait_for_function("() => window.sqlLive && window.sqlLive.dbReady === true")
        yield page
        browser.close()


def cell(page):
    """De eerste interactieve cel van de pagina."""
    return page.locator(".sql-live-wrap").first


def load_sql(page, sql: str) -> None:
    # Via de publieke API van #14/#30 — typen zou door autocomplete en
    # closeBrackets lopen en is niet wat we hier testen.
    page.evaluate("sql => window.sqlLive.editors[0].setValue(sql)", sql)


def click_line(page, text: str) -> None:
    """Klik (zoals een leerling) in de editorregel die `text` bevat."""
    cell(page).locator(".cm-line", has_text=text).click()


def result_headers(page):
    """Kolomkoppen van alle resultaattabellen onder de cel."""
    return cell(page).locator(".sql-live-output th")


def three_statements(tag: str) -> str:
    # Unieke aliassen per test, zodat een oud resultaat nooit voor een nieuw
    # kan doorgaan.
    return (
        f"SELECT 1 AS eerste_{tag};\n\n"
        f"SELECT 2 AS tweede_{tag};\n\n"
        f"SELECT 3 AS derde_{tag};"
    )


def test_run_executes_only_the_statement_under_the_cursor(page) -> None:
    load_sql(page, three_statements("cursor"))
    click_line(page, "SELECT 2")
    page.keyboard.press("Control+Enter")
    expect(result_headers(page)).to_have_text(["tweede_cursor"])


def test_run_button_uses_the_cursor_position_too(page) -> None:
    load_sql(page, three_statements("knop"))
    click_line(page, "SELECT 3")
    cell(page).locator("button.run").click()
    expect(result_headers(page)).to_have_text(["derde_knop"])


def test_run_executes_the_selection_when_there_is_one(page) -> None:
    load_sql(page, three_statements("selectie"))
    click_line(page, "SELECT 1")
    page.keyboard.press("Home")
    page.keyboard.press("Shift+ArrowDown")
    page.keyboard.press("Shift+ArrowDown")
    page.keyboard.press("Shift+End")  # selectie: statement 1 tot en met 2
    page.keyboard.press("Control+Enter")
    expect(result_headers(page)).to_have_text(["eerste_selectie", "tweede_selectie"])


def test_run_all_executes_every_statement(page) -> None:
    load_sql(page, three_statements("alles"))
    click_line(page, "SELECT 2")
    page.keyboard.press("Control+Shift+Enter")
    expect(result_headers(page)).to_have_text(["eerste_alles", "tweede_alles", "derde_alles"])

    load_sql(page, three_statements("allesknop"))
    click_line(page, "SELECT 2")
    cell(page).locator("button.runall").click()
    expect(result_headers(page)).to_have_text(["eerste_allesknop", "tweede_allesknop", "derde_allesknop"])


def test_statement_under_the_cursor_is_highlighted(page) -> None:
    load_sql(page, three_statements("markering"))
    click_line(page, "SELECT 2")
    marked = cell(page).locator(".cm-line.sql-run-line")
    expect(marked).to_have_count(1)
    expect(marked).to_contain_text("SELECT 2")

    click_line(page, "SELECT 3")
    expect(marked).to_contain_text("SELECT 3")

    page.keyboard.press("Shift+ArrowUp")  # met een selectie is de selectie zelf de markering
    expect(marked).to_have_count(0)


def test_single_statement_runs_whole_cell_without_highlight(page) -> None:
    load_sql(page, "-- één query\nSELECT 1 AS enkel;")
    click_line(page, "SELECT 1")
    expect(cell(page).locator(".cm-line.sql-run-line")).to_have_count(0)
    page.keyboard.press("Control+Enter")
    expect(result_headers(page)).to_have_text(["enkel"])


# --- e2e: download en upload van het eigen werk (#30/#35) --------------------

WORK_BAR = ".sql-download-bar"  # de balk "Mijn werk" onder de laatste cel


def editor_values(page) -> list[str]:
    return page.evaluate("() => window.sqlLive.editors.map(e => e.getValue())")


def initial_values(page) -> list[str]:
    return page.evaluate("() => window.sqlLive.editors.map(e => e.initialValue)")


def saved_values(page) -> list[str | None]:
    """Wat er per cel in localStorage staat (#14)."""
    return page.evaluate("() => window.sqlLive.editors.map(e => localStorage.getItem(e.key))")


def set_editor(page, index: int, sql: str) -> None:
    page.evaluate("([i, sql]) => window.sqlLive.editors[i].setValue(sql)", [index, sql])


def click_startcode(page, index: int) -> None:
    page.locator(".sql-live-wrap").nth(index).locator("button.startcode").click()


def reload(page) -> None:
    page.reload()
    page.wait_for_function("() => window.sqlLive && window.sqlLive.dbReady === true")


def upload(page, path: Path) -> None:
    """Klik op "Upload mijn queries" en kies `path` in de bestandskiezer."""
    with page.expect_file_chooser() as chooser:
        page.locator(WORK_BAR).locator("button.upload").click()
    chooser.value.set_files(str(path))


def upload_status(page):
    return page.locator(WORK_BAR).locator(".sql-upload-status")


def queries_file(page_path: str, cells: list[str]) -> str:
    """Een bestand in het formaat van "Download mijn queries" (#30)."""
    body = "\n".join(f"-- cel {i + 1}\n{sql}\n" for i, sql in enumerate(cells))
    return f"-- Mijn queries — {page_path}\n\n{body}"


def own_work(tag: str, n: int) -> list[str]:
    # Eigen werk voor de eerste n cellen: meerregelig, met commentaar en een
    # lege regel — precies wat de round-trip moet behouden.
    return [
        f"-- mijn oplossing {i + 1} ({tag})\nSELECT {i + 1} AS cel_{tag};\n\nSELECT 'twee' AS nog_{tag};"
        for i in range(n)
    ]


def test_upload_restores_downloaded_queries_after_storage_is_cleared(page, tmp_path) -> None:
    """Het scenario uit #35: werk downloaden, opslag kwijt (nieuwe laptop),
    bestand uploaden → dezelfde celinhoud terug, en bewaard voor de volgende keer."""
    work = own_work("rondje", 3)
    for i, sql in enumerate(work):
        set_editor(page, i, sql)

    with page.expect_download() as download:
        page.locator(WORK_BAR).locator("button.download").click()
    assert download.value.suggested_filename == "queries-01_Starten_met_sql.sql"
    path = tmp_path / download.value.suggested_filename
    download.value.save_as(path)
    text = path.read_text(encoding="utf-8")
    assert text.startswith(f"-- Mijn queries — {PAGE_PATH}\n"), text[:80]
    assert "\n-- cel 1\n" in text and "\n-- cel 3\n" in text

    # Opslag kwijt: Startcode wist de bewaarde versie van de cellen, en de rest
    # van de opslag gaat weg; na een herlaad staat overal weer de startcode.
    for i in range(3):
        click_startcode(page, i)
    page.evaluate("() => localStorage.clear()")
    reload(page)
    assert editor_values(page)[:3] == initial_values(page)[:3]
    expect(page.locator(".sql-live-own").first).to_be_hidden()

    upload(page, path)  # alleen startcode op de pagina → geen bevestiging nodig
    expect(upload_status(page)).to_have_text(re.compile(r"^Teruggezet: cellen 1, 2, 3, .* en \d+\.$"))
    assert editor_values(page)[:3] == work
    expect(page.locator(".sql-live-own").first).to_be_visible()  # "eigen versie"
    assert saved_values(page)[:3] == work  # meteen bewaard, niet pas na de debounce

    reload(page)
    assert editor_values(page)[:3] == work  # en bij het heropenen van de pagina nog steeds


def test_upload_asks_before_overwriting_own_work(page, tmp_path) -> None:
    mine = own_work("eigen", 2)
    for i, sql in enumerate(mine):
        set_editor(page, i, sql)
    theirs = own_work("bestand", 2)

    # Annuleren: niets verandert. Dit bestand komt bovendien van een andere pagina.
    other_page = tmp_path / "queries-02_Filteren.sql"
    other_page.write_text(queries_file("/chapters/SQL/02_Filteren.html", theirs), encoding="utf-8")
    messages: list[str] = []
    page.once("dialog", lambda dialog: (messages.append(dialog.message), dialog.dismiss()))
    upload(page, other_page)
    expect(upload_status(page)).to_have_text("Upload geannuleerd — er is niets gewijzigd.")
    assert editor_values(page)[:2] == mine
    assert len(messages) == 1, messages
    assert "andere pagina (02_Filteren)" in messages[0], messages[0]
    assert "Cellen 1 en 2 van deze pagina bevatten eigen werk" in messages[0], messages[0]

    # Bevestigen: het bestand wint.
    same_page = tmp_path / "queries-01_Starten_met_sql.sql"
    same_page.write_text(queries_file(PAGE_PATH, theirs), encoding="utf-8")
    messages.clear()
    page.once("dialog", lambda dialog: (messages.append(dialog.message), dialog.accept()))
    upload(page, same_page)
    expect(upload_status(page)).to_have_text("Teruggezet: cellen 1 en 2.")
    assert editor_values(page)[:2] == theirs
    assert len(messages) == 1 and "andere pagina" not in messages[0], messages


def test_upload_from_an_older_page_version_restores_what_matches(page, tmp_path) -> None:
    for i in range(3):
        click_startcode(page, i)
    untouched = "SELECT 'blijft staan' AS cel3;"
    set_editor(page, 2, untouched)  # eigen werk in cel 3, die niet in het bestand zit
    work = own_work("oud", 2)
    older = tmp_path / "queries-01_Starten_met_sql.sql"
    older.write_text(queries_file(PAGE_PATH, work) + "\n-- cel 99\nSELECT 99;\n", encoding="utf-8")

    upload(page, older)
    count = len(editor_values(page))
    expect(upload_status(page)).to_have_text(
        f"Teruggezet: cellen 1 en 2. Niet teruggezet: cel 99 — deze pagina heeft {count} cellen; "
        "het bestand komt wellicht van een oudere versie van de pagina."
    )
    values = editor_values(page)
    assert values[:2] == work
    assert values[2] == untouched


def test_upload_works_when_storage_is_blocked(page, site_url, tmp_path) -> None:
    """Geblokkeerde localStorage (strenge privacy-instellingen, zie #29): de
    upload zet de inhoud dan alleen live in de editors, zonder fouten."""
    context = page.context.browser.new_context()
    blocked = context.new_page()
    blocked.add_init_script(
        "Object.defineProperty(window, 'localStorage', { configurable: true, "
        "get() { throw new DOMException('localStorage is geblokkeerd', 'SecurityError'); } });"
    )
    errors: list[str] = []
    blocked.on("pageerror", lambda exc: errors.append(str(exc)))
    try:
        blocked.goto(site_url + PAGE)
        blocked.wait_for_function("() => window.sqlLive && window.sqlLive.dbReady === true")
        probe = "() => { try { window.localStorage; return 'open'; } catch (e) { return 'geblokkeerd'; } }"
        assert blocked.evaluate(probe) == "geblokkeerd"

        work = own_work("blok", 2)
        path = tmp_path / "queries-01_Starten_met_sql.sql"
        path.write_text(queries_file(PAGE_PATH, work), encoding="utf-8")
        upload(blocked, path)
        expect(upload_status(blocked)).to_have_text("Teruggezet: cellen 1 en 2.")
        assert editor_values(blocked)[:2] == work
        expect(blocked.locator(".sql-live-own").first).to_be_visible()
        assert errors == [], errors
    finally:
        context.close()
