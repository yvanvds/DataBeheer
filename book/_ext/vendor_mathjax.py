"""Lokale Sphinx-extensie die MathJax uit de gevendorde kopie laadt (issue #28).

``jupyterbook_patches`` zet ``mathjax_path`` bij ``builder-inited`` hard op
``mathjax_patch.js`` (zie ``patches/mathjax_patch.py`` in dat package), een
loaderscript dat MathJax at runtime van ``cdn.jsdelivr.net`` haalt — op elke
pagina. Achter een schoolfirewall die CDN's blokkeert (of offline) faalt die
request, hetzelfde risico dat issue #16/#17 voor de SQL-editor wegnam door
CodeMirror te vendoren.

Deze extensie overschrijft ``mathjax_path`` daarom *na* jupyterbook_patches
(zelfde event, hogere priority) met ``mathjax/loader.js``: een lokaal
loaderscript met hetzelfde gedrag (Firefox → SVG-uitvoer, anders CHTML) dat de
gevendorde MathJax 3.2.2-bundel uit ``_static/mathjax/`` laadt. De dubbele,
niet-deferred registratie van ``mathjax_patch.js`` werd al opgeruimd door
``sanitize_static_assets`` (issue #24); die extensie houdt nu ook de
gevendorde mathjax-bestanden uit de automatische paginascript-injectie van
Jupyter Book.

Ontbreekt een van de gevendorde bestanden, dan volgt een build-warning (en
breekt dus de 0-warnings-baseline), zodat stille drift zichtbaar wordt.
"""

from __future__ import annotations

from pathlib import Path

from sphinx.util import logging

__version__ = "1.0.0"

logger = logging.getLogger(__name__)

#: mathjax_path relatief t.o.v. _static; sphinx.ext.mathjax voegt dit script
#: (met ``defer``) toe op elke pagina, net zoals mathjax_patch.js voorheen.
_LOCAL_MATHJAX_PATH = "mathjax/loader.js"

#: Gevendorde bestanden die het loaderscript nodig heeft (relatief t.o.v.
#: book/_static). De woff2-fontmap wordt als geheel gecontroleerd.
_REQUIRED = (
    "mathjax/loader.js",
    "mathjax/tex-mml-chtml.js",   # CHTML-uitvoer (alle browsers behalve Firefox)
    "mathjax/tex-mml-svg.js",     # SVG-uitvoer (Firefox, zie loader.js)
    "mathjax/ui/lazy.js",         # door jupyterbook_patches geconfigureerd (loader.load)
    "mathjax/output/chtml/fonts/woff-v2",  # CHTML-webfonts (map)
)


def _use_vendored_mathjax(app):
    static_dir = Path(app.srcdir, "_static")
    missing = [rel for rel in _REQUIRED if not (static_dir / rel).exists()]
    if missing:
        logger.warning(
            "vendor_mathjax: gevendorde MathJax-bestanden ontbreken onder "
            "_static: %s — mathjax_path blijft op de CDN-loader staan",
            ", ".join(missing),
        )
        return
    app.config.mathjax_path = _LOCAL_MATHJAX_PATH


def setup(app):
    # priority=600: ná set_mathjax_path van jupyterbook_patches (default 500),
    # zodat onze waarde wint.
    app.connect("builder-inited", _use_vendored_mathjax, priority=600)
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
