#!/usr/bin/env bash
# Démarre le serveur central (API + interface web d'administration).
#   ./run_server.sh                  écoute sur 127.0.0.1:8000
#   HOTE=0.0.0.0 ./run_server.sh     accessible depuis les terminaux du réseau
set -euo pipefail
cd "$(dirname "$0")"
[[ -x .venv/bin/uvicorn ]] || { echo "Lancez d'abord ./setup.sh"; exit 1; }
HOTE=${HOTE:-127.0.0.1}
PORT=${PORT:-8000}
echo "Interface d'administration : http://$HOTE:$PORT   —   Documentation API : http://$HOTE:$PORT/docs"
exec .venv/bin/uvicorn server.app.main:app --host "$HOTE" --port "$PORT" "$@"
