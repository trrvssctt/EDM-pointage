"""API de l'application mobile : appareil enregistré, enrôlement à valider, pointage de secours."""
import uuid
from datetime import datetime

import pytest

from server.app.database import SessionLocale
from server.app.models import DemandeEnrolement, Terminal, TypeAppareil
from server.app.securite import empreinte_cle
from tests.conftest import CLE_KATI, images_visage, jeton

CLE_MOBILE = "cle-iphone"
MOBILE = {"X-Terminal-Key": CLE_MOBILE}


@pytest.fixture()
def telephone(db_vide):
    with SessionLocale() as db:
        db.add(Terminal(code="MOB-TEST", site_id=2, empreinte_cle=empreinte_cle(CLE_MOBILE), type=TypeAppareil.MOBILE))
        db.commit()


def session_mobile(client, identifiant="drh", mdp="Drh@2026"):
    r = client.post("/api/mobile/connexion", json={"identifiant": identifiant, "mot_de_passe": mdp}, headers=MOBILE)
    assert r.status_code == 200, r.text
    return {**MOBILE, "Authorization": f"Bearer {r.json()['jeton']}"}


def envoi(agent_id, images=None, u=None):
    poses = ["face", "gauche", "droite", "haut", "bas"]
    return {"uuid": u or str(uuid.uuid4()), "agent_id": agent_id, "consentement": True,
            "capture_le": datetime.now().isoformat(timespec="seconds"),
            "images": [{"pose": poses[i], "image": img} for i, img in enumerate(images or images_visage())]}


def test_connexion_reservee_aux_telephones_enregistres(client, telephone):
    corps = {"identifiant": "drh", "mot_de_passe": "Drh@2026"}
    assert client.post("/api/mobile/connexion", json=corps).status_code == 422          # sans clé d'appareil
    assert client.post("/api/mobile/connexion", json=corps, headers={"X-Terminal-Key": CLE_KATI}).status_code == 403  # borne
    r = client.post("/api/mobile/connexion", json=corps, headers=MOBILE).json()
    assert r["jeton"] and r["appareil"]["code"] == "MOB-TEST" and r["appareil"]["site"] == "Agence de Kati"


def test_accueil(client, telephone):
    h = session_mobile(client)
    r = client.get("/api/mobile/accueil", headers=h).json()
    assert r["utilisateur"]["utilisateur"]["identifiant"] == "drh" and r["activite"] == []
    assert r["utilisateur"]["droits"]["biometrie.proposer"] == "oui"


def test_enrolement_propose_puis_valide_par_la_drh(client, admin, creer_agent, telephone):
    agent = creer_agent("EDM0001")
    h = session_mobile(client)
    corps = envoi(agent["id"])
    r = client.post("/api/mobile/enrolements", json=corps, headers=h)
    assert r.status_code == 202 and r.json()["statut"] == "GABARIT_CALCULE"
    assert client.post("/api/mobile/enrolements", json=corps, headers=h).json()["statut"] == "GABARIT_CALCULE"  # renvoi
    with SessionLocale() as db:
        assert db.query(DemandeEnrolement).count() == 1
    # Pas encore enrôlé : la DRH doit valider
    assert client.get(f"/api/agents/{agent['id']}", headers=admin).json()["nb_gabarits"] == 0
    demande = client.get("/api/enrolements/demandes", headers=admin).json()[0]
    detail = client.get(f"/api/enrolements/demandes/{demande['uuid']}", headers=admin).json()
    assert set(detail["photos"]) == {"face", "gauche", "droite", "haut"}
    assert any(a["type"] == "ENROLEMENT" for a in client.get("/api/tableau-de-bord", headers=admin).json()["anomalies"])
    r = client.post(f"/api/enrolements/demandes/{demande['uuid']}/valider", headers=admin).json()
    assert r["statut"] == "VALIDEE"
    fiche = client.get(f"/api/agents/{agent['id']}", headers=admin).json()
    assert fiche["nb_gabarits"] == 4 and fiche["consentement_le"]
    with SessionLocale() as db:  # photos effacées après la décision
        assert db.query(DemandeEnrolement).one().photos_chiffrees is None
    assert client.get(f"/api/mobile/enrolements/{corps['uuid']}", headers=h).json()["statut"] == "VALIDEE"


