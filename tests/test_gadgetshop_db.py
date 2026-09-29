"""Tests voor gadgetshop.db, de databank van de overhoringen (issue #61).

De databank wordt gemaakt door scripts/generate_gadgetshop_db.py. Die tests
bewaken drie dingen:

- de gecommitte databank is precies wat het script maakt (deterministisch, met
  een vaste seed): wie het script aanpast en vergeet opnieuw te draaien, of de
  databank met de hand wijzigt, ziet het hier;
- de databank doorstaat de controles onderaan het script (wat de overhoringen
  nodig hebben: LIKE-patronen, NULL, datums als tekst, geldige foreign keys,
  kleiner dan 1 MB, ...), en die controles vangen echt iets op;
- book/overhoringen/README.md beschrijft de tabellen, kolommen en aantallen
  zoals ze in de databank staan: de auteurs van de overhoringen (#63, #64)
  lezen daar het schema.

Dat de cursus de databank niet gebruikt en dat de overhoringpagina ze laadt,
staat in tests/test_overhoringen.py.

    pytest tests/test_gadgetshop_db.py
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_gadgetshop_db.py"
DB = ROOT / "book" / "_static" / "db" / "gadgetshop.db"
README = ROOT / "book" / "overhoringen" / "README.md"
TABLES = ["brands", "categories", "products", "customers", "orders", "order_items", "reviews"]


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_gadgetshop_db", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_generator()


def dump(path: Path) -> list[str]:
    con = sqlite3.connect(path)
    try:
        return list(con.iterdump())
    finally:
        con.close()


def test_committed_database_is_what_the_script_makes(tmp_path) -> None:
    fresh = tmp_path / "gadgetshop.db"
    generator.build(fresh)
    committed, made = dump(DB), dump(fresh)
    assert len(committed) == len(made), "aantal rijen verschilt: draai scripts/generate_gadgetshop_db.py opnieuw"
    diff = [(a, b) for a, b in zip(committed, made) if a != b][:5]
    assert not diff, f"de gecommitte databank wijkt af van het script: {diff}"


def test_committed_database_passes_the_checks_of_the_script() -> None:
    counts = generator.verify(DB)
    assert list(counts) == TABLES
    assert DB.stat().st_size < 1_000_000


def test_foreign_keys_hold_with_the_editor_setting() -> None:
    """De editor zet PRAGMA foreign_keys aan (#46): elke rij moet dan geldig zijn,
    en een bestelling voor een onbestaande klant wordt geweigerd."""
    con = sqlite3.connect(DB)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        declared = {
            (table, row[2], row[3], row[4])
            for table in TABLES
            for row in con.execute(f"PRAGMA foreign_key_list({table})")
        }
        assert declared == {
            ("categories", "categories", "parent_category_id", "category_id"),
            ("products", "brands", "brand_id", "brand_id"),
            ("products", "categories", "category_id", "category_id"),
            ("orders", "customers", "customer_id", "customer_id"),
            ("order_items", "orders", "order_id", "order_id"),
            ("order_items", "products", "product_id", "product_id"),
            ("reviews", "products", "product_id", "product_id"),
            ("reviews", "customers", "customer_id", "customer_id"),
        }
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO orders VALUES (99999, 99999, '2026-08-31', 'pending', "
                        "'paypal', 'standard', NULL, NULL)")
    finally:
        con.rollback()
        con.close()


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param("UPDATE customers SET city = 'Gent' WHERE city = 'gent'", id="geen-stad-in-kleine-letters"),
        pytest.param("UPDATE products SET color = '' WHERE color IS NULL", id="lege-tekst-in-plaats-van-null"),
        pytest.param("UPDATE orders SET order_date = '01/09/2023' WHERE order_id = 10001", id="datum-niet-als-yyyy-mm-dd"),
        pytest.param("UPDATE orders SET shipped_date = NULL WHERE order_id = "
                     "(SELECT MIN(order_id) FROM orders WHERE status = 'delivered')", id="geleverd-zonder-verzenddatum"),
        pytest.param("INSERT INTO order_items VALUES (10001, 9999, 1, 9.99, 0)", id="ongeldige-foreign-key"),
        pytest.param("UPDATE reviews SET verified_purchase = 1 WHERE review_id = "
                     "(SELECT MIN(review_id) FROM reviews WHERE verified_purchase = 0)", id="review-zonder-aankoop-als-geverifieerd"),
        pytest.param("UPDATE products SET model_code = model_code || 'X' WHERE product_id = 1", id="modelcode-andere-lengte"),
        pytest.param("UPDATE customers SET email = 'jan.claes2@skynet.be' WHERE customer_id = "
                     "(SELECT MAX(customer_id) FROM customers WHERE email = 'jan.claes@skynet.be')",
                     id="geen-dubbel-emailadres"),
    ],
)
def test_the_checks_catch_a_broken_database(tmp_path, mutation) -> None:
    """De asserts van het script zijn geen versiering: elke eigenschap uit de
    issue die hier verdwijnt, doet verify() falen."""
    broken = tmp_path / "gadgetshop.db"
    shutil.copyfile(DB, broken)
    con = sqlite3.connect(broken)  # foreign keys uit: zo kan de fout erin
    con.execute(mutation)
    con.commit()
    con.close()
    with pytest.raises(AssertionError):
        generator.verify(broken)


def readme_tables() -> dict[str, tuple[list[str], int]]:
    """{tabel: (kolommen, rijen)} uit de tabel in book/overhoringen/README.md."""
    text = README.read_text(encoding="utf-8")
    section = text[text.index("## De databank: gadgetshop.db"):]
    section = section[: section.index("\n## ", 1)]
    rows = re.findall(r"^\| (\w+) \| ([\w, ]+) \| ([\d.]+) \|$", section, flags=re.MULTILINE)
    return {table: ([c.strip() for c in cols.split(",")], int(n.replace(".", ""))) for table, cols, n in rows}


def test_readme_describes_the_tables_as_they_are() -> None:
    described = readme_tables()
    assert list(described) == TABLES
    con = sqlite3.connect(DB)
    try:
        actual = {
            table: ([r[1] for r in con.execute(f"PRAGMA table_info({table})")],
                    con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in TABLES
        }
    finally:
        con.close()
    assert described == actual
