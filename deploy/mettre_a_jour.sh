#!/usr/bin/env bash
# Mise à jour sur le VPS après un « git push » : récupère le code, réinstalle, recompile, redémarre.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
.venv/bin/pip install --quiet -r requirements.txt
( cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent )
pm2 restart deploy/ecosystem.config.cjs --update-env   # relit l'environnement (fuseau horaire)
sleep 3
curl -fs http://127.0.0.1:8200/api/sante && echo "  ← API à jour"
