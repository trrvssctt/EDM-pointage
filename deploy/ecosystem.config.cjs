// PM2 : API centrale + interface web du pointage biométrique (FastAPI servi par uvicorn).
// Démarrage : pm2 start deploy/ecosystem.config.cjs && pm2 save
module.exports = {
  apps: [{
    name: "edm-pointage",
    cwd: "/opt/edm-pointage",
    script: ".venv/bin/uvicorn",
    // 127.0.0.1 : jamais exposé directement, Nginx est le seul point d'entrée.
    // --proxy-headers : l'adresse IP réelle du client est inscrite dans le journal d'audit.
    args: "server.app.main:app --host 127.0.0.1 --port 8200 --proxy-headers --forwarded-allow-ips 127.0.0.1",
    interpreter: "none",
    autorestart: true,
    max_memory_restart: "900M",
    env: { PYTHONUNBUFFERED: "1" },
  }],
};
