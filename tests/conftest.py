"""Configuration des tests : base SQLite temporaire et clés de test (avant tout import du serveur)."""
import base64
import os
import tempfile
from datetime import time
from pathlib import Path

import cv2
import pytest
from cryptography.fernet import Fernet

_DOSSIER = tempfile.mkdtemp(prefix="edm_tests_")
# Base de test : SQLite temporaire par défaut, ou PostgreSQL via EDM_TEST_DATABASE_URL
# (ex. postgresql+psycopg://postgres:motdepasse@127.0.0.1:5432/edm_tests).
os.environ["EDM_DATABASE_URL"] = os.environ.get("EDM_TEST_DATABASE_URL", f"sqlite:///{_DOSSIER}/test.db")
os.environ["EDM_CLE_JWT"] = "cle-de-test-uniquement-0123456789abcdef"
os.environ["EDM_CLE_BIOMETRIE"] = Fernet.generate_key().decode()
# Les images de test sont des photos planes : la vivacité d'enrôlement est testée à part.
os.environ["EDM_ENROLEMENT_VIVACITE_OBLIGATOIRE"] = "0"
# L'image de test est un visage de trois quarts (lacet ≈ 0,77) : tolérance élargie pour la pose « face ».
os.environ["EDM_ENROLEMENT_ECART_FACE"] = "0.35"

from fastapi.testclient import TestClient  # noqa: E402

from server.app.database import Base, SessionLocale, engine  # noqa: E402
from server.app.main import app  # noqa: E402
from server.app.models import Horaire, Organisation, Role, Service, Site, Terminal, TypeSite, Utilisateur  # noqa: E402
from server.app.securite import empreinte_cle, hacher_mot_de_passe  # noqa: E402

IMAGE_VISAGE = Path(__file__).parent / "donnees" / "visage_test.jpg"
CLE_SIEGE, CLE_KATI = "cle-terminal-siege", "cle-terminal-kati"


@pytest.fixture()
def db_vide():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocale() as db:
        db.add(Organisation())
        services = [Service(code="DSI", nom="Informatique"), Service(code="DRH", nom="Ressources humaines")]
        sites = [Site(code="SIEGE", nom="Siège", type=TypeSite.SIEGE),
                 Site(code="KATI", nom="Agence de Kati", type=TypeSite.AGENCE),
                 Site(code="KYS", nom="DR Kayes", type=TypeSite.DIRECTION_REGIONALE)]
        horaire = Horaire(nom="Bureau", heure_debut=time(7, 30), heure_fin=time(16, 0), tolerance_minutes=10,
                          jours_travailles="0,1,2,3,4,5,6")
        db.add_all([*services, *sites, horaire])
        db.flush()
        db.add_all([
            Terminal(code="T-SIEGE", site_id=sites[0].id, empreinte_cle=empreinte_cle(CLE_SIEGE)),
            Terminal(code="T-KATI", site_id=sites[1].id, empreinte_cle=empreinte_cle(CLE_KATI)),
            Utilisateur(identifiant="admin", email="admin@exemple.ml", mot_de_passe_hash=hacher_mot_de_passe("Admin@2026"),
                        role=Role.ADMIN),
            Utilisateur(identifiant="drh", mot_de_passe_hash=hacher_mot_de_passe("Drh@2026"), role=Role.DRH),
            Utilisateur(identifiant="resp", mot_de_passe_hash=hacher_mot_de_passe("Resp@2026"),
                        role=Role.RESPONSABLE, service_id=services[0].id),
            Utilisateur(identifiant="resp.kati", mot_de_passe_hash=hacher_mot_de_passe("Resp@2026"),
                        role=Role.RESPONSABLE, site_id=sites[1].id),
        ])
        db.commit()
    yield


@pytest.fixture()
def client(db_vide):
    return TestClient(app)


def jeton(client, identifiant, mot_de_passe):
    r = client.post("/api/auth/connexion", json={"identifiant": identifiant, "mot_de_passe": mot_de_passe})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['jeton']}"}


def enrolement(images: list[str] | None = None, consentement: bool = True) -> dict:
    poses = ["face", "gauche", "droite", "haut", "bas"]
    return {"consentement": consentement,
            "images": [{"pose": poses[i % 5], "image": img} for i, img in enumerate(images or images_visage())]}


@pytest.fixture()
def admin(client):
    return jeton(client, "admin", "Admin@2026")


@pytest.fixture()
def creer_agent(client, admin):
    def _creer(matricule="EDM0001", service_id=1, site_id=1, **kw):
        donnees = {"matricule": matricule, "nom": "TEST", "prenom": "Agent", "service_id": service_id,
                   "site_rattachement_id": site_id, "horaire_id": 1, **kw}
        r = client.post("/api/agents", json=donnees, headers=admin)
        assert r.status_code == 201, r.text
        return r.json()
    return _creer


def images_visage(n=4) -> list[str]:
    """Variantes d'une même photo (luminosité, échelle) encodées en base64."""
    image = cv2.imread(str(IMAGE_VISAGE))
    variantes = [image, cv2.convertScaleAbs(image, alpha=1.1, beta=10), cv2.resize(image, None, fx=1.2, fy=1.2),
                 cv2.convertScaleAbs(image, alpha=0.9, beta=-10)]
    return [base64.b64encode(cv2.imencode(".jpg", v)[1].tobytes()).decode() for v in variantes[:n]]
