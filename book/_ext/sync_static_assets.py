"""Lokale Sphinx-extensie die gewijzigde eigen ``_static``-bestanden ook bij een
incrementele build naar de output kopieert (issue #54).

**Wat er misging.** ``Builder.build`` (sphinx/builders/__init__.py) keert bij een
update-build vroegtijdig terug zodra geen enkel document verouderd is::

    else:
        if method == 'update' and not docnames:
            logger.info(bold(__('no targets are out of date.')))
            return

Die ``return`` staat *vóór* ``self.finish()``, en ``copy_static_files`` is een
finish-taak. Een bestand onder ``book/_static`` telt niet als afhankelijkheid van
een document, dus wie alleen daar iets wijzigt (``sql-editors.js``, of de
CodeMirror-bundel na ``npm run build:editor``) krijgt een build die "succeeded"
meldt terwijl ``book/_build/html/_static`` de vorige versie houdt. De
Playwright-tests in ``tests/test_sql_editor.py`` serveren die map, dus die
draaiden dan op oude editor-code: een groene run die niets zegt.

**Wat deze extensie doet.** Op ``build-finished`` — dat Sphinx wél altijd
uitstuurt, ook na de vroege ``return`` (sphinx/application.py) — loopt ze de
eigen paden uit ``html_static_path`` na en kopieert elk bestand
waarvan de inhoud in de output afwijkt of ontbreekt. Dat zijn enkel de mappen van
het boek zelf (``_static`` en ``figures``); thema- en extensie-assets blijven
onaangeroerd, zodat de patches van ``_ext/harden_theme_storage.py`` op
``_static/scripts/pydata-sphinx-theme.js`` en co. blijven staan.

Overgeslagen, net als bij Sphinx zelf: verborgen bestanden (``**/.*``), paden uit
``exclude_patterns`` en ``*_t``-sjablonen (die rendert Sphinx, kopiëren zou een
extra bestand in de output zetten).

De controle is een bytevergelijking van een paar honderd bestanden en kost
milliseconden; er wordt alleen geschreven wat echt verschilt.
``tests/conftest.py`` bewaakt dezelfde gelijkheid vanuit de testkant, zodat een
verouderde build luid faalt in plaats van stil groen te zijn.
"""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

from sphinx.util import logging
from sphinx.util.matching import Matcher

__version__ = "1.0.0"

logger = logging.getLogger(__name__)


def _own_static_paths(app) -> list[Path]:
    """De statische mappen en losse bestanden van het boek zelf.

    ``html_static_path`` is relatief t.o.v. de map met ``_config.yml`` en mag
    zowel mappen als losse bestanden bevatten; Jupyter Book voegt ``_static``
    er automatisch aan toe.
    """
    paths = []
    for entry in app.config.html_static_path:
        path = (Path(app.confdir) / entry).resolve()
        if path.exists():
            paths.append(path)
    return paths


def _copy_if_different(source: Path, target: Path) -> bool:
    """Kopieer alleen wat in de output ontbreekt of afwijkt; True als gekopieerd."""
    if target.is_file() and filecmp.cmp(source, target, shallow=False):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    shutil.copystat(source, target)
    return True


def _sync_path(path: Path, target_root: Path, excluded: Matcher) -> list[str]:
    """Synchroniseer een map (recursief) of een los bestand; geef de paden terug."""
    if path.is_file():
        if path.name.endswith("_t") or path.name.startswith("."):
            return []
        return [path.name] if _copy_if_different(path, target_root / path.name) else []

    copied = []
    for source in sorted(path.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(path)
        posix = relative.as_posix()
        if excluded(posix) or source.name.endswith("_t"):
            continue
        if _copy_if_different(source, target_root / relative):
            copied.append(posix)
    return copied


def _sync_static(app, exception) -> None:
    if exception is not None or app.builder.format != "html":
        return
    target_root = Path(app.outdir) / "_static"
    if not target_root.is_dir():  # geen HTML-output om bij te werken
        return
    excluded = Matcher([*app.config.exclude_patterns, "**/.*"])

    copied = []
    for path in _own_static_paths(app):
        try:
            copied += _sync_path(path, target_root, excluded)
        except OSError as err:
            logger.warning(
                "sync_static_assets: kon %s niet synchroniseren met de build: %s",
                path,
                err,
            )
    if copied:
        logger.info(
            "sync_static_assets: %d gewijzigd(e) bestand(en) opnieuw gekopieerd "
            "naar _static (%s)",
            len(copied),
            ", ".join(copied[:5]) + (", ..." if len(copied) > 5 else ""),
        )


def setup(app):
    # priority=100: vóór harden_theme_storage (default 500), zodat die extensie
    # een bestand dat hier net opnieuw gekopieerd is meteen weer hardt.
    app.connect("build-finished", _sync_static, priority=100)
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
