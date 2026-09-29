"""CITATION.cff en README.md beschrijven deze cursus, niet de TeachBooks-template (issue #70).

Beide bestanden kwamen ongewijzigd uit de template: GitHub toonde onder "Cite
this repository" de TeachBooks Template met teachbooks.github.io/template als
adres, en de README was de handleiding van de template. De tests hier houden
ze gelijk met de rest van de repo:

- het adres in CITATION.cff is html_baseurl uit book/_config.yml, de site van
  main in /DataBeheer/main/ (zonder /main/ een 404, issue #67), en de
  repository is repository_url uit dezelfde configuratie;
- titel, taal, auteur en licentie komen overeen met het boek en LICENSE;
- de README noemt het adres van de site en de delen in de volgorde van
  _toc.yml, en elk pad, commando en skill dat ze noemt, bestaat.

Deze tests lezen alleen bronbestanden, geen build.
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "book"
CITATION = ROOT / "CITATION.cff"
README = ROOT / "README.md"

#: Sporen van de TeachBooks-template die in geen van beide bestanden horen.
TEMPLATE_LEFTOVERS = [
    "TeachBooks Template",
    "TeachBooks Development Team",
    "teachbooks.github.io/template",
    "info@teachbooks.io",
    "dummydocent",
    "use the template",
    "<Book title>",
]


@functools.cache
def config() -> dict:
    return yaml.safe_load((BOOK / "_config.yml").read_text(encoding="utf-8"))


@functools.cache
def citation() -> dict:
    return yaml.safe_load(CITATION.read_text(encoding="utf-8"))


@functools.cache
def readme() -> str:
    return README.read_text(encoding="utf-8")


def sphinx_config() -> dict:
    return config()["sphinx"]["config"]


def site() -> str:
    return sphinx_config()["html_baseurl"]


def repository() -> str:
    return sphinx_config()["html_theme_options"]["repository_url"]


def toc_parts() -> list[str]:
    toc = yaml.safe_load((BOOK / "_toc.yml").read_text(encoding="utf-8"))
    return [part["caption"] for part in toc["parts"]]


# --- CITATION.cff -----------------------------------------------------------


def test_citation_url_is_the_main_site() -> None:
    cff = citation()
    urls = {
        "url": cff.get("url"),
        "preferred-citation.url": cff["preferred-citation"].get("url"),
    }
    wrong = {key: value for key, value in urls.items() if value != site()}
    assert not wrong, f"CITATION.cff wijst niet naar html_baseurl {site()!r}: {wrong}"


def test_citation_points_to_this_repository() -> None:
    cff = citation()
    repos = {
        "repository-code": cff.get("repository-code"),
        "preferred-citation.repository-code": cff["preferred-citation"].get("repository-code"),
    }
    wrong = {key: value for key, value in repos.items() if value != repository()}
    assert not wrong, f"CITATION.cff wijst niet naar repository_url {repository()!r}: {wrong}"
    identifiers = {entry["value"] for entry in cff["preferred-citation"].get("identifiers", [])}
    assert identifiers == {site(), repository()}, f"identifiers in CITATION.cff: {sorted(identifiers)}"


def test_citation_title_and_language_match_the_book() -> None:
    cff = citation()
    title = sphinx_config()["html_theme_options"]["logo"]["text"]
    assert cff["title"] == cff["preferred-citation"]["title"] == title, (
        f"titel in CITATION.cff: {cff['title']!r} / {cff['preferred-citation']['title']!r}, in het boek: {title!r}"
    )
    language = sphinx_config()["language"]
    assert cff["preferred-citation"].get("languages") == [language], (
        f"languages in CITATION.cff: {cff['preferred-citation'].get('languages')}, taal van het boek: {language!r}"
    )


def test_citation_author_and_license_match_the_book() -> None:
    cff = citation()
    book_author = config()["author"].split(",")[0].strip()
    for key, authors in (("authors", cff["authors"]), ("preferred-citation.authors", cff["preferred-citation"]["authors"])):
        names = [f"{a.get('given-names', '')} {a.get('family-names', '')}".strip() for a in authors]
        assert names == [book_author], f"{key} in CITATION.cff: {names}, auteur van het boek: {book_author!r}"
    assert cff["license"] == cff["preferred-citation"]["license"] == "CC-BY-4.0"
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("Attribution 4.0 International")


def test_citation_and_readme_have_no_template_leftovers() -> None:
    found = [
        f"{path.name}: {phrase!r}"
        for path in (CITATION, README)
        for phrase in TEMPLATE_LEFTOVERS
        if phrase.lower() in path.read_text(encoding="utf-8").lower()
    ]
    assert not found, f"nog tekst uit de TeachBooks-template: {found}"


# --- README.md --------------------------------------------------------------


def test_readme_names_the_site() -> None:
    assert site() in readme(), f"README.md noemt het adres van de site {site()!r} niet"


def test_readme_lists_parts_in_toc_order() -> None:
    listed = re.findall(r"^\d+\. \*\*(.+?)\*\*", readme(), flags=re.MULTILINE)
    assert [t.lower() for t in listed] == [t.lower() for t in toc_parts()], (
        f"README.md beschrijft de delen als {listed}, _toc.yml als {toc_parts()}"
    )


def _fenced_blocks(text: str) -> list[str]:
    return re.findall(r"^```[^\n]*\n(.*?)^```", text, flags=re.MULTILINE | re.DOTALL)


def _inline_code(text: str) -> list[str]:
    without_blocks = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
    return re.findall(r"`([^`\n]+)`", without_blocks)


def test_readme_paths_exist() -> None:
    """Elk pad tussen backticks bestaat (behalve de build, die je zelf maakt)."""
    paths = [code for code in _inline_code(readme()) if " " not in code and "/" in code and not code.startswith("/")]
    assert paths, "README.md noemt geen paden meer"
    missing = [p for p in paths if not p.startswith("book/_build") and not (ROOT / p).exists()]
    assert not missing, f"README.md noemt paden die niet bestaan: {missing}"


def test_readme_skills_exist() -> None:
    skills = [code[1:] for code in _inline_code(readme()) if re.fullmatch(r"/[a-z-]+", code)]
    assert set(skills) >= {"leerdoelen", "rubriek", "overhoring"}, f"skills in README.md: {skills}"
    missing = [s for s in skills if not (ROOT / ".claude" / "skills" / s / "SKILL.md").is_file()]
    assert not missing, f"README.md noemt skills zonder .claude/skills/<naam>/SKILL.md: {missing}"


def test_readme_commands_exist() -> None:
    commands = [line.split("#")[0].strip() for block in _fenced_blocks(readme()) for line in block.splitlines()]
    commands = [c for c in commands if c]
    for expected in ("teachbooks build book", "pytest tests", "npm run build:editor"):
        assert expected in commands, f"README.md noemt `{expected}` niet in een codeblok: {commands}"
    scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    for command in commands:
        if m := re.fullmatch(r"npm run (\S+)", command):
            assert m.group(1) in scripts, f"README.md: `{command}`, maar package.json heeft geen script {m.group(1)!r}"
        if m := re.fullmatch(r"pip install -r (\S+)", command):
            assert (ROOT / m.group(1)).is_file(), f"README.md: `{command}`, maar {m.group(1)} bestaat niet"
