#!/usr/bin/env bash
# Installation du pointage biométrique sur le VPS (à lancer en root depuis /opt/edm-pointage).
#   ./deploy/installer_vps.sh           base vide (organisation, comptes et terminaux de départ)
#   ./deploy/installer_vps.sh --demo    + agents fictifs et 3 semaines d'historique (démonstration)
# Le script peut être relancé : il ne recrée ni la base, ni les clés, ni les données existantes.
set -euo pipefail
cd "$(dirname "$0")/.."
RACINE=$PWD
PORT_API=8200
PORT_PUBLIC=8095
PORT_PG=5442
CONTENEUR_PG=edm-pointage-db
IP_PUBLIQUE=${IP_PUBLIQUE:-185.215.165.43}
URL_PUBLIQUE=${URL_PUBLIQUE:-http://$IP_PUBLIQUE:$PORT_PUBLIC}
DEMO=""; [[ "${1:-}" == "--demo" ]] && DEMO="--demo"
etape() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }

etape "Vérification des prérequis"
[[ $EUID -eq 0 ]] || { echo "À lancer en root (sudo)."; exit 1; }
for c in python3 node npm docker nginx pm2 curl openssl; do command -v $c >/dev/null || { echo "Commande manquante : $c"; exit 1; }; done
python3 -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ requis"'
[[ $(node -p 'process.versions.node.split(".")[0]') -ge 18 ]] || { echo "Node.js 18+ requis pour compiler l'interface"; exit 1; }
# Ubuntu : le module venv existe mais ensurepip (pip dans l'environnement) est livré dans python3.X-venv.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  VERSION_PY=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  apt-get update -qq && apt-get install -y -qq "python${VERSION_PY}-venv" python3-venv
fi
for p in $PORT_API $PORT_PUBLIC $PORT_PG; do
  if ss -ltnH "sport = :$p" | grep -q . && ! ss -ltnpH "sport = :$p" | grep -qE "uvicorn|docker-proxy|nginx"; then
    echo "Le port $p est déjà utilisé par une autre application : modifiez-le dans ce script."; exit 1
  fi
done

etape "Base de données PostgreSQL (conteneur $CONTENEUR_PG, 127.0.0.1:$PORT_PG)"
if [[ ! -f deploy/.db.env ]]; then
  echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)" > deploy/.db.env
  chmod 600 deploy/.db.env
fi
source deploy/.db.env
if ! docker ps -a --format '{{.Names}}' | grep -qx $CONTENEUR_PG; then
  docker run -d --name $CONTENEUR_PG --restart unless-stopped \
    -e POSTGRES_USER=edm -e POSTGRES_DB=edm_pointage -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -v edm_pointage_donnees:/var/lib/postgresql/data -p 127.0.0.1:$PORT_PG:5432 postgres:16-alpine
fi
docker start $CONTENEUR_PG >/dev/null
until docker exec $CONTENEUR_PG pg_isready -U edm -d edm_pointage -q; do sleep 1; done
sleep 2
if [[ $(docker exec $CONTENEUR_PG psql -U edm -d edm_pointage -tAc "select to_regclass('public.agents') is not null") != "t" ]]; then
  docker exec -i $CONTENEUR_PG psql -U edm -d edm_pointage -v ON_ERROR_STOP=1 -q < database/schema.sql
  echo "Schéma créé (database/schema.sql)"
else
  echo "Schéma déjà présent : conservé"
fi

etape "Clés secrètes (server/.env)"
if [[ ! -f server/.env ]]; then
  {
    echo "# Généré le $(date '+%F %T') — NE PAS DIFFUSER, À SAUVEGARDER"
    echo "EDM_CLE_JWT=$(openssl rand -base64 48 | tr -d '\n')"
    echo "EDM_CLE_BIOMETRIE=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"
    echo "EDM_DATABASE_URL=postgresql+psycopg://edm:$POSTGRES_PASSWORD@127.0.0.1:$PORT_PG/edm_pointage"
  } > server/.env
  chmod 600 server/.env
  echo "server/.env créé"
else
  echo "server/.env existant : conservé"
fi

etape "Dépendances Python"
[[ -x .venv/bin/pip ]] || { rm -rf .venv; python3 -m venv .venv; }   # environnement incomplet : recréé
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

etape "Interface web (React)"
( cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent )

etape "Modèles de reconnaissance faciale"
mkdir -p models
for m in face_detection_yunet/face_detection_yunet_2023mar.onnx face_recognition_sface/face_recognition_sface_2021dec.onnx; do
  f=models/$(basename $m)
  if [[ ! -s $f ]]; then
    curl -fsSL --retry 3 -o $f.part "https://github.com/opencv/opencv_zoo/raw/main/models/$m" && mv $f.part $f
  fi
done
.venv/bin/python -c "from common.moteur_facial import MoteurFacial; MoteurFacial(); print('Moteur facial opérationnel')"

etape "Données initiales"
EDM_URL_PUBLIQUE=$URL_PUBLIQUE .venv/bin/python -m server.seed $DEMO

etape "Service PM2 (edm-pointage, 127.0.0.1:$PORT_API)"
if pm2 describe edm-pointage >/dev/null 2>&1; then pm2 restart edm-pointage --update-env; else pm2 start deploy/ecosystem.config.cjs; fi
pm2 save >/dev/null

etape "Nginx (port public $PORT_PUBLIC)"
cp deploy/nginx-edm-pointage.conf /etc/nginx/sites-available/edm-pointage
ln -sf /etc/nginx/sites-available/edm-pointage /etc/nginx/sites-enabled/edm-pointage
nginx -t
systemctl reload nginx
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ufw allow $PORT_PUBLIC/tcp; fi

etape "Vérification"
for i in $(seq 1 30); do curl -fs http://127.0.0.1:$PORT_API/api/sante >/dev/null && break; sleep 1; done
curl -fs http://127.0.0.1:$PORT_API/api/sante && echo "  ← API"
curl -fs -o /dev/null -w "Interface via Nginx : HTTP %{http_code}\n" http://127.0.0.1:$PORT_PUBLIC/
cat <<FIN

Déploiement terminé.
  Application : $URL_PUBLIQUE
  API (doc)   : $URL_PUBLIQUE/docs
  Comptes de départ : admin / Admin@2026, drh / Drh@2026 — À CHANGER IMMÉDIATEMENT (Mon compte).
  Configurations des bornes et du téléphone : $RACINE/terminal/config/
  À sauvegarder hors du serveur : server/.env et deploy/.db.env
FIN
