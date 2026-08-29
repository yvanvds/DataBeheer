"""Tests voor de interactieve SQL-editor: Run voert de selectie uit, of anders
het statement onder de cursor; "Run alles" voert de hele cel uit (issue #34).
"Download mijn queries" / "Upload mijn queries" bewaren het eigen werk van een
pagina als .sql-bestand en zetten het terug (issues #30/#35). De databank van
een pagina blijft in de browser bewaard (IndexedDB) en is met "Download mijn
databank" als .db-bestand te downloaden (issue #41). Daarop draaien de
bouwlessen van het ERD-deel (hoofdstuk 4 en 5, pagina's zonder seed) volledig
op de site (issue #42). De controlecel voor PRAGMA foreign_keys in ERD
hoofdstuk 1 loopt met "Run alles" en regel per regel zonder syntaxfout (issue
#43). De editor zet die bewaking zelf aan bij het openen van elke sessie, op
elke pagina en ook na Reset db, zodat de lessen er niet meer aan hoeven te
herinneren (issue #46). Het normalisatiehoofdstuk (ERD 2) draait van de eerste
tot de laatste cel op de site-editor (issue #49). Op een klein leerlingenscherm
laat "Groot scherm" één cel de hele viewport vullen (issue #48).

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
import sqlite3
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
    for module in ("sql-statements.js", "sql-queries-file.js", "sql-db-store.js"):
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


# --- e2e: de databank bewaren en downloaden (#41) ---------------------------

DB_BADGE = ".sql-live-own-db"  # label "eigen databank" in elke celtoolbar
work_status = upload_status  # dezelfde statusregel meldt ook opslagproblemen van de databank

# Pagina zonder sql-db-cel (lege startdatabank), afgeleid van de eerste
# SQL-pagina — zie no_seed_page_url.
NO_SEED_PAGE = "chapters/SQL/_test_zonder_seed.html"


def wait_ready(page) -> None:
    page.wait_for_function("() => window.sqlLive && window.sqlLive.dbReady === true")


def wait_db_saved(page, saved: bool) -> None:
    """Wacht tot de kopie in IndexedDB geschreven (True) of verwijderd (False) is."""
    page.wait_for_function("saved => window.sqlLive.dbSaved === saved", arg=saved)


def run_all(page, sql: str) -> None:
    """Zet `sql` in de eerste cel en klikt op "Run alles"."""
    load_sql(page, sql)
    cell(page).locator("button.runall").click()


def output(page):
    return cell(page).locator(".sql-live-output")


def db_badge(page):
    return page.locator(DB_BADGE).first


def download_database(page, tmp_path: Path) -> Path:
    with page.expect_download() as download:
        page.locator(WORK_BAR).locator("button.download-db").click()
    path = tmp_path / download.value.suggested_filename
    download.value.save_as(path)
    return path


def tables_in(path: Path) -> list[str]:
    """Tabelnamen in een gedownload .db-bestand, gelezen met Pythons sqlite3."""
    assert path.read_bytes()[:16] == b"SQLite format 3\x00", "geen SQLite-bestand"
    con = sqlite3.connect(path)
    try:
        return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    finally:
        con.close()


def saved_database_size(page) -> int | None:
    """Grootte van de kopie in IndexedDB voor deze pagina, of None als er geen staat."""
    return page.evaluate(
        """async () => {
            const names = (await indexedDB.databases()).map(d => d.name);
            if (!names.includes('sql-live')) return null;
            const db = await new Promise((ok, err) => {
                const req = indexedDB.open('sql-live', 1);
                req.onsuccess = () => ok(req.result);
                req.onerror = () => err(req.error);
            });
            try {
                if (!db.objectStoreNames.contains('databases')) return null;
                const record = await new Promise((ok, err) => {
                    const req = db.transaction('databases').objectStore('databases').get('db:' + location.pathname);
                    req.onsuccess = () => ok(req.result);
                    req.onerror = () => err(req.error);
                });
                return record ? record.bytes.length : null;
            } finally {
                db.close();
            }
        }"""
    )


@pytest.fixture(scope="module")
def no_seed_page_url(site_url):
    """Een pagina zonder sql-db-cel (lege startdatabank, zoals de bouwlessen van
    het ERD-deel): de eerste SQL-pagina met de tag van haar seed-cel uitgeschakeld.
    Tijdelijk in de build gezet, zodat alle relatieve paden (_static) werken."""
    text = (HTML / PAGE).read_text(encoding="utf-8")
    assert "tag_sql-db" in text, f"{PAGE} heeft geen sql-db-cel"
    derived = HTML / NO_SEED_PAGE
    derived.write_text(text.replace("tag_sql-db", "tag_sql-db-uit"), encoding="utf-8")
    try:
        yield site_url + NO_SEED_PAGE
    finally:
        derived.unlink(missing_ok=True)


def test_download_database_is_the_live_sqlite_file(page, tmp_path) -> None:
    """"Download mijn databank" levert het actuele SQLite-bestand: de seed
    (webshop.db) plus wat de leerling er zelf in bouwde — te openen met
    Pythons sqlite3, dus ook met DB Browser."""
    run_all(
        page,
        "CREATE TABLE mijn_tabel (id INTEGER PRIMARY KEY, naam TEXT);\n"
        "INSERT INTO mijn_tabel (naam) VALUES ('download');",
    )
    expect(output(page)).to_contain_text("OK")

    path = download_database(page, tmp_path)
    assert path.name == "databank-01_Starten_met_sql.db"
    assert tables_in(path) == ["customers", "mijn_tabel", "order_lines", "orders", "products"]
    con = sqlite3.connect(path)
    try:
        assert con.execute("SELECT naam FROM mijn_tabel").fetchall() == [("download",)]
        assert con.execute("SELECT count(*) FROM customers").fetchone()[0] > 0
    finally:
        con.close()

    # De export stoort de lopende databank niet.
    run_all(page, "SELECT count(*) AS na_download FROM mijn_tabel;")
    expect(result_headers(page)).to_have_text(["na_download"])
    expect(output(page).locator("td")).to_have_text(["1"])


def test_database_changes_survive_a_reload_until_reset_db(page) -> None:
    """Het scenario uit #41: tabellen bouwen, de pagina later heropenen en
    verder werken. "Reset db" gaat terug naar de startgegevens — en dat blijft
    zo na een herlaad."""
    run_all(
        page,
        "CREATE TABLE speler (id INTEGER PRIMARY KEY, naam TEXT);\n"
        "INSERT INTO speler (naam) VALUES ('Ine');",
    )
    expect(output(page)).to_contain_text("OK")
    expect(db_badge(page)).to_be_visible()  # "eigen databank"
    wait_db_saved(page, True)
    assert saved_database_size(page) > 0

    reload(page)
    expect(db_badge(page)).to_be_visible()  # hersteld uit de opslag, niet opnieuw geseed
    run_all(page, "SELECT naam AS speler_naam FROM speler;")
    expect(result_headers(page)).to_have_text(["speler_naam"])
    expect(output(page).locator("td")).to_have_text(["Ine"])

    cell(page).locator("button.reset").click()
    wait_ready(page)
    expect(db_badge(page)).to_be_hidden()
    wait_db_saved(page, False)
    assert saved_database_size(page) is None
    run_all(page, "SELECT naam FROM speler;")
    expect(output(page)).to_contain_text("no such table: speler")

    reload(page)
    expect(db_badge(page)).to_be_hidden()
    run_all(page, "SELECT naam FROM speler;")
    expect(output(page)).to_contain_text("no such table: speler")


def test_select_only_work_saves_no_copy_of_the_database(page) -> None:
    """Enkel bevragen (het hele SQL-deel) bewaart niets: een bijgewerkte seed
    komt dan gewoon door, en er staat geen kopie van elke seed in elke browser."""
    run_all(page, "SELECT 1 AS alleen_lezen;")
    expect(result_headers(page)).to_have_text(["alleen_lezen"])
    run_all(page, "UPDATE customers SET first_name = first_name WHERE 0;")  # wijzigt geen rij
    expect(output(page)).to_contain_text("OK")
    # Een snapshot zou vóór dit resultaat zijn aangekomen (berichten van de
    # worker komen in volgorde), dus dit is geen race.
    run_all(page, "SELECT 2 AS nog_steeds_alleen_lezen;")
    expect(result_headers(page)).to_have_text(["nog_steeds_alleen_lezen"])
    expect(db_badge(page)).to_be_hidden()
    assert page.evaluate("() => window.sqlLive.dbSaved") is False
    assert saved_database_size(page) is None


def test_foreign_keys_setting_survives_saving_the_database(page) -> None:
    """De bewaking van foreign keys is een instelling van de verbinding. Het
    bewaren van een snapshot sluit en heropent die verbinding (zo werkt
    db.export() in sql.js) en mag de instelling niet stilletjes uitzetten."""
    run_all(page, "CREATE TABLE fk_test (id INTEGER PRIMARY KEY);")  # wijziging → snapshot
    expect(output(page)).to_contain_text("OK")
    expect(db_badge(page)).to_be_visible()
    run_all(page, "PRAGMA foreign_keys;")
    expect(result_headers(page)).to_have_text(["foreign_keys"])
    expect(output(page).locator("td")).to_have_text(["1"])

    # Zet een leerling ze zelf uit, dan blijft dat zo over een snapshot heen.
    run_all(page, "PRAGMA foreign_keys = OFF;\nCREATE TABLE fk_test_uit (id INTEGER PRIMARY KEY);")
    expect(output(page)).to_contain_text("OK")
    run_all(page, "PRAGMA foreign_keys;")
    expect(output(page).locator("td")).to_have_text(["0"])

    cell(page).locator("button.reset").click()  # opruimen voor de volgende tests
    wait_ready(page)
    wait_db_saved(page, False)


def foreign_keys_are_on(target) -> None:
    """`PRAGMA foreign_keys;` in de eerste cel geeft 1 (de bewaking staat aan)."""
    run_all(target, FOREIGN_KEYS_CHECK)
    expect(result_headers(target)).to_have_text(["foreign_keys"])
    expect(output(target).locator("td")).to_have_text(["1"])


def test_foreign_keys_are_on_from_the_start_on_every_page(page, site_url) -> None:
    """Issue #46: de editor voert `PRAGMA foreign_keys = ON` zelf uit bij het
    openen van elke sessie, zodat de lessen er niet meer aan hoeven te
    herinneren. Op een vers geopende pagina (seed), na een herlaad (hersteld
    uit IndexedDB) en na Reset db geeft `PRAGMA foreign_keys;` dus `1` — en
    webshop.db weigert dan een bestelling voor een klant die niet bestaat, met
    een leesbare fout."""
    context, fresh = open_fresh(page, site_url, PAGE)
    try:
        foreign_keys_are_on(fresh)  # vers geopend, met seed

        # De bewaking doet ook echt haar werk: orders.customer_id verwijst naar customers.
        run_all(fresh, "INSERT INTO orders (customer_id, order_date, status) VALUES (999999, '2026-02-02', 'open');")
        expect(output(fresh)).to_contain_text("FOREIGN KEY constraint failed")

        run_all(fresh, "CREATE TABLE fk_bewaard (id INTEGER PRIMARY KEY);")  # eigen werk → wordt bewaard
        expect(output(fresh)).to_contain_text("OK")
        wait_db_saved(fresh, True)
        reload(fresh)
        expect(db_badge(fresh)).to_be_visible()  # hersteld uit IndexedDB, niet opnieuw geseed
        foreign_keys_are_on(fresh)

        cell(fresh).locator("button.reset").click()
        wait_ready(fresh)
        wait_db_saved(fresh, False)
        expect(db_badge(fresh)).to_be_hidden()
        foreign_keys_are_on(fresh)  # ook na Reset db
    finally:
        context.close()


def test_foreign_keys_are_on_when_the_page_has_no_seed(page, no_seed_page_url) -> None:
    """Issue #46: ook op een pagina zonder sql-db-cel — de lege startdatabank
    van de bouwlessen in het ERD-deel — staat de bewaking meteen aan."""
    context = page.context.browser.new_context()
    empty = context.new_page()
    try:
        empty.goto(no_seed_page_url)
        wait_ready(empty)
        foreign_keys_are_on(empty)
    finally:
        context.close()


def test_editor_and_download_work_when_indexeddb_is_blocked(page, site_url, tmp_path) -> None:
    """Geblokkeerde IndexedDB (strenge privacy-instellingen): bouwen en
    downloaden werken gewoon, alleen blijft er na een herlaad niets bewaard —
    en dat wordt gemeld, zonder pageerrors."""
    context = page.context.browser.new_context()
    blocked = context.new_page()
    blocked.add_init_script(
        "window.indexedDB.open = () => { throw new DOMException('IndexedDB is geblokkeerd', 'SecurityError'); };"
    )
    errors: list[str] = []
    blocked.on("pageerror", lambda exc: errors.append(str(exc)))
    try:
        blocked.goto(site_url + PAGE)
        wait_ready(blocked)
        run_all(
            blocked,
            "CREATE TABLE blok (id INTEGER PRIMARY KEY, naam TEXT);\n"
            "INSERT INTO blok (naam) VALUES ('geblokkeerd');",
        )
        expect(output(blocked)).to_contain_text("OK")
        expect(db_badge(blocked)).to_be_visible()  # de databank bevat eigen werk...
        expect(work_status(blocked)).to_contain_text("kon in deze browser niet bewaard worden")  # ...dat niet bewaard blijft

        path = download_database(blocked, tmp_path)  # de download werkt wel
        assert "blok" in tables_in(path)

        reload(blocked)
        expect(db_badge(blocked)).to_be_hidden()
        run_all(blocked, "SELECT naam FROM blok;")
        expect(output(blocked)).to_contain_text("no such table: blok")
        assert errors == [], errors
    finally:
        context.close()


def test_page_without_seed_starts_empty_and_keeps_what_you_build(page, no_seed_page_url, tmp_path) -> None:
    """Pagina zonder sql-db-cel: een lege startdatabank. Wat je bouwt blijft
    bewaard en is als .db-bestand te downloaden — het scenario van de
    bouwlessen in het ERD-deel."""
    context = page.context.browser.new_context()
    fresh = context.new_page()
    try:
        fresh.goto(no_seed_page_url)
        wait_ready(fresh)
        run_all(fresh, "SELECT name FROM sqlite_master WHERE type = 'table';")
        expect(output(fresh)).to_contain_text("geen resultaatrijen")  # leeg begonnen
        expect(db_badge(fresh)).to_be_hidden()

        run_all(
            fresh,
            "CREATE TABLE ploeg (id INTEGER PRIMARY KEY, naam TEXT);\n"
            "INSERT INTO ploeg (naam) VALUES ('Rood');",
        )
        expect(output(fresh)).to_contain_text("OK")
        wait_db_saved(fresh, True)

        reload(fresh)
        expect(db_badge(fresh)).to_be_visible()
        run_all(fresh, "SELECT naam FROM ploeg;")
        expect(output(fresh).locator("td")).to_have_text(["Rood"])

        path = download_database(fresh, tmp_path)
        assert path.name == "databank-_test_zonder_seed.db"
        assert tables_in(path) == ["ploeg"]
    finally:
        context.close()


# --- e2e: de bouwlessen van het ERD-deel (#42) -------------------------------

# ERD hoofdstuk 4 (de voetbal) en 5 (de cafetaria) bouwen een databank van nul
# op de site-editor: pagina's zonder sql-db-cel. Ze starten leeg, wat je bouwt
# blijft bewaard (#41) en "Download mijn databank" levert het in te dienen
# .db-bestand. De cafetaria-les wordt hier van fase 4 tot 7 gedraaid met de
# startcode van haar eigen cellen — de twee opdrachtcellen die de leerling
# zelf schrijft, krijgen een oplossing — en elke "wat moet je zien?"-claim
# van de les wordt nagekeken.
VOETBAL_PAGE = "chapters/ERD/04_de_voetbal.html"
CAFETARIA_PAGE = "chapters/ERD/05_de_cafetaria.html"

# Startcode-ankers van de opdrachtcellen in de cafetaria-les.
CAFETARIA_TASK_1 = "-- Fase 4, opdracht 1"
CAFETARIA_TASK_2 = "-- Fase 5, opdracht"

CAFETARIA_TABLES = """\
CREATE TABLE leerlingen (leerling_id INTEGER PRIMARY KEY, naam TEXT, klas TEXT);
CREATE TABLE producten (product_id INTEGER PRIMARY KEY, naam TEXT, prijs REAL);
CREATE TABLE bestellingen (bestelling_id INTEGER PRIMARY KEY, datum TEXT, status TEXT, leerling_id INTEGER);
CREATE TABLE bestelling_lijnen (bestellijn_id INTEGER PRIMARY KEY, bestelling_id INTEGER, product_id INTEGER, aantal INTEGER);
"""

CAFETARIA_TABLES_WITH_CONSTRAINTS = """\
CREATE TABLE leerlingen (
  leerling_id INTEGER PRIMARY KEY,
  naam TEXT NOT NULL CHECK (naam <> ''),
  klas TEXT NOT NULL
);
CREATE TABLE producten (
  product_id INTEGER PRIMARY KEY,
  naam TEXT NOT NULL CHECK (naam <> ''),
  prijs REAL NOT NULL CHECK (prijs >= 0)
);
CREATE TABLE bestellingen (
  bestelling_id INTEGER PRIMARY KEY,
  datum TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'betaald', 'geannuleerd')),
  leerling_id INTEGER NOT NULL
);
CREATE TABLE bestelling_lijnen (
  bestellijn_id INTEGER PRIMARY KEY,
  bestelling_id INTEGER NOT NULL,
  product_id INTEGER NOT NULL,
  aantal INTEGER NOT NULL CHECK (aantal > 0)
);
"""

TABLES_PROBE = "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name;"


def open_fresh(page, site_url: str, path: str):
    """Een nieuwe browsercontext (lege opslag) met de pagina geladen tot de database klaar is."""
    context = page.context.browser.new_context()
    fresh = context.new_page()
    fresh.goto(site_url + path)
    wait_ready(fresh)
    return context, fresh


def cell_at(page, index: int):
    return page.locator(".sql-live-wrap").nth(index)


def output_at(page, index: int):
    return cell_at(page, index).locator(".sql-live-output")


def find_cell(page, needle: str, exact: bool = False) -> int:
    """Index van de eerste cel waarvan de startcode `needle` bevat (of, met exact, precies is)."""
    index = page.evaluate(
        "([needle, exact]) => window.sqlLive.editors.findIndex("
        "e => exact ? e.initialValue === needle : e.initialValue.includes(needle))",
        [needle, exact],
    )
    assert index >= 0, f"geen cel met startcode die {needle!r} {'is' if exact else 'bevat'}"
    return index


def run_cell(page, index: int, sql: str | None = None):
    """Klikt "Run alles" in cel `index` (met de startcode, of met `sql` erin gezet) en geeft de uitvoer."""
    if sql is not None:
        set_editor(page, index, sql)
    cell_at(page, index).locator("button.runall").click()
    out = output_at(page, index)
    expect(out).not_to_contain_text("Bezig")
    return out


def probe(page, index: int, sql: str) -> str:
    """Voert `sql` uit in cel `index` en zet daarna de startcode van die cel terug."""
    text = run_cell(page, index, sql).inner_text()
    click_startcode(page, index)
    return text


def run_lines_one_by_one(page, index: int) -> dict[str, bool]:
    """Voert elke statementregel van cel `index` apart uit zoals de les vraagt
    (cursor op de regel, Ctrl+Enter — Run voert alleen dat statement uit) en
    geeft per regel of ze lukte."""
    outcomes: dict[str, bool] = {}
    for line in initial_values(page)[index].splitlines():
        if not line.strip() or line.lstrip().startswith("--"):
            continue
        cell_at(page, index).locator(".cm-line", has_text=re.compile(rf"^\s*{re.escape(line)}\s*$")).click()
        page.keyboard.press("Control+Enter")
        out = output_at(page, index)
        expect(out).not_to_contain_text("Bezig")
        outcomes[line] = "Fout:" not in out.inner_text()
    return outcomes


def failing_lines(outcomes: dict[str, bool]) -> list[str]:
    return [line for line, ok in outcomes.items() if not ok]


def row_count(path: Path, table: str) -> int:
    con = sqlite3.connect(path)
    try:
        return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


def test_voetbal_page_starts_empty_keeps_what_you_build_and_exports_it(page, site_url, tmp_path) -> None:
    """Hoofdstuk 4: een pagina zonder sql-db-cel start leeg; het voorbeeld uit
    stap 7 draait in de cellen zelf, overleeft een herlaad, wordt als
    databank-04_de_voetbal.db gedownload, en Reset db maakt de databank weer leeg."""
    context, fresh = open_fresh(page, site_url, VOETBAL_PAGE)
    try:
        own = find_cell(fresh, "-- Stap 7: jullie voetbaldatabank")  # de opdrachtcel, hier als proefcel
        assert "geen resultaatrijen" in probe(fresh, own, TABLES_PROBE)  # leeg begonnen
        expect(db_badge(fresh)).to_be_hidden()

        expect(run_cell(fresh, find_cell(fresh, "CREATE TABLE spelers"))).to_contain_text("OK")
        expect(run_cell(fresh, find_cell(fresh, "INSERT INTO spelers"))).to_contain_text("OK")
        expect(run_cell(fresh, find_cell(fresh, "UPDATE spelers"))).to_contain_text("OK")
        wait_db_saved(fresh, True)

        reload(fresh)
        expect(db_badge(fresh)).to_be_visible()  # hersteld uit de opslag
        assert "J. Peeters" in probe(fresh, own, "SELECT naam FROM spelers;")

        path = download_database(fresh, tmp_path)
        assert path.name == "databank-04_de_voetbal.db"
        assert tables_in(path) == ["spelers"]
        con = sqlite3.connect(path)
        try:
            assert con.execute("SELECT speler_id, naam FROM spelers").fetchall() == [(1, "J. Peeters")]
        finally:
            con.close()

        expect(run_cell(fresh, find_cell(fresh, "DROP TABLE spelers"))).to_contain_text("OK")
        assert "geen resultaatrijen" in probe(fresh, own, TABLES_PROBE)

        # Reset db op een pagina zonder seed: weer een lege databank, ook na herladen.
        cell_at(fresh, own).locator("button.reset").click()
        wait_ready(fresh)
        wait_db_saved(fresh, False)
        expect(db_badge(fresh)).to_be_hidden()
        reload(fresh)
        assert "geen resultaatrijen" in probe(fresh, own, TABLES_PROBE)
    finally:
        context.close()


def test_cafetaria_lesson_runs_end_to_end_on_the_site_editor(page, site_url, tmp_path) -> None:
    """Hoofdstuk 5 van fase 4 tot 7 op de site-editor: zonder constraints →
    met constraints → met foreign keys, met de startcode van de cellen zelf.
    Onderweg: de databank overleeft een herlaad, de controlecellen van 6.2 en
    7.0 bevestigen dat de editor foreign keys aan zette (#46), en de download
    is het volledige SQLite-bestand."""
    context, fresh = open_fresh(page, site_url, CAFETARIA_PAGE)
    try:
        task1 = find_cell(fresh, CAFETARIA_TASK_1)
        task2 = find_cell(fresh, CAFETARIA_TASK_2)
        pragma = find_cell(fresh, FOREIGN_KEYS_CHECK)  # 6.2, de controlecel
        pragma_again = find_cell(fresh, "-- Fase 7: controle vooraf")
        assert task1 < task2 < pragma < pragma_again
        last = len(initial_values(fresh)) - 1

        # Leeg begonnen: geen seed, geen tabellen.
        assert "geen resultaatrijen" in probe(fresh, task1, TABLES_PROBE)
        expect(db_badge(fresh)).to_be_hidden()

        # Fase 4 — zonder constraints: alles lukt, ook de foute gegevens.
        expect(run_cell(fresh, task1, CAFETARIA_TABLES)).to_contain_text("OK")
        drop_all = find_cell(
            fresh,
            "DROP TABLE bestelling_lijnen;\nDROP TABLE bestellingen;\nDROP TABLE producten;\nDROP TABLE leerlingen;",
            exact=True,
        )
        for index in range(task1 + 1, drop_all):
            out = run_cell(fresh, index)
            expect(out).not_to_contain_text("Fout:")
        overview = output_at(fresh, find_cell(fresh, "-- 3.1"))
        expect(overview.locator("span.sql-null")).not_to_have_count(0)  # bestelling voor leerling 999
        expect(output_at(fresh, find_cell(fresh, "-- 3.5")).locator("tbody tr")).to_have_count(6)
        wait_db_saved(fresh, True)

        # Herladen: de databank staat er nog (zoals tussen twee lessen).
        reload(fresh)
        expect(db_badge(fresh)).to_be_visible()
        assert "3" in probe(fresh, task1, "SELECT count(*) AS leerlingen FROM leerlingen;")
        assert "6" in probe(fresh, task1, "SELECT count(*) AS lijnen FROM bestelling_lijnen;")

        # Fase 5 — met constraints: precies de drie rijen uit de les worden geweigerd.
        expect(run_cell(fresh, drop_all)).to_contain_text("OK")
        expect(run_cell(fresh, task2, CAFETARIA_TABLES_WITH_CONSTRAINTS)).to_contain_text("OK")
        refused = []
        for needle in ("INSERT INTO leerlingen (naam, klas) VALUES ('Aya",
                       "INSERT INTO producten (naam, prijs) VALUES ('Kaasbroodje', 2.50);",
                       "INSERT INTO bestellingen (datum, status, leerling_id) VALUES ('2026-02-02', 'open', 1);\nINSERT INTO bestellingen (datum, status, leerling_id) VALUES ('2026-02-02', 'betaald', 2);\nINSERT INTO bestellingen (datum, status, leerling_id) VALUES ('2026-02-02', 'klaar', 3);",
                       "INSERT INTO bestelling_lijnen (bestelling_id, product_id, aantal) VALUES (3, 1, 0);"):
            refused += failing_lines(run_lines_one_by_one(fresh, find_cell(fresh, needle)))
        assert refused == [
            "INSERT INTO producten (naam, prijs) VALUES ('Chocomelk', -1.50);",
            "INSERT INTO bestellingen (datum, status, leerling_id) VALUES ('2026-02-02', 'klaar', 3);",
            "INSERT INTO bestelling_lijnen (bestelling_id, product_id, aantal) VALUES (3, 1, 0);",
        ], refused
        receipt = run_cell(fresh, find_cell(fresh, "-- 5.5"))
        expect(receipt.locator("span.sql-null")).not_to_have_count(0)  # leerling 999 en product 99 bestaan niet

        # Fase 6 — foreign keys: de controlecel bevestigt dat ze aan staan, en de verwijzingen worden bewaakt.
        expect(run_cell(fresh, pragma).locator("td")).to_have_text(["1"])
        expect(run_cell(fresh, find_cell(fresh, "DROP TABLE bestelling_lijnen;\nDROP TABLE bestellingen;", exact=True))).to_contain_text("OK")
        expect(run_cell(fresh, find_cell(fresh, "ON DELETE CASCADE"))).to_contain_text("OK")
        refused = []
        for needle in ("INSERT INTO bestellingen (datum, status, leerling_id) VALUES ('2026-02-02', 'betaald', 3);",
                       "INSERT INTO bestelling_lijnen (bestelling_id, product_id, aantal) VALUES (3, 1, 3);"):
            refused += failing_lines(run_lines_one_by_one(fresh, find_cell(fresh, needle)))
        assert refused == [
            "INSERT INTO bestellingen (datum, status, leerling_id) VALUES ('2026-02-02', 'open', 999);",
            "INSERT INTO bestelling_lijnen (bestelling_id, product_id, aantal) VALUES (2, 99, 1);",
            "INSERT INTO bestelling_lijnen (bestelling_id, product_id, aantal) VALUES (99, 1, 1);",
        ], refused
        cascade = run_cell(fresh, find_cell(fresh, "-- 6.7.1"))
        expect(cascade.locator("tbody tr")).to_have_count(2)  # de lijnen van bestelling 1 zijn mee verdwenen
        expect(run_cell(fresh, find_cell(fresh, "-- 6.7.2"))).to_contain_text("FOREIGN KEY constraint failed")
        expect(run_cell(fresh, find_cell(fresh, "-- 6.7.3"))).to_contain_text("FOREIGN KEY constraint failed")

        # Fase 7 — testen: geldige data lukt, de regels houden de rest tegen.
        expect(run_cell(fresh, pragma_again).locator("td")).to_have_text(["1"])
        for index in range(pragma_again + 1, find_cell(fresh, "-- 7.2")):
            expect(run_cell(fresh, index)).to_contain_text("OK")
        receipt = run_cell(fresh, find_cell(fresh, "-- 7.2"))
        expect(receipt.locator("tbody tr")).to_have_count(3)
        expect(receipt.locator("span.sql-null")).to_have_count(0)
        expect(run_cell(fresh, find_cell(fresh, "-- 7.3.1")).locator("td")).to_contain_text(["1", "betaald"])
        expect(run_cell(fresh, find_cell(fresh, "-- 7.3.2"))).to_contain_text("OK")
        expect(run_cell(fresh, find_cell(fresh, "-- 7.3.3"))).to_contain_text("CHECK constraint failed")
        expect(run_cell(fresh, find_cell(fresh, "-- 7.4.1")).locator("tbody tr")).to_have_count(1)
        expect(run_cell(fresh, find_cell(fresh, "-- 7.4.2"))).to_contain_text("FOREIGN KEY constraint failed")
        expect(run_cell(fresh, find_cell(fresh, "-- 7.4.3"))).to_contain_text("OK")
        expect(run_cell(fresh, last)).to_contain_text("FOREIGN KEY constraint failed")  # 7.4.4, de laatste cel
        wait_db_saved(fresh, True)

        # Indienen: het volledige SQLite-bestand, met schema, foreign keys en de gegevens van fase 7.
        path = download_database(fresh, tmp_path)
        assert path.name == "databank-05_de_cafetaria.db"
        assert tables_in(path) == ["bestelling_lijnen", "bestellingen", "leerlingen", "producten"]
        assert {t: row_count(path, t) for t in tables_in(path)} == {
            "leerlingen": 2, "producten": 3, "bestellingen": 1, "bestelling_lijnen": 1,
        }
        con = sqlite3.connect(path)
        try:
            fks = con.execute("PRAGMA foreign_key_list(bestelling_lijnen)").fetchall()
            assert sorted((fk[2], fk[6]) for fk in fks) == [("bestellingen", "CASCADE"), ("producten", "RESTRICT")], fks
        finally:
            con.close()
    finally:
        context.close()


# --- e2e: de foreign_keys-controle in ERD hoofdstuk 1 (#43, #46) ------------

# Hoofdstuk 1 bevraagt webshop.db (pagina mét seed). De cel bij §5 controleert
# PRAGMA foreign_keys. Ze bevatte `#`-commentaar, dat SQLite niet kent: met
# "Run alles" (en met Run zodra de cursor op zo'n regel stond) gaf sql.js een
# syntaxfout (#43). Sinds #46 zet de editor de bewaking zelf aan: de cel is
# een controle die meteen 1 geeft, en de instructie eromheen is weg.
ERD_INTRO_PAGE = "chapters/ERD/01_Inleiding_tot_ERD.html"
FOREIGN_KEYS_CHECK = "PRAGMA foreign_keys;"
FOREIGN_KEYS_ON = "PRAGMA foreign_keys = ON;"


def run_at_line(page, index: int, needle) -> None:
    """Klik (zoals een leerling) in de regel van cel `index` die `needle` bevat en druk op Ctrl+Enter."""
    cell_at(page, index).locator(".cm-line", has_text=needle).click()
    page.keyboard.press("Control+Enter")


def test_erd_intro_foreign_keys_cell_runs_without_syntax_error(page, site_url) -> None:
    """Op een vers geopende pagina geeft de controlecel meteen 1, zonder fout
    — met "Run alles" en met Run, ook met de cursor op de commentaarregel, die
    bij het statement erna hoort. De cel zet de instelling niet meer zelf aan."""
    context, fresh = open_fresh(page, site_url, ERD_INTRO_PAGE)
    try:
        index = find_cell(fresh, FOREIGN_KEYS_CHECK)
        assert FOREIGN_KEYS_ON not in initial_values(fresh)[index]  # #46: alleen nog een controle
        out = run_cell(fresh, index)
        expect(out).not_to_contain_text("Fout:")
        expect(out.locator("th")).to_have_text(["foreign_keys"])
        expect(out.locator("td")).to_have_text(["1"])  # de editor zette ze aan

        run_at_line(fresh, index, re.compile(r"^PRAGMA foreign_keys;$"))
        expect(out.locator("td")).to_have_text(["1"])
        run_at_line(fresh, index, "1 = aan, 0 = uit")  # commentaarregel: Run voert het statement erna uit
        expect(out.locator("td")).to_have_text(["1"])
        expect(out).not_to_contain_text("Fout:")
    finally:
        context.close()


# --- e2e: het normalisatiehoofdstuk (#46, #49) ------------------------------

# ERD hoofdstuk 2 bouwt uit de "brede" tabel orders_wide (seed webshop_bad.db)
# vier genormaliseerde tabellen. De foreign key van orders verwees naar
# customers(id) — een kolom die die tabel niet heeft; ze heet customer_id. Met
# de bewaking uit bleef dat onzichtbaar, met de bewaking aan weigert SQLite de
# INSERT met "foreign key mismatch" (#46). En §5.2 vulde de koppeltabel met
# `ow.price`, terwijl orders_wide die kolom `unit_price` noemt (#49). De les
# moet van begin tot eind blijven lopen; niets draaide ze tot nu toe uit.
NORMALISATIE_PAGE = "chapters/ERD/02_normalisatie.html"

# De werkende variant van 3.2, die de les zelf in commentaar meegeeft: de
# eerste poging (DISTINCT sku, name) botst op de UNIQUE-constraint — dat is
# het didactische punt van die paragraaf.
PRODUCTS_PER_SKU = """\
INSERT INTO products (sku, name)
SELECT product_sku,
       MIN(product_name) AS name
FROM orders_wide
GROUP BY product_sku;
"""


def build_customers_products_and_orders(fresh) -> None:
    """Stap 2 tot 4 van hoofdstuk 2 op de site-editor, met de startcode van de
    cellen zelf: de klanten- en productentabel vullen (de eerste poging bij de
    producten hoort te falen), en dan de orders-tabel aanmaken en vullen. Die
    laatste INSERT loopt alleen als de foreign key van orders naar een
    bestaande kolom van customers wijst (#46)."""
    expect(run_cell(fresh, find_cell(fresh, "CREATE TABLE customers ("))).to_contain_text("OK")
    expect(run_cell(fresh, find_cell(fresh, "INSERT INTO customers (email, name, city, postcode)"))).not_to_contain_text("Fout:")
    expect(run_cell(fresh, find_cell(fresh, "CREATE TABLE products ("))).to_contain_text("OK")

    products = find_cell(fresh, "INSERT INTO products (sku, name)")
    expect(run_cell(fresh, products)).to_contain_text("UNIQUE constraint failed")  # het punt van 3.2
    expect(run_cell(fresh, products, PRODUCTS_PER_SKU)).to_contain_text("OK")

    expect(run_cell(fresh, find_cell(fresh, "CREATE TABLE orders ("))).to_contain_text("OK")
    orders = run_cell(fresh, find_cell(fresh, "INSERT INTO orders (order_date, customer_id)"))
    expect(orders).not_to_contain_text("foreign key mismatch")
    expect(orders).to_contain_text("OK")


def test_normalisation_lesson_builds_its_tables_with_foreign_keys_on(page, site_url) -> None:
    """Stap 3 en 4 van hoofdstuk 2 op de site-editor. De INSERT in orders is de
    reden van deze test — ze loopt alleen als de foreign key van orders naar
    een bestaande kolom van customers wijst."""
    context, fresh = open_fresh(page, site_url, NORMALISATIE_PAGE)
    try:
        build_customers_products_and_orders(fresh)
        control = run_cell(fresh, find_cell(fresh, "SELECT * FROM orders;"))
        expect(control.locator("tbody tr")).to_have_count(4)
        expect(control.locator("span.sql-null")).to_have_count(0)  # elke bestelling heeft een klant
    finally:
        context.close()


# De prijzen van de vijf regels van orders_wide, in de volgorde waarin de
# INSERT van §5.2 ze in order_items schrijft. Ze staan hier voluit omdat net
# die kolom fout gelezen werd: een lege of verschoven kolom valt zo op.
ORDER_ITEM_PRICES = ["199.99", "12.5", "59", "69", "129.95"]


def test_normalisation_lesson_fills_order_items_from_the_wide_table(page, site_url) -> None:
    """Issue #49: stap 5 van hoofdstuk 2 op de site-editor. De INSERT van §5.2
    las `ow.price` uit orders_wide, maar die tabel noemt de prijskolom
    `unit_price` (`price` is de kolom in order_items zelf). De cel eindigde dus
    altijd op "no such column: ow.price": de controle in 5.3 bleef leeg en stap
    6 toonde een order_items zonder rijen. Met de juiste kolom loopt de reeks
    door tot het einde — vijf orderregels, met de prijzen uit de brede tabel."""
    context, fresh = open_fresh(page, site_url, NORMALISATIE_PAGE)
    try:
        build_customers_products_and_orders(fresh)
        expect(run_cell(fresh, find_cell(fresh, "CREATE TABLE order_items ("))).to_contain_text("OK")

        insert = find_cell(fresh, "INSERT INTO order_items (order_id, product_sku, quantity, price)")
        filled = run_cell(fresh, insert)
        expect(filled).not_to_contain_text("no such column")
        expect(filled).not_to_contain_text("Fout:")
        expect(filled).to_contain_text("OK")

        control = run_cell(fresh, find_cell(fresh, "SELECT * FROM order_items;"))
        expect(control.locator("th")).to_have_text(["order_id", "product_sku", "quantity", "price"])
        expect(control.locator("tbody tr")).to_have_count(5)
        expect(control.locator("tbody tr td:nth-child(4)")).to_have_text(ORDER_ITEM_PRICES)
        expect(control.locator("span.sql-null")).to_have_count(0)
    finally:
        context.close()


# --- e2e: schermvullende modus per cel (#48) --------------------------------

# De laptops van de leerlingen hebben een klein scherm; op 1366×768 blijft er
# tussen lestekst, sidebar en navigatie weinig over voor een langere query of
# een brede resultaattabel. De knop "Groot scherm" laat één cel de hele
# viewport vullen; de knop zelf of Esc brengt de gewone lay-out terug.
LAPTOP = {"width": 1366, "height": 768}
FULLSCREEN_BTN = "button.fullscreen"


@pytest.fixture(scope="module")
def laptop_page(page, site_url):
    """De eerste SQL-pagina in een eigen context op laptopformaat (1366×768)."""
    context = page.context.browser.new_context(viewport=LAPTOP)
    laptop = context.new_page()
    laptop.goto(site_url + PAGE)
    wait_ready(laptop)
    try:
        yield laptop
    finally:
        context.close()


def fullscreen_button(page, index: int = 0):
    return cell_at(page, index).locator(FULLSCREEN_BTN)


def box(locator) -> dict:
    b = locator.bounding_box()
    assert b is not None, "element is niet zichtbaar"
    return b


def page_scrolls(page) -> bool:
    """Scrollt de pagina mee als de leerling het muiswiel gebruikt? Bewust met
    een echte wielbeweging: `window.scrollTo` scrolt ook een pagina die met
    `overflow: hidden` op slot staat. De muis staat boven de lestekst bovenaan
    de pagina; in schermvullende stand ligt de cel daaroverheen."""
    before = page.evaluate("() => window.scrollY")
    page.evaluate("() => window.scrollTo(0, 0)")
    page.mouse.move(LAPTOP["width"] // 2, 400)
    page.mouse.wheel(0, 400)
    page.wait_for_timeout(250)
    moved = page.evaluate("() => window.scrollY") != 0
    page.evaluate("y => window.scrollTo(0, y)", before)
    return moved


def test_every_cell_has_a_fullscreen_button(laptop_page) -> None:
    """De knop staat in de balk van élke cel, naast Run / Run alles / Schema /
    Reset db, en staat bij het openen van de pagina uit."""
    cells = laptop_page.locator(".sql-live-wrap")
    expect(laptop_page.locator(f".sql-live-toolbar {FULLSCREEN_BTN}")).to_have_count(cells.count())
    btn = fullscreen_button(laptop_page)
    expect(btn).to_have_text("Groot scherm")
    expect(btn).to_have_attribute("aria-pressed", "false")


def test_fullscreen_fills_the_laptop_viewport_and_esc_restores(laptop_page) -> None:
    """Het scenario van #48 op een leerlingenlaptop: klikken op "Groot scherm"
    laat de cel de viewport vullen (editor én resultaatpaneel), Run werkt in
    die stand gewoon, de pagina eronder scrollt niet mee, en Esc zet de
    oorspronkelijke lay-out terug."""
    laptop_page.evaluate("() => window.scrollTo(0, 0)")
    wrap = cell(laptop_page)
    editor = wrap.locator(".sql-live-editor")
    normal, normal_editor = box(wrap), box(editor)
    assert normal["height"] < LAPTOP["height"], normal  # tussen de lestekst: klein
    assert page_scrolls(laptop_page), "de pagina scrolt normaal niet — test zegt niets"

    fullscreen_button(laptop_page).click()

    full = box(wrap)
    assert (round(full["x"]), round(full["y"])) == (0, 0), full
    assert (round(full["width"]), round(full["height"])) == (LAPTOP["width"], LAPTOP["height"]), full
    # De editor krijgt de resterende hoogte (toolbar en resultaatpaneel eraf).
    grown = box(editor)
    assert grown["height"] > normal_editor["height"] + 100, (normal_editor, grown)
    assert not page_scrolls(laptop_page), "de pagina achter de cel scrolt mee"

    # De cursor staat in de editor, dus de sneltoetsen werken meteen.
    assert laptop_page.evaluate("() => !!document.activeElement.closest('.sql-live-editor')")
    load_sql(laptop_page, three_statements("groot"))
    click_line(laptop_page, "SELECT 2")
    laptop_page.keyboard.press("Control+Enter")
    expect(result_headers(laptop_page)).to_have_text(["tweede_groot"])
    cell(laptop_page).locator("button.runall").click()
    expect(result_headers(laptop_page)).to_have_text(["eerste_groot", "tweede_groot", "derde_groot"])
    assert (round(box(wrap)["width"]), round(box(wrap)["height"])) == (LAPTOP["width"], LAPTOP["height"])

    laptop_page.keyboard.press("Escape")

    # Terug in de lestekst: dezelfde plek en breedte als daarnet, en weer een
    # gewone hoogte (het resultaatpaneel maakt de cel nu wel wat hoger).
    back = box(wrap)
    assert (round(back["x"]), round(back["width"])) == (round(normal["x"]), round(normal["width"])), back
    assert back["height"] < LAPTOP["height"], back
    assert page_scrolls(laptop_page), "de pagina scrolt na Esc niet opnieuw"
    expect(fullscreen_button(laptop_page)).to_have_text("Groot scherm")


def test_the_button_also_closes_and_the_result_panel_scrolls_on_its_own(laptop_page) -> None:
    """Dezelfde knop sluit weer (label en aria-pressed schakelen mee), en een
    lange resultaattabel scrollt in het paneel zelf zonder de pagina eronder
    mee te nemen."""
    laptop_page.evaluate("() => window.scrollTo(0, 0)")
    btn = fullscreen_button(laptop_page)
    btn.click()
    expect(btn).to_have_text("Klein scherm")
    expect(btn).to_have_attribute("aria-pressed", "true")

    run_all(laptop_page, "SELECT name, unit_price FROM products;")  # 41 rijen
    expect(result_headers(laptop_page)).to_have_text(["name", "unit_price"])
    panel = output(laptop_page)
    behind = laptop_page.evaluate("() => window.scrollY")
    scrolled = panel.evaluate(
        "el => { const room = el.scrollHeight - el.clientHeight; el.scrollTop = room; "
        "return { room, top: el.scrollTop }; }"
    )
    assert scrolled["room"] > 0, "het resultaatpaneel is niet hoger dan zijn venster"
    assert scrolled["top"] > 0, "het resultaatpaneel scrolt niet zelfstandig"
    assert laptop_page.evaluate("() => window.scrollY") == behind, "de pagina eronder schoof mee"

    btn.click()
    expect(btn).to_have_text("Groot scherm")
    expect(btn).to_have_attribute("aria-pressed", "false")
    assert round(box(cell(laptop_page))["height"]) < LAPTOP["height"]
    assert page_scrolls(laptop_page)


def test_schema_stays_reachable_and_esc_closes_it_before_the_fullscreen(laptop_page) -> None:
    """In schermvullende stand blijft Schema bereikbaar: het overlay komt over
    de cel heen. Esc sluit dan eerst het schema; pas de volgende Esc brengt de
    gewone lay-out terug."""
    btn = fullscreen_button(laptop_page)
    btn.click()
    expect(btn).to_have_attribute("aria-pressed", "true")

    cell(laptop_page).locator("button.schema").click()
    overlay = laptop_page.locator(".sql-schema-overlay")
    expect(overlay).to_be_visible()
    panel = overlay.locator(".sql-schema-panel")
    middle = box(panel)
    on_top = laptop_page.evaluate(
        "([x, y]) => !!document.elementFromPoint(x, y).closest('.sql-schema-overlay')",
        [round(middle["x"] + middle["width"] / 2), round(middle["y"] + middle["height"] / 2)],
    )
    assert on_top, "het schema-overlay ligt onder de schermvullende cel"

    laptop_page.keyboard.press("Escape")
    expect(overlay).to_be_hidden()
    expect(btn).to_have_attribute("aria-pressed", "true")  # de cel blijft schermvullend

    laptop_page.keyboard.press("Escape")
    expect(btn).to_have_attribute("aria-pressed", "false")
    assert page_scrolls(laptop_page)
