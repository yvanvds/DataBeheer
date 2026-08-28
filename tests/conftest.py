"""Gedeelde pytest-configuratie voor tests/.

De tests slaan zichzelf over zodra iets in de omgeving ontbreekt: de gebouwde
site (book/_build/html), Node, Playwright of Chromium. Lokaal is dat handig,
maar in CI zou zo'n stille skip een groene run opleveren zonder dat er iets
getest is. Met TESTS_FAIL_ON_SKIP=1 telt elke skip daarom als failure; de
workflow .github/workflows/tests.yml zet die variabele aan (issue #39).

    TESTS_FAIL_ON_SKIP=1 pytest tests
"""
from __future__ import annotations

import os

import pytest

FAIL_ON_SKIP = os.environ.get("TESTS_FAIL_ON_SKIP", "").strip().lower() not in ("", "0", "false", "no")


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
