#!/usr/bin/env bash
# Installation complète du prototype : environnement Python, modèles de reconnaissance faciale,
# clés de sécurité et base de données initialisée (avec données de démonstration).
#
#   ./setup.sh            installation + base de démonstration
#   ./setup.sh --vierge   installation + base sans agents fictifs
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}
MODELES_URL="https://github.com/opencv/opencv_zoo/raw/main/models"
OPTION_SEED="--demo"
[[ "${1:-}" == "--vierge" ]] && OPTION_SEED=""

etape() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }

etape "Vérification de Python"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10 ou plus requis"; print(sys.version)'

etape "Environnement virtuel et dépendances"
[[ -d .venv ]] || "$PYTHON" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

etape "Interfaces web (React + TypeScript)"
command -v npm >/dev/null || { echo "Node.js 18+ et npm sont requis (https://nodejs.org)"; exit 1; }
( cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent )

etape "Modèles de reconnaissance faciale (OpenCV Zoo)"
mkdir -p models
telecharger() {
  local fichier=$1 chemin=$2
  if [[ ! -s "models/$fichier" ]]; then
    echo "Téléchargement de $fichier"
    curl -fsSL --retry 3 -o "models/$fichier.part" "$MODELES_URL/$chemin/$fichier"
    mv "models/$fichier.part" "models/$fichier"
  else
    echo "$fichier déjà présent"
  fi
}
telecharger face_detection_yunet_2023mar.onnx face_detection_yunet
telecharger face_recognition_sface_2021dec.onnx face_recognition_sface

etape "Clés de sécurité (server/.env)"
if [[ ! -f server/.env ]]; then
  {
    echo "# Généré par setup.sh le $(date '+%F %T') — NE PAS DIFFUSER"
    echo "EDM_CLE_JWT=$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
    echo "EDM_CLE_BIOMETRIE=$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
    echo "# EDM_DATABASE_URL=postgresql+psycopg://edm:motdepasse@localhost:5432/edm_pointage"
  } > server/.env
  chmod 600 server/.env
  echo "server/.env créé"
else
  echo "server/.env existe déjà (conservé)"
fi

etape "Base de données"
.venv/bin/python -m server.seed $OPTION_SEED

etape "Vérification"
.venv/bin/python -c "from common.moteur_facial import MoteurFacial; MoteurFacial(); print('Moteur facial opérationnel')"

cat <<'EOF'

Installation terminée.
  1. Serveur central :   ./run_server.sh             puis http://127.0.0.1:8000
  2. Terminal (caméra) : ./run_terminal.sh TRM-BKO-03  (écran kiosque sur http://127.0.0.1:8100)
  3. Tests :             .venv/bin/python -m pytest
Comptes de démonstration (à changer en production) :
  admin / Admin@2026 (administrateur)   drh / Drh@2026 (DRH)
  resp.sikasso / Resp@2026 (responsable DR Sikasso)   resp.sotuba / Resp@2026 (responsable maintenance Sotuba)
EOF
