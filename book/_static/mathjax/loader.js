/* Lokale vervanger van jupyterbook_patches' mathjax_patch.js (issue #28).
 *
 * Zelfde gedrag als het origineel (Firefox krijgt de SVG-uitvoer vanwege een
 * MathJax/ui-lazy renderprobleem, andere browsers CHTML), maar de MathJax-
 * bundel wordt uit deze map geladen in plaats van van cdn.jsdelivr.net, zodat
 * het boek ook achter een schoolfirewall of offline werkt. MathJax leidt zijn
 * rootpad af van de script-src, dus ui/lazy.js en de CHTML-woff2-fonts worden
 * automatisch ook uit deze map (_static/mathjax/) geladen.
 *
 * Gevendorde bestanden: mathjax@3.2.2 (npm), es5/tex-mml-chtml.js,
 * es5/tex-mml-svg.js, es5/ui/lazy.js en es5/output/chtml/fonts/woff-v2/.
 * De registratie als mathjax_path gebeurt in _ext/vendor_mathjax.py.
 */
(function () {
  "use strict";
  var isFirefox = typeof InstallTrigger !== "undefined";
  var output = isFirefox ? "svg" : "chtml";

  // Basis-URL = de map van dit script (…/_static/mathjax/), zodat het pad
  // klopt vanaf elke paginadiepte.
  var current = document.currentScript;
  var base = current && current.src ? current.src.replace(/[^/]*$/, "") : "";

  var script = document.createElement("script");
  script.src = base + "tex-mml-" + output + ".js";
  script.async = true;
  document.head.appendChild(script);
})();
