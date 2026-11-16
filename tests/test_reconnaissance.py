"""Poste de pointage simulé : identification en direct de plusieurs visages."""
import base64
import time

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


def _photo_reconnue(client, admin, creer_agent, matricule):
    agent = creer_agent(matricule)
    assert client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement(), headers=admin).status_code == 200
    return images_visage(1)[0]


def test_une_photo_reconnue_ne_prouve_pas_la_vivacite(client, admin, creer_agent, monkeypatch):
    """Une photo (ou un écran) immobile est reconnue, mais le défi de rotation échoue : aucun passage."""
    image = _photo_reconnue(client, admin, creer_agent, "EDM0002")
    monkeypatch.setattr("server.app.routers.reconnaissance.DUREE_DEFI", 1.0)
    envoyer = lambda: client.post("/api/reconnaissance/identifier", json={"image": image, "session": "photo"},
                                  headers=admin).json()
    r = envoyer()
    assert r["visages"][0]["statut"] == "RECONNU" and r["visages"][0]["vivacite"] == "DEFI"
    assert r["defi"]["matricule"] == "EDM0002" and r["defi"]["direction"] in ("droite", "gauche")
    for _ in range(4):
        assert envoyer()["visages"][0]["vivacite"] == "DEFI"
    time.sleep(1.1)  # délai du défi écoulé sans aucune rotation
    r = envoyer()
    assert r["visages"][0]["vivacite"] == "ECHEC" and r["defi"] is None

    # Signalée comme tentative de fraude, avec l'identité présentée, comme pour une borne.
    assert r["fraude_signalee"] is True
    lignes = client.get("/api/pointages", params={"alerte": "FRAUDE"}, headers=admin).json()["elements"]
    assert [(l["motif"], l["matricule"], l["terminal"]) for l in lignes] == [("ECHEC_VIVACITE", "EDM0002", "POSTE-WEB")]
    assert lignes[0]["libelle_alerte"] == "Fraude : photo, écran ou vidéo"
    anomalies = client.get("/api/tableau-de-bord", headers=admin).json()["anomalies"]
    assert any(x["type"] == "FRAUDE" and "EDM0002" in x["detail"] for x in anomalies)
    assert any(e["action"] == "FRAUDE_SUSPECTEE" for e in client.get("/api/audit", headers=admin).json())
    # Le poste virtuel n'apparaît pas parmi les terminaux, et l'échec suivant n'est pas compté deux fois.
    assert "POSTE-WEB" not in [t["code"] for t in client.get("/api/terminaux", headers=admin).json()]
    time.sleep(4.1)  # fin de l'affichage de l'échec : nouveau défi, de nouveau échoué
    envoyer(); time.sleep(1.1); envoyer()
    assert client.get("/api/pointages", params={"alerte": "FRAUDE"}, headers=admin).json()["total"] == 1


def test_rotation_dans_le_bon_sens_prouve_la_vivacite(client, admin, creer_agent, monkeypatch):
    image = _photo_reconnue(client, admin, creer_agent, "EDM0003")
    monkeypatch.setattr("server.app.routers.reconnaissance.random.choice", lambda choix: "droite")
    lacets = iter([0.5, 0.5, 0.3, 0.3])  # de face, puis nez vers la gauche de l'image : tête tournée vers sa droite
    monkeypatch.setattr("common.vivacite.rapport_lacet", lambda _: next(lacets))
    envoyer = lambda: client.post("/api/reconnaissance/identifier", json={"image": image, "session": "vivant"},
                                  headers=admin).json()
    etats = [envoyer()["visages"][0]["vivacite"] for _ in range(4)]
    assert etats == ["DEFI", "DEFI", "VERIFIEE", "VERIFIEE"]


def test_pas_de_defi_avec_plusieurs_personnes(client, admin, creer_agent):
    _photo_reconnue(client, admin, creer_agent, "EDM0004")
    visage = cv2.imdecode(np.frombuffer(base64.b64decode(images_visage(1)[0]), np.uint8), cv2.IMREAD_COLOR)
    b64 = base64.b64encode(cv2.imencode(".jpg", np.hstack([visage, visage]))[1].tobytes()).decode()
    r = client.post("/api/reconnaissance/identifier", json={"image": b64, "session": "groupe"}, headers=admin).json()
    assert r["defi"] is None and {v["vivacite"] for v in r["visages"]} <= {"NON_VERIFIEE", None}


def test_visage_change_pendant_le_defi_signale_une_usurpation(client, admin, creer_agent, monkeypatch):
    image = _photo_reconnue(client, admin, creer_agent, "EDM0005")
    monkeypatch.setattr("server.app.routers.reconnaissance.random.choice", lambda choix: "droite")
    lacets = iter([0.5, 0.5, 0.3, 0.3])
    monkeypatch.setattr("common.vivacite.rapport_lacet", lambda _: next(lacets))
    monkeypatch.setattr("common.moteur_facial.Galerie.score_agent", lambda *_: 0.1)  # une autre personne a tourné la tête
    envoyer = lambda: client.post("/api/reconnaissance/identifier", json={"image": image, "session": "usurpation"},
                                  headers=admin).json()
    r = [envoyer() for _ in range(3)][-1]
    assert r["visages"][0]["vivacite"] == "ECHEC" and r["fraude_signalee"] is True
    ligne = client.get("/api/pointages", params={"alerte": "FRAUDE"}, headers=admin).json()["elements"][0]
    assert (ligne["motif"], ligne["matricule"], ligne["libelle_alerte"]) == ("CHANGEMENT_VISAGE", "EDM0005", "Usurpation d'identité")


def test_le_poste_web_ne_se_cree_pas_a_la_main(client, admin):
    site = client.get("/api/sites", headers=admin).json()[0]["id"]
    r = client.post("/api/terminaux", json={"code": "X-WEB", "site_id": site, "type": "WEB"}, headers=admin)
    assert r.status_code == 422
