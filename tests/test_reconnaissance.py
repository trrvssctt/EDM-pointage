"""Poste de pointage simulé : identification en direct de plusieurs visages."""
import base64

import cv2
import numpy as np

from server.app.models import Pointage
from server.app.database import SessionLocale
from tests.conftest import enrolement, images_visage, jeton


def test_identifie_un_agent_enrole_sans_creer_de_pointage(client, admin, creer_agent):
    agent = creer_agent("EDM0001")
    image = images_visage(1)[0]
    inconnu = client.post("/api/reconnaissance/identifier", json={"image": image, "debut": True}, headers=admin).json()
    assert [v["statut"] for v in inconnu["visages"]] == ["INCONNU"]
    assert client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement(), headers=admin).status_code == 200
    r = client.post("/api/reconnaissance/identifier", json={"image": image}, headers=admin).json()
    visage = r["visages"][0]
    assert visage["statut"] == "RECONNU" and visage["agent"]["matricule"] == "EDM0001" and len(visage["boite"]) == 4
    assert r["agents_enroles"] == 1
    with SessionLocale() as db:
        assert db.query(Pointage).count() == 0  # démonstration : rien n'est enregistré
    journal = client.get("/api/audit", headers=admin).json()
    assert any(e["action"] == "RECONNAISSANCE_DIRECT" for e in journal)


def test_plusieurs_visages_et_image_vide(client, admin):
    visage = cv2.imdecode(np.frombuffer(base64.b64decode(images_visage(1)[0]), np.uint8), cv2.IMREAD_COLOR)
    double = np.hstack([visage, visage])
    b64 = base64.b64encode(cv2.imencode(".jpg", double)[1].tobytes()).decode()
    assert len(client.post("/api/reconnaissance/identifier", json={"image": b64}, headers=admin).json()["visages"]) == 2
    noir = base64.b64encode(cv2.imencode(".jpg", np.zeros((480, 640, 3), np.uint8))[1].tobytes()).decode()
    assert client.post("/api/reconnaissance/identifier", json={"image": noir}, headers=admin).json()["visages"] == []


def test_reserve_a_l_administrateur_et_a_la_drh(client):
    resp = jeton(client, "resp", "Resp@2026")
    assert client.post("/api/reconnaissance/identifier", json={"image": images_visage(1)[0]}, headers=resp).status_code == 403
