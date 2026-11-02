#!/usr/bin/env bash
# Démarre un terminal de pointage : service local (caméra, reconnaissance, file hors ligne)
# et écran tactile en mode kiosque.
#   ./run_terminal.sh TRM-BKO-03                  caméra de la configuration (0 par défaut)
#   ./run_terminal.sh TRM-SEL-01 --camera 1       autre caméra, ou chemin d'une vidéo
#   SANS_ECRAN=1 ./run_terminal.sh TRM-BKO-03     service seul (l'écran s'ouvre ailleurs)
#   FENETRE=1 ./run_terminal.sh TRM-BKO-03        écran dans une fenêtre (démonstration sur PC) au lieu du plein écran
set -euo pipefail
cd "$(dirname "$0")"
CODE=${1:-}
if [[ -z "$CODE" ]]; then
  echo "Usage : $0 CODE_TERMINAL [--camera N|video.mp4] [--port P]"
  echo "Terminaux configurés :"; ls terminal/config/*.json 2>/dev/null | xargs -n1 basename | sed 's/\.json$//; s/^/  /'
  exit 1
fi
shift
CONFIG="terminal/config/$CODE.json"
[[ -f "$CONFIG" ]] || { echo "Configuration introuvable : $CONFIG"; exit 1; }
PORT=$(.venv/bin/python -c "import json,sys; print(json.load(open(sys.argv[1])).get('port_local', 8100))" "$CONFIG")
for (( i = 1; i <= $#; i++ )); do [[ "${!i}" == "--port" ]] && { j=$((i + 1)); PORT=${!j}; }; done

.venv/bin/python -m terminal.service --config "$CONFIG" "$@" &
SERVICE=$!
trap 'kill $SERVICE 2>/dev/null' EXIT

# Attente du service puis ouverture de l'écran en plein écran (kiosque)
for _ in $(seq 1 60); do curl -fs "http://127.0.0.1:$PORT/api/etat" >/dev/null 2>&1 && break; sleep 0.5; done
if [[ -z "${SANS_ECRAN:-}" ]]; then
  NAVIGATEUR=$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)
  if [[ -n "$NAVIGATEUR" ]]; then
    MODE="--kiosk"; [[ -n "${FENETRE:-}" ]] && MODE="--window-size=1024,640"
    "$NAVIGATEUR" $MODE --app="http://127.0.0.1:$PORT" --user-data-dir="$PWD/terminal/donnees/.navigateur-$CODE" \
      --noerrdialogs --disable-infobars --no-first-run --disable-translate --overscroll-history-navigation=0 >/dev/null 2>&1 &
  else
    echo "Ouvrez http://127.0.0.1:$PORT dans un navigateur en plein écran (F11)."
  fi
fi
echo "Terminal $CODE démarré — écran : http://127.0.0.1:$PORT (Ctrl+C pour arrêter)"
wait $SERVICE
