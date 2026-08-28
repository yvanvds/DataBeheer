"""Structuurtests voor het boek: deelvolgorde, kruisverwijzingen en prev/next-flow (issue #36).

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


# --- tests op de gebouwde site (wat de leerling ziet) ----------------------


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
