"""Tests voor de interactieve SQL-editor (issue #34): Run voert de selectie uit,
of anders het statement onder de cursor; "Run alles" voert de hele cel uit.

Twee lagen:

- de statementgrenzen (book/_static/sql-statements.js) hebben unit-tests in
  Node — tests/sql-statements.test.mjs — die hier via ``node --test`` draaien;
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
NODE_TESTS = ROOT / "tests" / "sql-statements.test.mjs"

# Eerste pagina met interactieve cellen (tag sql-live) en een seed-database.
PAGE = "chapters/SQL/01_Starten_met_sql.html"

NO_BUILD = "book/_build/html ontbreekt; bouw eerst met `teachbooks build book`"


# --- unit-tests van de statementgrenzen (Node) ----------------------------


def test_statement_boundaries_unit_tests_pass_in_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node ontbreekt (nodig voor tests/sql-statements.test.mjs)")
    proc = subprocess.run(
        [node, "--test", "--test-reporter=tap", str(NODE_TESTS)],
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
    assert (HTML / "_static" / "sql-statements.js").is_file(), "sql-statements.js niet in de build"
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
