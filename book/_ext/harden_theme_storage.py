"""Lokale Sphinx-extensie die de opslag-consolefouten van de theme-assets wegneemt (issue #29, omvat #26).

De gevendorde theme/extensie-scripts die met de TeachBooks-template meekwamen
(commit c44066d) gebruiken ``localStorage``/``sessionStorage`` zonder enige
foutafhandeling. Dat geeft drie soorten consolefouten:

1. **Eerste bezoek** (leeg localStorage): het inline mode-bootstrapscript van
   pydata-sphinx-theme zet ``document.documentElement.dataset.mode`` op een
   lege string, waarna ``setTheme("")`` in ``pydata-sphinx-theme.js`` een
   ``console.error`` "Got invalid theme mode: . Resetting to auto." logt (#26).
2. **Geblokkeerde opslag** (bv. strenge privacy-instellingen): elke toegang
   tot ``window.localStorage`` gooit een ``SecurityError``. Ongevangen
   pageerrors uit het inline bootstrapscript, ``sphinx_highlight.js``,
   ``Accessibility.js`` en ``pydata-sphinx-theme.js``.
3. **Volle opslag**: ``setItem`` gooit ``QuotaExceededError``, ongevangen in
   ``pydata-sphinx-theme.js``.

Omdat deze bestanden bij elke build opnieuw uit de geinstalleerde packages
worden gekopieerd, patcht deze extensie de *build-output* (``build-finished``),
zodat de fix elke rebuild overleeft:

- Het inline bootstrapscript in elke HTML-pagina wordt vervangen door een
  geharde versie die (a) veilige storage-wrappers definieert
  (``window.plinkSafeStorage``: try/catch rond elke native call, met een
  in-memory fallback zodat de themavoorkeur binnen de pagina blijft werken
  als schrijven niet kan) en (b) een lege/ongeldige mode meteen naar een
  geldige waarde normaliseert, zodat ``setTheme`` nooit meer een ongeldige
  mode ziet.
- In de gevendorde scripts die opslag gebruiken worden de kale
  ``localStorage``/``sessionStorage``-referenties herschreven naar die
  wrappers. Een shim op ``window.localStorage`` zelf is niet genoeg: als de
  browser de property als niet-configureerbare getter blokkeert, valt er
  runtime niets meer te overschrijven.

De vervangingen zijn idempotent en de extensie waarschuwt (en breekt dus de
0-warnings-baseline) wanneer een verwacht patroon na een theme-upgrade niet
meer voorkomt, zodat stille drift zichtbaar wordt bij de build.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from sphinx.util import logging

__version__ = "1.0.0"

logger = logging.getLogger(__name__)

# Gevendorde scripts (relatief t.o.v. de outputmap) die opslag gebruiken.
# "required": bij ontbreken of nul vervangingen volgt een build-warning;
# de overige worden gepatcht als ze bestaan (extensieset kan wijzigen).
_REQUIRED_JS = (
    "_static/scripts/pydata-sphinx-theme.js",
    "_static/sphinx_highlight.js",
    "_static/Accessibility.js",
)
_OPTIONAL_JS = (
    "_static/searchtools.js",
    "_static/design-tabs.js",
    "_sphinx_design_static/design-tabs.js",
)

# Kale (of window.-geprefixte) verwijzingen naar de storage-globals. De
# negative lookbehind sluit property-accesses op andere objecten uit
# (bv. ``foo.localStorage``) en houdt de vervanging idempotent.
_JS_STORAGE_RE = re.compile(r"(?<![\w$.])(?:window\.)?(localStorage|sessionStorage)\b")
_JS_REPLACEMENT = {
    "localStorage": "window.plinkSafeStorage.local",
    "sessionStorage": "window.plinkSafeStorage.session",
}

# Het inline mode-bootstrapscript van pydata-sphinx-theme (layout.html,
# block css); ``default_mode`` wordt uit de pagina zelf overgenomen.
_BOOTSTRAP_RE = re.compile(
    r'<script data-cfasync="false">\s*'
    r'document\.documentElement\.dataset\.mode\s*=\s*'
    r'localStorage\.getItem\("mode"\)\s*\|\|\s*"(?P<default>[^"]*)";\s*'
    r'document\.documentElement\.dataset\.theme\s*=\s*'
    r'localStorage\.getItem\("theme"\)\s*\|\|\s*"[^"]*";\s*'
    r'</script>'
)

# Geharde vervanging: veilige wrappers + genormaliseerde mode/theme. Moet
# als allereerste script blijven draaien (voor de theme-scripts laden).
_BOOTSTRAP_REPLACEMENT = """<script data-cfasync="false">
    (function () {
      "use strict";
      function safeStorage(name) {
        var mem = Object.create(null);
        function native() { return window[name]; }
        return {
          getItem: function (key) {
            key = String(key);
            if (key in mem) { return mem[key]; }
            try { return native().getItem(key); } catch (err) { return null; }
          },
          setItem: function (key, value) {
            key = String(key);
            mem[key] = String(value);
            try { native().setItem(key, mem[key]); delete mem[key]; } catch (err) {}
          },
          removeItem: function (key) {
            key = String(key);
            delete mem[key];
            try { native().removeItem(key); } catch (err) {}
          },
          clear: function () {
            mem = Object.create(null);
            try { native().clear(); } catch (err) {}
          },
          key: function (index) {
            try { return native().key(index); } catch (err) { return null; }
          },
          get length() {
            try { return native().length; } catch (err) {
              return Object.keys(mem).length;
            }
          }
        };
      }
      window.plinkSafeStorage = {
        local: safeStorage("localStorage"),
        session: safeStorage("sessionStorage")
      };
      var mode = window.plinkSafeStorage.local.getItem("mode") || "%DEFAULT%";
      if (mode !== "light" && mode !== "dark" && mode !== "auto") { mode = "auto"; }
      var theme = window.plinkSafeStorage.local.getItem("theme");
      if (theme !== "light" && theme !== "dark") {
        theme = mode !== "auto" ? mode
          : (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      }
      document.documentElement.dataset.mode = mode;
      document.documentElement.dataset.theme = theme;
    })();
  </script>"""


def _patch_js_file(path: Path) -> bool:
    """Patch een script; True zolang het bestand (nu of al eerder) gehard is.

    Bij een incrementele rebuild kopieert Sphinx ongewijzigde assets niet
    opnieuw; het bestand bevat dan al de wrappers en telt gewoon als gehard.
    """
    source = path.read_text(encoding="utf-8")
    patched, count = _JS_STORAGE_RE.subn(
        lambda match: _JS_REPLACEMENT[match.group(1)], source
    )
    if count:
        path.write_text(patched, encoding="utf-8")
        return True
    return "plinkSafeStorage" in source


def _patch_html_file(path: Path) -> bool:
    """Patch een pagina; True zolang die (nu of al eerder) gehard is."""
    source = path.read_text(encoding="utf-8")

    def _replace(match: re.Match[str]) -> str:
        return _BOOTSTRAP_REPLACEMENT.replace("%DEFAULT%", match.group("default"))

    patched, count = _BOOTSTRAP_RE.subn(_replace, source)
    if count:
        path.write_text(patched, encoding="utf-8")
        return True
    return "plinkSafeStorage" in source


def _harden_output(app, exception):
    if exception is not None or app.builder.format != "html":
        return
    outdir = Path(app.outdir)

    for relative in _REQUIRED_JS + _OPTIONAL_JS:
        target = outdir / relative
        required = relative in _REQUIRED_JS
        if not target.is_file():
            if required:
                logger.warning(
                    "harden_theme_storage: verwacht themescript ontbreekt: %s "
                    "(theme-upgrade? pas _ext/harden_theme_storage.py aan)",
                    relative,
                )
            continue
        if not _patch_js_file(target) and required:
            logger.warning(
                "harden_theme_storage: geen storage-referenties gevonden in %s "
                "(theme-upgrade? pas _ext/harden_theme_storage.py aan)",
                relative,
            )

    pages_patched = sum(
        1 for page in outdir.rglob("*.html") if _patch_html_file(page)
    )
    if pages_patched == 0:
        logger.warning(
            "harden_theme_storage: het inline mode-bootstrapscript is op geen "
            "enkele pagina gevonden (theme-upgrade? pas "
            "_ext/harden_theme_storage.py aan)"
        )
    else:
        logger.info(
            "harden_theme_storage: %d pagina's en de themescripts gehard",
            pages_patched,
        )


def setup(app):
    app.connect("build-finished", _harden_output)
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
