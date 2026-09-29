"""Lokale Sphinx-extensie voor de overhoringen (issue #60).

Een overhoring is een notebook in ``book/overhoringen/<naam>/``. Ze wordt mee
gepubliceerd met de cursus (de deploy-workflow bouwt alleen ``book/``), maar
staat er los van: niet in ``_toc.yml``, geen link van of naar de cursus, niet
vindbaar via Zoeken, en met een eigen uiterlijk, zodat de leraar vanop afstand
ziet wanneer een leerling tijdens de overhoring de cursus opent. Het
authoringformaat staat in ``book/overhoringen/README.md``.

**Welke bestanden een pagina worden.** Elke notebook op precies dit niveau:
``overhoringen/<naam>/<pagina>.ipynb`` (gewoonlijk ``overhoring.ipynb``). De
rest van de map — ``leerdoelen.md``, ``rubriek.csv``, een README — wordt geen
pagina. Een nieuwe overhoringmap vraagt geen aanpassing van de configuratie.

**Waarom een extensie.** ``_config.yml`` zet ``external_toc_exclude_missing:
true``: sphinx-external-toc zet dan elk bronbestand dat niet in ``_toc.yml``
staat in ``exclude_patterns`` (``parse_toc_to_env``, op ``config-inited`` met
prioriteit 900). Die instelling uitzetten zou elk los bestand van het boek
bouwen (``Untitled.ipynb``, maar ook ``leerdoelen.md`` in elke overhoringmap).
Deze extensie haalt daarom, net ná sphinx-external-toc, alleen de
overhoringnotebooks weer uit ``exclude_patterns``. Ze in ``_toc.yml`` zetten kan
niet: dan staan ze in de zijbalk en in de vorige/volgende-keten van de cursus.

**Wat de extensie per overhoringpagina doet.**

- Ze markeert de pagina als *orphan* (geen waarschuwing "document isn't
  included in any toctree"); zonder toctree-plaats heeft ze ook geen
  vorige/volgende.
- Ze houdt de pagina volledig uit de zoekindex van de site
  (``searchindex.js``): de HTML-builder slaat ze over bij het indexeren.
- Ze rendert de pagina met een eigen sjabloon (``_ext/templates/overhoring.html``)
  in plaats van het gewone paginasjabloon. Lege ``html_sidebars`` volstaan
  niet: ook het logo, het zoekvenster (Ctrl+K, een formulier naar
  ``search.html``), de knoppen in de artikelheader (repository, issues,
  bewerken, .ipynb downloaden), vorige/volgende, de inhoudstafel rechts en de
  voettekst linken naar de cursus of naar GitHub. Het sjabloon toont alleen een
  vaste band "Overhoring" en het artikel, en zet de klasse ``overhoring`` op
  ``<html>``: daar haakt ``_static/overhoring.css`` op in.
- Ze laadt ``_static/overhoring.css`` en de module ``_static/overhoring.js``
  alleen op die pagina (``_ext/sanitize_static_assets.py`` houdt ze van de
  andere pagina's weg) en geeft het script de vragen mee als JSON: de
  Markdown-bron van de doelen en van elke vraag, zodat "Download mijn
  antwoorden" de vragen letterlijk kan overnemen.

Fouten tegen het formaat (een vraag zonder antwoordcel, een codecel zonder
overhoringtag, ...) geven een build-warning; ``tests/test_overhoringen.py``
controleert elke overhoringnotebook met dezelfde parser.
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from sphinx.util import logging

__version__ = "1.0.0"

logger = logging.getLogger(__name__)

#: Map onder book/ met één submap per overhoring.
QUIZ_ROOT = "overhoringen"
#: Standaardnaam van de overhoringnotebook in een overhoringmap.
DEFAULT_PAGE = "overhoring"
#: Sjabloon waarmee de overhoringpagina's gerenderd worden (in _ext/templates/).
TEMPLATE = "overhoring.html"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
#: Paginabestanden uit book/_static, alleen op overhoringpagina's geladen.
CSS_FILE = "overhoring.css"
JS_FILE = "overhoring.js"

#: Tag van een codecel -> vraagtype. `sql-live` is de gewone SQL-editor.
ANSWER_TAGS = {
    "sql-live": "sql",
    "overhoring-open": "open",
    "overhoring-mc": "mc",
}
#: Codecel met het pad naar de databank van de pagina (zie sql-editors.js).
SEED_TAG = "sql-db"
#: Cellen met deze tags laat MyST-NB weg uit de pagina (bv. notities voor de auteur).
REMOVE_TAGS = {"remove-cell", "remove_cell"}

_QUIZ_SOURCE = re.compile(rf"^{QUIZ_ROOT}/[^/.][^/]*/[^/.][^/]*\.ipynb$")
_QUIZ_DOCNAME = re.compile(rf"^{QUIZ_ROOT}/[^/.][^/]*/[^/.][^/]*$")
_TITLE = re.compile(r"^#\s+(?P<text>\S.*?)\s*$")
_H2 = re.compile(r"^##\s+(?P<text>\S.*?)\s*$")
_DOELEN = re.compile(r"^Doelen$", re.IGNORECASE)
_VRAAG = re.compile(r"^Vraag\s+(?P<nummer>\d+)\b")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,}|:{3,})")


# --- welke bestanden overhoringen zijn -------------------------------------


def is_quiz_source(path: str) -> bool:
    """``overhoringen/<naam>/<pagina>.ipynb``, relatief t.o.v. book/ (POSIX)."""
    return bool(_QUIZ_SOURCE.match(path))


def is_quiz_docname(docname: str) -> bool:
    return bool(_QUIZ_DOCNAME.match(docname))


def quiz_id(docname: str) -> str:
    """Naam van de overhoring, voor de bestandsnaam van de antwoorden.

    ``overhoringen/sql-h1-h2/overhoring`` -> ``sql-h1-h2``; een tweede
    notebook in dezelfde map (bv. een parallelversie ``groep-b.ipynb``) krijgt
    haar eigen naam erbij: ``sql-h1-h2-groep-b``.
    """
    _, folder, page = PurePosixPath(docname).parts
    return folder if page == DEFAULT_PAGE else f"{folder}-{page}"


# --- het formaat van een overhoringnotebook --------------------------------


def _tags(cell: dict) -> list[str]:
    return list(cell.get("metadata", {}).get("tags", []))


def _source(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def _clean(lines: list[str]) -> str:
    return "\n".join(lines).strip("\n").rstrip()


def parse_quiz(notebook: dict) -> tuple[dict, list[str]]:
    """Lees een overhoringnotebook in volgens het formaat uit
    ``book/overhoringen/README.md``.

    Geeft ``(quiz, fouten)`` terug. ``quiz`` heeft de sleutels ``title``,
    ``doelen`` (Markdown) en ``questions``: per vraag ``heading`` (de kop
    zonder ``##``), ``number``, ``text`` (Markdown), ``type`` (``sql``,
    ``open`` of ``mc``), ``placeholder`` (open vraag) en ``options``
    (meerkeuze). De antwoordcellen staan in dezelfde volgorde op de pagina,
    zodat ``overhoring.js`` ze op volgorde aan hun vraag koppelt.
    """
    errors: list[str] = []
    title = ""
    doelen: list[str] | None = None
    questions: list[dict] = []
    target: list[str] | None = None  # buffer waar markdownregels nu heen gaan

    for index, cell in enumerate(notebook.get("cells", []), start=1):
        tags = _tags(cell)
        if REMOVE_TAGS.intersection(tags):
            continue
        where = f"cel {index}"
        if not _source(cell).strip():
            # MyST-NB laat lege cellen weg uit de pagina: een lege antwoordcel
            # zou er dus niet staan.
            if cell.get("cell_type") == "code" and any(tag in ANSWER_TAGS for tag in tags):
                errors.append(
                    f"{where}: lege antwoordcel; MyST-NB laat lege cellen weg, zet er startcode, "
                    "een hulptekst of de opties in"
                )
            continue
        if cell.get("cell_type") == "markdown":
            in_fence = None
            for line in _source(cell).splitlines():
                fence = _FENCE.match(line)
                if fence and in_fence is None:
                    in_fence = fence.group(1)[0]
                elif fence and fence.group(1)[0] == in_fence:
                    in_fence = None
                if in_fence is None and not fence:
                    h1, h2 = _TITLE.match(line), _H2.match(line)
                    if h1 and not title:
                        title, target = h1.group("text"), None
                        continue
                    if h2:
                        heading = h2.group("text")
                        vraag = _VRAAG.match(heading)
                        if _DOELEN.match(heading):
                            doelen = []
                            target = doelen
                        elif vraag:
                            target = []
                            questions.append({
                                "heading": heading,
                                "number": int(vraag.group("nummer")),
                                "lines": target,
                                "type": None,
                            })
                        else:
                            target = None  # een andere sectie (bv. instructies): niet in de download
                        continue
                if target is not None:
                    target.append(line)
            continue

        if cell.get("cell_type") != "code":
            continue
        if SEED_TAG in tags:
            continue
        kinds = [ANSWER_TAGS[tag] for tag in tags if tag in ANSWER_TAGS]
        if len(kinds) != 1:
            errors.append(
                f"{where}: een codecel op een overhoringpagina heeft precies één van de tags "
                f"{', '.join(sorted(ANSWER_TAGS))} (of {SEED_TAG}); gevonden: {tags or 'geen tags'}"
            )
            continue
        if not questions or questions[-1]["type"] is not None:
            errors.append(f"{where}: antwoordcel ({kinds[0]}) zonder eigen '## Vraag n'-kop erboven")
            continue
        question = questions[-1]
        question["type"] = kinds[0]
        target = None  # tekst na de antwoordcel hoort niet meer bij de vraag
        text = _source(cell)
        if kinds[0] == "mc":
            options = [line.strip() for line in text.splitlines() if line.strip()]
            if len(options) < 2:
                errors.append(f"{where}: meerkeuzevraag '{question['heading']}' heeft minder dan twee opties")
            if len(set(options)) != len(options):
                errors.append(f"{where}: meerkeuzevraag '{question['heading']}' heeft dubbele opties")
            question["options"] = options
        elif kinds[0] == "open":
            question["placeholder"] = text.strip()

    if not title:
        errors.append("geen titel: de pagina begint met een markdowncel '# <titel>'")
    if doelen is None or not _clean(doelen):
        errors.append("geen doelen: zet de leerdoelen onder een kop '## Doelen'")
    if not questions:
        errors.append("geen vragen: elke vraag begint met een kop '## Vraag n'")
    numbers = [q["number"] for q in questions]
    if numbers != list(range(1, len(questions) + 1)):
        errors.append(f"de vragen zijn niet doorlopend genummerd vanaf 1: {numbers}")
    for question in questions:
        if question["type"] is None:
            errors.append(f"'{question['heading']}' heeft geen antwoordcel")
        if not _clean(question["lines"]):
            errors.append(f"'{question['heading']}' heeft geen vraagtekst")

    quiz = {
        "title": title,
        "doelen": _clean(doelen or []),
        "questions": [
            {
                "heading": q["heading"],
                "number": q["number"],
                "text": _clean(q["lines"]),
                "type": q["type"],
                **({"options": q["options"]} if "options" in q else {}),
                **({"placeholder": q["placeholder"]} if "placeholder" in q else {}),
            }
            for q in questions
        ],
    }
    return quiz, errors


def read_quiz(path: Path) -> tuple[dict, list[str]]:
    return parse_quiz(json.loads(Path(path).read_text(encoding="utf-8")))


def quiz_json(quiz: dict, docname: str) -> str:
    """De gegevens voor overhoring.js, veilig om in een <script>-blok te zetten."""
    data = {"id": quiz_id(docname), **quiz}
    text = json.dumps(data, ensure_ascii=False)
    # Geen "</script>" of "<!--" in de inline JSON: < > & als \u-escapes.
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


# --- Sphinx-events ---------------------------------------------------------


def _include_quiz_pages(app, config):
    """Haal de overhoringnotebooks weer uit ``exclude_patterns`` (na
    sphinx-external-toc, prioriteit 900) en registreer het sjabloon."""
    patterns = list(config.exclude_patterns)
    kept = [p for p in patterns if not (isinstance(p, str) and is_quiz_source(p))]
    if len(kept) != len(patterns):
        config.exclude_patterns = kept
    if str(TEMPLATES_DIR) not in config.templates_path:
        config.templates_path = [*config.templates_path, str(TEMPLATES_DIR)]


def _mark_quiz_page(app, doctree):
    """Orphan (geen toctree-waarschuwing) en controle van het formaat."""
    docname = app.env.docname
    if not is_quiz_docname(docname):
        return
    app.env.metadata[docname]["orphan"] = True
    _, errors = read_quiz(Path(app.env.doc2path(docname)))
    for error in errors:
        logger.warning("overhoring: %s", error, location=docname)


def _skip_search_index(app):
    """Overhoringpagina's komen niet in searchindex.js (ook niet als lege
    vermelding, zoals bij de metadata ``nosearch``)."""
    builder = app.builder
    original = getattr(builder, "index_page", None)
    if original is None:
        return

    def index_page(pagename, *args, **kwargs):
        if is_quiz_docname(pagename):
            return None
        return original(pagename, *args, **kwargs)

    builder.index_page = index_page


def _render_quiz_page(app, pagename, templatename, context, doctree):
    if not is_quiz_docname(pagename) or doctree is None:
        return None
    quiz, _ = read_quiz(Path(app.env.doc2path(pagename)))
    context["overhoring_id"] = quiz_id(pagename)
    context["overhoring_data"] = quiz_json(quiz, pagename)
    # Alleen op deze pagina (Sphinx >= 3.5: toegevoegd tijdens html-page-context).
    app.add_css_file(CSS_FILE)
    app.add_js_file(JS_FILE, type="module")
    return TEMPLATE


def setup(app):
    # Na sphinx-external-toc (900), dat de ontbrekende bestanden uitsluit.
    app.connect("config-inited", _include_quiz_pages, priority=950)
    app.connect("doctree-read", _mark_quiz_page)
    app.connect("builder-inited", _skip_search_index)
    app.connect("html-page-context", _render_quiz_page)
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
