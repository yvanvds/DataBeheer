"""Regeleindes in de werkmap: overal LF, net als in de repo (issue #56).

Zonder `.gitattributes` herschrijft git met `core.autocrlf=true` bij elke
checkout op Windows de LF-bytes van tekstbestanden naar CRLF. De geminifieerde
CodeMirror-bundel `book/_static/codemirror/codemirror.js` heeft geen lege
regels, dus die elf extra `\r`-bytes belanden middenin stringliteralen -- onder
meer in de standaard regelscheider van `sliceString(e,t=this.length,i=`\n`)`,
die dan `\r\n` wordt. GitHub Pages serveert de LF-versie uit de repo, dus de
editor die lokaal getest wordt is dan niet de editor die de leerling krijgt.
Dezelfde conversie maakt bovendien de bytevergelijking uit tests/conftest.py
(issue #54) na elke branchwissel vals alarm.

Twee lagen, want ze vangen verschillende dingen:

- de bytecontrole ziet het echte symptoom, maar alleen op een machine die
  converteert (Windows); op de Linux-runner is ze per definitie groen;
- de `git check-attr`-controles vragen git wat het met deze paden *zou* doen en
  falen daarom op elk platform zodra `.gitattributes` verdwijnt of de
  binaire assets er niet meer in staan.
"""
from __future__ import annotations

import functools
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: De gevendorde bundel uit de issue: geminified, dus elke \r landt in code.
CODEMIRROR = "book/_static/codemirror/codemirror.js"

#: Tekstbestanden die byte voor byte geserveerd worden of de build voeden.
#: git moet ze als tekst zien en met LF in de werkmap zetten.
TEXT_PATHS = [
    "book/_static/sql-editors.js",
    "book/_static/sql-statements.js",
    "book/_static/sql-queries-file.js",
    "book/_static/sql-worker.js",
    "book/_static/sql-editors.css",
    "book/_static/plink/tokens.css",
    "book/chapters/SQL/01_Starten_met_sql.ipynb",
    "book/_toc.yml",
    "tests/conftest.py",
]

#: Assets die git nooit mag aanraken: de gevendorde bundels worden byte voor
#: byte geserveerd, de rest is binair (SQLite-seeds, Excel, wasm, webfonts).
UNTOUCHED_PATHS = [
    CODEMIRROR,
    "book/_static/mathjax/loader.js",
    "book/_static/sqljs/sql-wasm.js",
    "book/_static/tippy/popper.min.js",
    "book/_static/db/adventureworks.db",
    "book/_static/db/webshop.db",
    "book/_static/excel/webshop_verkopen.xlsx",
    "book/_static/sqljs/sql-wasm.wasm",
]

NO_GIT = "git ontbreekt of dit is geen git-werkmap (nodig voor de regeleinde-controle)"


def _git(*args: str) -> str:
    if shutil.which("git") is None:
        pytest.skip(NO_GIT)
    proc = subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        pytest.skip(NO_GIT)
    return proc.stdout


@functools.lru_cache(maxsize=None)
def _check_attr(attribute: str, paths: tuple[str, ...]) -> dict[str, str]:
    """``git check-attr`` voor één attribuut, als {pad: waarde}."""
    out = _git("check-attr", attribute, "--", *paths)
    values = {}
    for line in out.splitlines():
        path, _, value = line.rpartition(f": {attribute}: ")
        if path:
            values[path] = value
    return values


# --- het symptoom uit de issue ---------------------------------------------


def test_codemirror_bundle_has_no_carriage_returns() -> None:
    """De gevendorde bundel bevat geen \r; anders draait de test andere code
    dan de site serveert (11 CRLF's voor de fix van issue #56)."""
    data = (ROOT / CODEMIRROR).read_bytes()
    assert b"\r" not in data, (
        f"{CODEMIRROR} bevat {data.count(chr(13).encode())} \r-bytes: git heeft de "
        "bundel bij het uitchecken naar CRLF herschreven. De werkmap draait dan op "
        "andere code dan GitHub Pages serveert (issue #56)."
    )


def test_tracked_text_files_use_lf_in_the_working_tree() -> None:
    """Geen enkel bijgehouden tekstbestand staat met CRLF in de werkmap.

    ``git ls-files --eol`` meldt per bestand wat er in de index staat (``i/``)
    en wat er werkelijk op schijf staat (``w/``). Binaire bestanden meldt git
    zelf als ``i/-text``; die slaan we over.
    """
    offenders = []
    for line in _git("ls-files", "--eol").splitlines():
        info, _, path = line.partition("\t")
        fields = info.split()
        if len(fields) < 2:
            continue
        index_eol, worktree_eol = fields[0], fields[1]
        if index_eol == "i/-text":
            continue
        if worktree_eol in ("w/crlf", "w/mixed"):
            offenders.append(f"{path} ({index_eol} -> {worktree_eol})")
    assert not offenders, (
        "deze bijgehouden bestanden staan met CRLF in de werkmap terwijl de repo LF "
        "bewaart; `.gitattributes` hoort dat te voorkomen (issue #56):\n  "
        + "\n  ".join(offenders[:20])
        + (f"\n  ... en nog {len(offenders) - 20} bestand(en)" if len(offenders) > 20 else "")
    )


# --- wat git met deze paden zou doen (platformonafhankelijk) ----------------


def test_gitattributes_exists() -> None:
    assert (ROOT / ".gitattributes").is_file(), (
        "zonder .gitattributes bepaalt core.autocrlf van de machine de regeleindes "
        "in de werkmap (issue #56)"
    )


@pytest.mark.parametrize("path", TEXT_PATHS)
def test_text_assets_are_checked_out_with_lf(path: str) -> None:
    assert _check_attr("eol", tuple(TEXT_PATHS)).get(path) == "lf", (
        f"{path}: git zet dit bestand niet gegarandeerd met LF in de werkmap; "
        "op Windows met core.autocrlf=true wordt het CRLF (issue #56)"
    )


@pytest.mark.parametrize("path", UNTOUCHED_PATHS)
def test_vendored_and_binary_assets_are_never_converted(path: str) -> None:
    """``text: unset`` (= ``-text``): git raakt de bytes nooit aan.

    De gevendorde bundels worden byte voor byte geserveerd en de
    SQLite-seeddatabases, het Excel-werkblad, de wasm-module en de webfonts
    zijn binair -- één \r erbij maakt ze stuk.
    """
    assert _check_attr("text", tuple(UNTOUCHED_PATHS)).get(path) == "unset", (
        f"{path}: git beschouwt dit niet als onaanraakbaar en mag de bytes dus "
        "herschrijven (issue #56)"
    )
