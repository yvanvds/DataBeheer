"""De metadata van de repo beschrijven deze cursus, niet de TeachBooks-template (issues #70, #71).

CITATION.cff en README.md kwamen ongewijzigd uit de template: GitHub toonde
onder "Cite this repository" de TeachBooks Template met
teachbooks.github.io/template als adres, en de README was de handleiding van de
template (issue #70). package.json had de beschrijving van de template en wat
`npm init` invult (licentie ISC, geen auteur, een test-script dat altijd faalt),
en CODEOWNERS noemde een maintainer van de template als eigenaar (issue #71).
De tests hier houden die bestanden gelijk met de rest van de repo:

- het adres in CITATION.cff is html_baseurl uit book/_config.yml, de site van
  main in /DataBeheer/main/ (zonder /main/ een 404, issue #67), en de
  repository is repository_url uit dezelfde configuratie;
- titel, taal, auteur en licentie komen overeen met het boek en LICENSE;
- de README noemt het adres van de site en de delen in de volgorde van
  _toc.yml, en elk pad, commando en skill dat ze noemt, bestaat;
- package.json en de wortel van package-lock.json hebben dezelfde auteur,
  licentie, site en repository als het boek, de beschrijving is het begin van
  de samenvatting in CITATION.cff, en elk npm-script noemt bestaande bestanden:
  `npm test` draait de Node-unittests in tests/*.test.mjs;
- CODEOWNERS noemt de eigenaar van de repository.

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
PACKAGE = ROOT / "package.json"
PACKAGE_LOCK = ROOT / "package-lock.json"
CODEOWNERS = ROOT / "CODEOWNERS"

#: Sporen van de TeachBooks-template en van `npm init` die in geen van deze
#: bestanden horen.
TEMPLATE_LEFTOVERS = [
    "TeachBooks Template",
    "TeachBooks Development Team",
    "teachbooks.github.io/template",
    "info@teachbooks.io",
    "dummydocent",
    "use the template",
    "<Book title>",
    "start your own TeachBook",
    "Tom-van-Woudenberg",
    "no test specified",
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


@functools.cache
def package() -> dict:
    return json.loads(PACKAGE.read_text(encoding="utf-8"))


def sphinx_config() -> dict:
    return config()["sphinx"]["config"]


def site() -> str:
    return sphinx_config()["html_baseurl"]


def repository() -> str:
    return sphinx_config()["html_theme_options"]["repository_url"]


def repository_owner() -> str:
    match = re.fullmatch(r"https://github\.com/([^/]+)/[^/]+", repository())
    assert match, f"repository_url is geen GitHub-repository: {repository()!r}"
    return match.group(1)


def book_author() -> str:
    """De auteur van het boek, zonder de TeachBooks- en licentievermelding erachter."""
    return config()["author"].split(",")[0].strip()


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
    for key, authors in (("authors", cff["authors"]), ("preferred-citation.authors", cff["preferred-citation"]["authors"])):
        names = [f"{a.get('given-names', '')} {a.get('family-names', '')}".strip() for a in authors]
        assert names == [book_author()], f"{key} in CITATION.cff: {names}, auteur van het boek: {book_author()!r}"
    assert cff["license"] == cff["preferred-citation"]["license"] == "CC-BY-4.0"
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("Attribution 4.0 International")


def test_repo_metadata_has_no_template_leftovers() -> None:
    found = [
        f"{path.name}: {phrase!r}"
        for path in (CITATION, README, PACKAGE, CODEOWNERS)
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


# --- package.json -----------------------------------------------------------


def test_package_describes_the_course() -> None:
    """De beschrijving is het begin van de samenvatting in CITATION.cff."""
    description = package().get("description", "")
    abstract = " ".join(citation()["abstract"].split())
    assert description.endswith(".") and abstract.startswith(description[:-1]), (
        f"package.json beschrijft de repo als {description!r}; dat is geen begin van de samenvatting "
        f"in CITATION.cff: {abstract!r}"
    )


def test_package_author_license_and_homepage_match_the_book() -> None:
    pkg = package()
    assert pkg.get("author") == book_author(), (
        f"author in package.json: {pkg.get('author')!r}, auteur van het boek: {book_author()!r}"
    )
    assert pkg.get("license") == citation()["license"] == "CC-BY-4.0", (
        f"license in package.json: {pkg.get('license')!r}, in CITATION.cff: {citation()['license']!r}"
    )
    assert pkg.get("homepage") == site(), f"homepage in package.json: {pkg.get('homepage')!r}, site: {site()!r}"


def test_package_points_to_this_repository() -> None:
    pkg = package()
    assert pkg.get("repository") == {"type": "git", "url": f"git+{repository()}.git"}, pkg.get("repository")
    assert pkg.get("bugs") == {"url": f"{repository()}/issues"}, pkg.get("bugs")


def test_package_is_private() -> None:
    """npm bouwt hier alleen de editorbundel: het pakket wordt nooit gepubliceerd en is geen module."""
    pkg = package()
    assert pkg.get("private") is True, 'package.json mist "private": true'
    assert "main" not in pkg or (ROOT / pkg["main"]).is_file(), f"main in package.json bestaat niet: {pkg['main']!r}"


def test_package_lock_root_matches_package() -> None:
    """Wie package.json aanpast, werkt ook package-lock.json bij (npm install --package-lock-only)."""
    lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    pkg = package()
    root = lock["packages"][""]
    differ = {
        key: (root.get(key), pkg.get(key))
        for key in ("name", "version", "license", "dependencies", "devDependencies")
        if root.get(key) != pkg.get(key)
    }
    differ |= {f"lock.{key}": (lock.get(key), pkg.get(key)) for key in ("name", "version") if lock.get(key) != pkg.get(key)}
    assert not differ, f"package-lock.json (links) volgt package.json (rechts) niet: {differ}"


def test_package_scripts_name_existing_files() -> None:
    missing = []
    for name, command in package()["scripts"].items():
        for arg in command.split()[1:]:
            path = arg.split("=", 1)[-1]
            if "/" not in path:
                continue
            exists = any(ROOT.glob(path)) if any(c in path for c in "*?[") else (ROOT / path).exists()
            if not exists:
                missing.append(f"{name}: {path}")
    assert not missing, f"npm-scripts noemen bestanden die niet bestaan: {missing}"


def test_npm_test_runs_all_node_unit_tests() -> None:
    """`npm test` is niet de stub van npm init, maar draait elke tests/*.test.mjs."""
    command = package()["scripts"].get("test", "")
    words = command.split()
    assert words[:2] == ["node", "--test"], f"npm test in package.json: {command!r}"
    run = {path for pattern in words[2:] for path in ROOT.glob(pattern)}
    expected = set((ROOT / "tests").glob("*.test.mjs"))
    assert expected and run == expected, (
        f"npm test draait {sorted(p.name for p in run)}, tests/ heeft {sorted(p.name for p in expected)}"
    )


# --- CODEOWNERS -------------------------------------------------------------


def test_codeowners_is_the_repository_owner() -> None:
    rules = [
        line.split()
        for line in CODEOWNERS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    owners = {owner for rule in rules for owner in rule[1:]}
    assert rules and owners == {f"@{repository_owner()}"}, (
        f"CODEOWNERS noemt {sorted(owners)}, eigenaar van de repository: @{repository_owner()}"
    )
