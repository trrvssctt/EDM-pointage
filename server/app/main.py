"""Serveur central du système de pointage biométrique multisite."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.app.database import initialiser_base
from server.app.documentation_api import documenter
from server.app.routers import (agents, auth, enrolements, mobile, organisation, pointages, reconnaissance, referentiels,
                                terminal_api)
from server.app.services import maintenance

# Interface d'administration (React) compilée par « npm run build » dans frontend/
INTERFACE = Path(__file__).resolve().parents[2] / "frontend" / "dist"

initialiser_base()


@asynccontextmanager
async def cycle_de_vie(_: FastAPI):
    maintenance.planifier()  # purge de conservation au démarrage puis chaque nuit
    yield


app = FastAPI(title="Pointage biométrique multisite — API", version="1.0.0", lifespan=cycle_de_vie,
              description="Gestion des agents, enrôlement facial, pointages multisites, rapports et terminaux.")

for r in (auth.router, organisation.router, referentiels.router, agents.router, enrolements.router, pointages.router,
          terminal_api.router, mobile.router, reconnaissance.router):
    app.include_router(r)
documenter(app)


@app.middleware("http")
async def entetes_securite(request, call_next):
    reponse = await call_next(request)
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["X-Frame-Options"] = "DENY"
    reponse.headers["Referrer-Policy"] = "no-referrer"
    reponse.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        reponse.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/assets/"):  # fichiers nommés d'après leur contenu : jamais modifiés
        reponse.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif reponse.headers.get("content-type", "").startswith("text/html"):
        # Pages de l'interface : revalidées à chaque visite, la nouvelle version s'affiche après une mise à jour
        reponse.headers["Cache-Control"] = "no-cache"
    return reponse


@app.get("/api/sante", tags=["Supervision"])
def sante():
    return {"statut": "ok", "version": app.version}


if (INTERFACE / "assets").exists():
    app.mount("/assets", StaticFiles(directory=INTERFACE / "assets"), name="assets")


@app.get("/{chemin:path}", include_in_schema=False)
def interface(chemin: str):
    """Application monopage : toute route inconnue renvoie l'interface d'administration."""
    if chemin.startswith("api/"):
        raise HTTPException(404, "Ressource introuvable")
    fichier = INTERFACE / chemin
    if chemin and fichier.is_file() and INTERFACE in fichier.resolve().parents:
        return FileResponse(fichier)
    index = INTERFACE / "index.html"
    if not index.exists():
        raise HTTPException(503, "Interface non compilée : lancez ./setup.sh (ou npm run build dans frontend/)")
    return FileResponse(index)