def test_rejet_d_un_enrolement(client, admin, creer_agent, telephone):
    agent = creer_agent("EDM0001")
    corps = envoi(agent["id"])
    client.post("/api/mobile/enrolements", json=corps, headers=session_mobile(client))
    r = client.post(f"/api/enrolements/demandes/{corps['uuid']}/rejeter", json={"motif": "Photos floues"}, headers=admin)
    assert r.json()["statut"] == "REJETEE" and r.json()["motif"] == "Photos floues"
    assert client.post(f"/api/enrolements/demandes/{corps['uuid']}/valider", headers=admin).status_code == 409


def test_photos_inexploitables_rejetees_automatiquement(client, creer_agent, telephone):
    agent = creer_agent("EDM0001")
    noir = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
    r = client.post("/api/mobile/enrolements", json=envoi(agent["id"], [noir] * 5), headers=session_mobile(client)).json()
    assert r["statut"] == "REJETEE" and "exploitable" in r["motif"]


def test_responsable_propose_dans_son_perimetre_mais_ne_valide_pas(client, creer_agent, telephone):
    dans, hors = creer_agent("EDM0001", site_id=2), creer_agent("EDM0002", site_id=1)
    h = session_mobile(client, "resp.kati", "Resp@2026")
    assert client.post("/api/mobile/enrolements", json=envoi(dans["id"]), headers=h).status_code == 202
    assert client.post("/api/mobile/enrolements", json=envoi(hors["id"]), headers=h).status_code == 404
    resp = jeton(client, "resp.kati", "Resp@2026")
    assert client.get("/api/enrolements/demandes", headers=resp).status_code == 403


def test_pointage_de_secours(client, admin, creer_agent, telephone):
    agent = creer_agent("EDM0001", site_id=1)
    client.post("/api/mobile/enrolements", json=(c := envoi(agent["id"])), headers=session_mobile(client))
    client.post(f"/api/enrolements/demandes/{c['uuid']}/valider", headers=admin)
    h = session_mobile(client)
    corps = {"uuid": str(uuid.uuid4()), "horodatage": datetime.now().isoformat(timespec="seconds"),
             "image": images_visage(1)[0], "hors_ligne": True}
    r = client.post("/api/mobile/secours", json=corps, headers=h).json()
    assert r["resultat"] == "ENREGISTRE" and r["type"] == "ENTREE" and r["agent"]["matricule"] == "EDM0001"
    assert r["site"] == "Agence de Kati" and r["hors_rattachement"] and r["appareil"] == "MOB-TEST"
    assert client.post("/api/mobile/secours", json=corps, headers=h).json()["uuid"] == corps["uuid"]  # renvoi
    ligne = client.get("/api/pointages", headers=admin).json()["elements"][0]
    assert ligne["secours"] is True and ligne["synchro"] == "DIFFERE" and ligne["terminal"] == "MOB-TEST"
    # Deuxième pointage immédiat : anti-rebond
    second = {**corps, "uuid": str(uuid.uuid4())}
    assert client.post("/api/mobile/secours", json=second, headers=h).json()["resultat"] == "DEJA_POINTE"
    # « Ce n'est pas moi »
    assert client.post(f"/api/mobile/secours/{corps['uuid']}/annuler", headers=h).json()["annule"] is True


def test_secours_visage_inconnu_et_photo_inexploitable(client, telephone):
    h = session_mobile(client)
    corps = {"uuid": str(uuid.uuid4()), "horodatage": datetime.now().isoformat(), "image": images_visage(1)[0]}
    assert client.post("/api/mobile/secours", json=corps, headers=h).json()["resultat"] == "REFUSE"
    noir = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
    r = client.post("/api/mobile/secours", json={**corps, "uuid": str(uuid.uuid4()), "image": noir}, headers=h).json()
    assert r["resultat"] == "REPRENDRE"
