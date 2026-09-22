"""Gedeelde pytest-configuratie voor tests/.

De tests slaan zichzelf over zodra iets in de omgeving ontbreekt: de gebouwde
site (book/_build/html), Node, Playwright of Chromium. Lokaal is dat handig,
maar in CI zou zo'n stille skip een groene run opleveren zonder dat er iets
getest is. Met TESTS_FAIL_ON_SKIP=1 telt elke skip daarom als failure; de
workflow .github/workflows/tests.yml zet die variabele aan (issue #39).

    TESTS_FAIL_ON_SKIP=1 pytest tests

Daarnaast bewaakt dit bestand dat de gebouwde site die de tests serveren
werkelijk de huidige bronbestanden bevat: klopt book/_build/html/_static niet
meer met book/_static, dan wordt de hele testrun afgebroken in plaats van
groen te draaien op oude editor-code (issue #54).
"""
from __future__ import annotations

import filecmp
import os
from pathlib import Path

import pytest

FAIL_ON_SKIP = os.environ.get("TESTS_FAIL_ON_SKIP", "").strip().lower() not in ("", "0", "false", "no")

ROOT = Path(__file__).resolve().parents[1]
STATIC_SOURCE = ROOT / "book" / "_static"
STATIC_BUILT = ROOT / "book" / "_build" / "html" / "_static"

#: Zoveel afwijkende bestanden noemen we in de foutmelding.
_MAX_REPORTED = 10


def _skip_as_failure(report) -> None:
    """Zet een skipped-rapport om in een failed-rapport, met de skip-reden als melding."""
    if not (FAIL_ON_SKIP and report.skipped) or hasattr(report, "wasxfail"):
        return
    longrepr = report.longrepr
    reason = longrepr[2] if isinstance(longrepr, tuple) and len(longrepr) == 3 else str(longrepr)
    report.outcome = "failed"
    report.longrepr = f"[TESTS_FAIL_ON_SKIP=1] overgeslagen test telt als failure: {reason}"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Skips tijdens setup (fixtures) of in de test zelf."""
    report = yield
    _skip_as_failure(report)
    return report


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector):
    """Skips op moduleniveau (pytest.importorskip, allow_module_level=True)."""
    report = yield
    _skip_as_failure(report)
    return report


# --- verouderde build luid laten falen (issue #54) --------------------------


def stale_static_files() -> list[str]:
    """Bestanden uit book/_static die in de build ontbreken of verouderd zijn.

    De e2e-tests serveren book/_build/html; staat daar een oudere kopie van
    sql-editors.js of de CodeMirror-bundel, dan testen ze code die niemand meer
    schrijft. Sphinx kopieert deze bestanden byte voor byte, dus elk verschil is
    een verouderde build. Overgeslagen, net als bij Sphinx zelf: verborgen
    bestanden en ``*_t``-sjablonen (die worden gerenderd, niet gekopieerd).

    Zonder build is de lijst leeg: de tests slaan zichzelf dan al over.
    """
    if not STATIC_BUILT.is_dir() or not STATIC_SOURCE.is_dir():
        return []
    stale = []
    for source in sorted(STATIC_SOURCE.rglob("*")):
        if not source.is_file() or source.name.endswith("_t"):
            continue
        relative = source.relative_to(STATIC_SOURCE)
        if any(part.startswith(".") for part in relative.parts):
            continue
        built = STATIC_BUILT / relative
        if not built.is_file():
            stale.append(f"{relative.as_posix()} (ontbreekt in de build)")
        elif not filecmp.cmp(source, built, shallow=False):
            stale.append(f"{relative.as_posix()} (verouderd in de build)")
    return stale


def pytest_collection_modifyitems(config, items):
    """Breek de run af zodra de gebouwde site niet meer bij de bron past.

    Een incrementele ``teachbooks build book`` sloeg de kopieerstap over zolang
    geen enkele pagina verouderd was, waardoor de tests stil groen draaiden op
    oude editor-code (issue #54). De build kopieert nu zelf bij
    (book/_ext/sync_static_assets.py); deze controle houdt dat afdwingbaar — ze
    kost een bytevergelijking van ~70 bestanden, enkele milliseconden.
    """
    stale = stale_static_files()
    if not stale:
        return
    listed = "\n".join(f"  - {entry}" for entry in stale[:_MAX_REPORTED])
    if len(stale) > _MAX_REPORTED:
        listed += f"\n  - ... en nog {len(stale) - _MAX_REPORTED} bestand(en)"
    raise pytest.UsageError(
        "book/_build/html/_static komt niet overeen met book/_static: de tests "
        "zouden op een verouderde kopie van de editor draaien (issue #54).\n"
        f"{listed}\n"
        "Bouw opnieuw met `teachbooks build book` en draai de tests daarna "
        "opnieuw."
    )
