"""Lokale Sphinx-extensie die de consolefouten op elke pagina wegneemt (issue #24).

1. Jupyter Book voegt elk ``*.js``-bestand onder ``_static`` toe aan
   ``html_js_files`` (``jupyter_book/config.py``, ``get_final_config``).
   Daardoor zouden de CodeMirror-bundel (ES-module), ``sqljs/sql-wasm.js``
   (UMD, verwacht een worker-context) en de module-/workerbestanden van de
   SQL-editor als klassieke ``<script>``-tags op elke pagina terechtkomen,
   met consolefouten ("Unexpected token 'export'", "importScripts is not
   defined") tot gevolg. ``_prune_static_js`` houdt alleen ``sql-editors.js``
   over — als ES-module (``type="module"``), zodat het de CodeMirror-bundel,
   ``sql-statements.js``, ``sql-queries-file.js``, ``sql-db-store.js`` en het
   overlay via ``import`` kan laden; de rest
   wordt on demand geladen via ``import()`` of ``new Worker(...)``.

2. Sphinx (t/m 7.x) zet inline scripts (``add_js_file(None, body=...)``) van
   extensies dubbel op de pagina: ``StandaloneHTMLBuilder.prepare_writing``
   registreert de registry-entries opnieuw met bestandsnaam ``''`` terwijl de
   eerdere kopie bestandsnaam ``None`` heeft, waardoor de dedup-check ze als
   verschillend ziet. Elke ``let``-declaratie van de TeachBooks-extensies
   (thebe-, dual-button- en accessibility-vertalingen) stond daardoor twee
   keer op elke pagina, met "Identifier '...' has already been declared" als
   gevolg.

3. ``jupyterbook_patches`` registreert ``mathjax_patch.js`` twee keer: één
   keer rechtstreeks via ``add_js_file`` (op elke pagina) en één keer als
   ``mathjax_path`` (defer, alleen op pagina's met wiskunde). Het script laadt
   MathJax vanaf de CDN, dus op wiskundepagina's initialiseerde MathJax
   dubbel: "Cannot set property Package of #<Object> which has only a getter".
   We laten alleen de ``mathjax_path``-kopie (met ``defer``) staan.

4. De TeachBooks-fork van sphinx-thebe (0.3.1) registreert ``thebe.css`` maar
   levert dat bestand niet mee, wat een 404 in de console gaf op elke pagina.
   De dode verwijzing wordt verwijderd (thebe/live code wordt in dit boek
   niet gebruikt).
"""

from __future__ import annotations

__version__ = "1.0.0"

# Paginascripts uit book/_static die we bewust behouden. sql-editors.js is
# een ES-module (importeert de CodeMirror-bundel) en krijgt type="module".
_KEEP_JS_MODULE = {
    "sql-editors.js",  # bootstrapt de SQL-editors; laadt de rest zelf
}

# Relatieve paden die geen klassiek paginascript zijn. tippy/ en mathjax/
# (issue #28) bevatten gevendorde bibliotheken die gericht geladen worden:
# popper/tippy via de tippy_js-config van teachbooks_sphinx_tippy, MathJax
# via mathjax_path (zie _ext/vendor_mathjax.py).
_DROP_PREFIXES = ("codemirror/", "sqljs/", "tippy/", "mathjax/")
_DROP_JS = {
    "sql-overlay.js",  # ES-module, dynamisch geimporteerd door sql-editors.js
    "sql-statements.js",  # ES-module, statisch geimporteerd door sql-editors.js (#34)
    "sql-queries-file.js",  # ES-module, statisch geimporteerd door sql-editors.js (#30/#35)
    "sql-db-store.js",  # ES-module, statisch geimporteerd door sql-editors.js (#41)
    "sql-worker.js",   # workerscript, gestart via new Worker(...)
}

# CSS-verwijzingen die naar niet-bestaande bestanden wijzen (zie punt 4).
_DROP_CSS = {"_static/thebe.css"}


def _prune_static_js(app, config):
    """Haal auto-toegevoegde _static-bestanden uit ``html_js_files`` (punt 1)."""
    kept = []
    for entry in config.html_js_files:
        filename = entry[0] if isinstance(entry, (tuple, list)) else entry
        if isinstance(filename, str) and "://" not in filename:
            if filename in _KEEP_JS_MODULE:
                # Herregistreer als ES-module (Sphinx zet het type-attribuut
                # op de <script>-tag; modules zijn impliciet deferred).
                kept.append((filename, {"type": "module"}))
                continue
            if filename in _DROP_JS or filename.startswith(_DROP_PREFIXES):
                continue
        kept.append(entry)
    config.html_js_files[:] = kept


def _asset_key(asset):
    # Normaliseer None/'' zodat de dubbel geregistreerde inline scripts
    # (zie moduledocstring, punt 2) dezelfde sleutel krijgen.
    return (
        str(asset.filename or ""),
        asset.priority,
        tuple(sorted(asset.attributes.items())),
    )


def _clean_js(assets):
    seen = set()
    unique = []
    for asset in assets:
        # Punt 3: alleen de defer-kopie van mathjax_patch.js behouden.
        if (
            str(asset.filename or "").endswith("mathjax_patch.js")
            and "defer" not in asset.attributes
        ):
            continue
        key = _asset_key(asset)
        if key not in seen:
            seen.add(key)
            unique.append(asset)
    return unique


def _fix_page_assets(app, pagename, templatename, context, doctree):
    builder = app.builder
    for attr in ("_js_files", "_orig_js_files"):
        assets = getattr(builder, attr, None)
        if assets:
            assets[:] = _clean_js(assets)
    for attr in ("_css_files", "_orig_css_files"):
        assets = getattr(builder, attr, None)
        if assets:
            assets[:] = [a for a in assets if str(a.filename) not in _DROP_CSS]


def setup(app):
    app.connect("config-inited", _prune_static_js)
    # priority=0: opschonen voordat andere extensies paginascripts toevoegen
    # (zoals sphinx.ext.mathjax, dat op wiskundepagina's de defer-kopie van
    # mathjax_patch.js toevoegt).
    app.connect("html-page-context", _fix_page_assets, priority=0)
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
