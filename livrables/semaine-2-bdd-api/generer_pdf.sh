#!/usr/bin/env bash
# Génère le PDF du livrable n° 2 : document principal + annexes A, B et C.
#   ./generer_pdf.sh            → Livrable_S2_Base_de_donnees_et_API.pdf
# Prérequis : pandoc (2.x ou plus) et Google Chrome ou Chromium.
set -euo pipefail
cd "$(dirname "$0")"
command -v pandoc >/dev/null || { echo "pandoc est requis (https://pandoc.org/installing.html)"; exit 1; }
NAVIGATEUR=$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)
[[ -n "$NAVIGATEUR" ]] || { echo "Google Chrome ou Chromium est requis pour l'impression PDF"; exit 1; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
for f in Livrable_S2_Base_de_donnees_et_API.md annexes/A_dictionnaire_de_donnees.md annexes/B_reference_api.md annexes/C_resultats_des_tests.md; do
  sed 's#^\\newpage$#<div class="saut"></div>#' "$f"
  printf '\n\n<div class="saut"></div>\n\n'
done > "$TMP/livrable.md"

# --self-contained : images et style intégrés dans un HTML autonome (option renommée --embed-resources dans pandoc 3)
OPTION=--self-contained; pandoc --help | grep -q -- --embed-resources && OPTION="--embed-resources --standalone"
pandoc "$TMP/livrable.md" -f markdown -t html5 --standalone $OPTION --resource-path=. \
  --css=outils/style.css --include-before-body=outils/couverture.html \
  --toc --toc-depth=2 --metadata toc-title="Sommaire" --no-highlight -o "$TMP/livrable.html"
cp "$TMP/livrable.html" Livrable_S2_Base_de_donnees_et_API.html

"$NAVIGATEUR" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --print-to-pdf="$PWD/Livrable_S2_Base_de_donnees_et_API.pdf" "file://$TMP/livrable.html" 2>/dev/null
echo "PDF généré : $PWD/Livrable_S2_Base_de_donnees_et_API.pdf"
