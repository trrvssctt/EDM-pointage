"""Authentification, habilitations, gestion des agents, enrôlement et protection des données."""
import pyotp

from server.app.database import SessionLocale
from server.app.models import GabaritFacial, Utilisateur
from server.app.securite import dechiffrer_texte
from server.app.services import biometrie
from tests.conftest import enrolement, images_visage, jeton


# --- Connexion ----------------------------------------------------------------
def test_connexion_par_identifiant_ou_email(client):
    for identifiant in ("admin", "ADMIN@exemple.ml"):
        r = client.post("/api/auth/connexion", json={"identifiant": identifiant, "mot_de_passe": "Admin@2026"})
        assert r.status_code == 200 and r.json()["session"]["utilisateur"]["role"] == "ADMIN"


def test_connexion_refusee_avec_mauvais_mot_de_passe(client):
    r = client.post("/api/auth/connexion", json={"identifiant": "admin", "mot_de_passe": "faux"})
    assert r.status_code == 401


def test_blocage_apres_cinq_echecs(client):
    for _ in range(5):
        client.post("/api/auth/connexion", json={"identifiant": "drh", "mot_de_passe": "faux"})
    r = client.post("/api/auth/connexion", json={"identifiant": "drh", "mot_de_passe": "Drh@2026"})
    assert r.status_code == 423


def test_acces_sans_jeton_refuse(client):
    for chemin in ("/api/agents", "/api/pointages", "/api/rapports", "/api/tableau-de-bord"):
        assert client.get(chemin).status_code == 401


def test_derniere_connexion_enregistree(client, admin):
    u = next(u for u in client.get("/api/utilisateurs", headers=admin).json() if u["identifiant"] == "admin")
    assert u["derniere_connexion"] is not None


def test_mot_de_passe_oublie_signale_a_l_administrateur(client, admin):
    r = client.post("/api/auth/mot-de-passe-oublie", json={"identifiant": "drh"})
    inconnu = client.post("/api/auth/mot-de-passe-oublie", json={"identifiant": "personne"})
    assert r.json() == inconnu.json()  # pas d'énumération des comptes
    drh = next(u for u in client.get("/api/utilisateurs", headers=admin).json() if u["identifiant"] == "drh")
    assert drh["reinitialisation_demandee"] is True
    anomalies = client.get("/api/tableau-de-bord", headers=admin).json()["anomalies"]
    assert any(a["type"] == "MOT_DE_PASSE" for a in anomalies)


def test_verification_en_deux_etapes(client):
    drh = jeton(client, "drh", "Drh@2026")
    assert "<svg" in client.post("/api/auth/deux-etapes/preparer", headers=drh).json()["qr_svg"]
    with SessionLocale() as db:
        secret = dechiffrer_texte(db.query(Utilisateur).filter_by(identifiant="drh").one().secret_totp)
    assert client.post("/api/auth/deux-etapes/activer", json={"code": "000000"}, headers=drh).status_code == 400
    assert client.post("/api/auth/deux-etapes/activer", json={"code": pyotp.TOTP(secret).now()}, headers=drh).status_code == 200

    etape1 = client.post("/api/auth/connexion", json={"identifiant": "drh", "mot_de_passe": "Drh@2026"}).json()
    assert etape1["deux_etapes_requise"] and etape1["jeton"] is None
    faux = client.post("/api/auth/deux-etapes", json={"jeton_temporaire": etape1["jeton_temporaire"], "code": "123456"})
    assert faux.status_code == 401
    ok = client.post("/api/auth/deux-etapes", json={"jeton_temporaire": etape1["jeton_temporaire"],
                                                   "code": pyotp.TOTP(secret).now()})
    assert ok.status_code == 200 and ok.json()["jeton"]
    # Le jeton temporaire ne donne pas accès à l'API
    assert client.get("/api/agents", headers={"Authorization": f"Bearer {etape1['jeton_temporaire']}"}).status_code == 401


# --- Habilitations ------------------------------------------------------------
def test_matrice_des_droits(client, admin):
    droits = {d["code"]: d for d in client.get("/api/droits", headers=admin).json()}
    assert droits["agents.gerer"]["RESPONSABLE"] == "perimetre"
    assert droits["biometrie.enroler"]["RESPONSABLE"] == "non"
    assert droits["sites.gerer"]["DRH"] == "non"
    assert droits["audit.consulter"]["DRH"] == "oui"


def test_responsable_limite_a_son_service(client, creer_agent):
    creer_agent("EDM0001", service_id=1)
    creer_agent("EDM0002", service_id=2)
    resp = jeton(client, "resp", "Resp@2026")
    assert [a["matricule"] for a in client.get("/api/agents", headers=resp).json()["elements"]] == ["EDM0001"]
    assert client.get("/api/agents/2", headers=resp).status_code == 404
    assert client.get("/api/utilisateurs", headers=resp).status_code == 403
    assert client.post("/api/agents/1/enrolement", json=enrolement(), headers=resp).status_code == 403


def test_responsable_limite_a_son_site(client, creer_agent):
    creer_agent("EDM0001", site_id=1)
    creer_agent("EDM0002", site_id=2)
    resp = jeton(client, "resp.kati", "Resp@2026")
    assert [a["matricule"] for a in client.get("/api/agents", headers=resp).json()["elements"]] == ["EDM0002"]
    # Peut gérer un dossier de son périmètre, pas en créer hors de son site
    assert client.put("/api/agents/2", json={"fonction": "Caissier"}, headers=resp).status_code == 200
    hors = {"matricule": "EDM0003", "nom": "X", "prenom": "Y", "service_id": 1, "site_rattachement_id": 1, "horaire_id": 1}
    assert client.post("/api/agents", json=hors, headers=resp).status_code == 403


def test_drh_ne_gere_ni_utilisateurs_ni_terminaux(client):
    drh = jeton(client, "drh", "Drh@2026")
    assert client.post("/api/utilisateurs", json={"identifiant": "x", "mot_de_passe": "Abcdef12", "role": "DRH"},
                       headers=drh).status_code == 403
    assert client.post("/api/terminaux", json={"code": "T", "site_id": 1}, headers=drh).status_code == 403
    assert client.patch("/api/sites/1/pointage", json={"autorise": False}, headers=drh).status_code == 403
    assert client.get("/api/audit", headers=drh).status_code == 200


def test_mot_de_passe_faible_refuse(client, admin):
    r = client.post("/api/utilisateurs", json={"identifiant": "nouveau", "mot_de_passe": "court", "role": "DRH"},
                    headers=admin)
    assert r.status_code == 400


def test_responsable_sans_perimetre_refuse(client, admin):
    r = client.post("/api/utilisateurs", json={"identifiant": "resp2", "mot_de_passe": "Abcdef12",
                                               "role": "RESPONSABLE"}, headers=admin)
    assert r.status_code == 400


def test_un_administrateur_ne_peut_pas_se_retirer_ses_droits(client, admin):
    assert client.put("/api/utilisateurs/1", json={"role": "DRH"}, headers=admin).status_code == 400


# --- Agents -------------------------------------------------------------------
def test_creation_et_unicite_du_matricule(client, admin, creer_agent):
    assert creer_agent("edm-0001")["matricule"] == "EDM-0001"
    r = client.post("/api/agents", json={"matricule": "EDM-0001", "nom": "X", "prenom": "Y", "service_id": 1,
                                         "site_rattachement_id": 1, "horaire_id": 1}, headers=admin)
    assert r.status_code == 409


def test_recherche_filtres_et_pagination(client, admin, creer_agent):
    for i in range(12):
        creer_agent(f"EDM{i:04d}", prenom="Awa" if i == 3 else "Moussa")
    page = client.get("/api/agents?taille=5&page=3", headers=admin).json()
    assert page["total"] == 12 and len(page["elements"]) == 2
    assert client.get("/api/agents?q=awa", headers=admin).json()["total"] == 1
    assert client.get("/api/agents?enrole=false", headers=admin).json()["total"] == 12


def test_modification_desactivation_et_sites_autorises(client, admin, creer_agent):
    agent = creer_agent()
    r = client.put(f"/api/agents/{agent['id']}", json={"fonction": "Ingénieur", "tous_sites": False,
                                                       "sites_autorises": [2], "actif": False}, headers=admin)
    assert r.status_code == 200
    a = r.json()
    assert a["fonction"] == "Ingénieur" and a["actif"] is False and a["tous_sites"] is False and a["sites_autorises"] == [2]
    assert client.get("/api/agents?actif=true", headers=admin).json()["total"] == 0


# --- Enrôlement et biométrie ----------------------------------------------------
def test_enrolement_exige_le_consentement(client, admin, creer_agent):
    agent = creer_agent()
    r = client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement(consentement=False), headers=admin)
    assert r.status_code == 400 and "consentement" in r.text


def test_enrolement_chiffre_les_gabarits(client, admin, creer_agent):
    agent = creer_agent()
    r = client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement(), headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["gabarits_enregistres"] == 4
    assert client.get(f"/api/agents/{agent['id']}", headers=admin).json()["consentement_le"] is not None
    with SessionLocale() as db:
        gabarit = db.query(GabaritFacial).first()
        # Fernet : jeton chiffré, jamais les 512 octets bruts du vecteur
        assert gabarit.donnees_chiffrees.startswith(b"gAAAAA") and len(gabarit.donnees_chiffrees) > 512
        assert gabarit.pose == "face"


def test_enrolement_refuse_une_photo_quand_la_vivacite_est_exigee(client, admin, creer_agent, monkeypatch):
    """Une photo, même présentée sous plusieurs angles, ne montre pas de rotation 3D de la tête."""
    monkeypatch.setattr(biometrie, "VIVACITE_OBLIGATOIRE", True)
    agent = creer_agent()
    r = client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement(), headers=admin)
    assert r.status_code == 422 and "vivacité" in r.text


def test_enrolement_exige_une_vraie_photo_de_face(client, admin, creer_agent, monkeypatch):
    """Visage de trois quarts sur la pose « face » : refusé avec le seuil de production."""
    monkeypatch.setattr(biometrie, "ECART_MAX_FACE", 0.22)
    agent = creer_agent()
    r = client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement(), headers=admin)
    assert r.status_code == 422 and "photo de face est obligatoire" in r.text and "droit vers l" in r.text


def test_profil_trop_tourne_refuse(client, admin, creer_agent, monkeypatch):
    monkeypatch.setattr(biometrie, "ECART_MAX_PROFIL", 0.2)  # l'image de test (≈ 0,27) devient « trop de profil »
    agent = creer_agent()
    r = client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement(), headers=admin)
    assert r.status_code == 422 and "trop tournée" in r.text


def test_enrolement_refuse_image_sans_visage(client, admin, creer_agent):
    agent = creer_agent()
    noir = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
    r = client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement([noir] * 3), headers=admin)
    assert r.status_code == 422 and "aucun visage" in r.text


def test_analyse_en_direct_pour_l_enrolement(client, admin):
    r = client.post("/api/agents/enrolement/analyse", json={"image": images_visage(1)[0]}, headers=admin).json()
    assert r["nb_visages"] == 1 and r["taille_ok"] and 0.2 < r["lacet"] < 0.8
    assert r["luminosite"] in ("CORRECTE", "SOMBRE", "SUREXPOSEE") and r["nettete"] is not None


def test_un_visage_ne_peut_appartenir_qu_a_un_agent(client, admin, creer_agent):
    a1, a2 = creer_agent("EDM0001"), creer_agent("EDM0002")
    assert client.post(f"/api/agents/{a1['id']}/enrolement", json=enrolement(), headers=admin).status_code == 200
    r = client.post(f"/api/agents/{a2['id']}/enrolement", json=enrolement(), headers=admin)
    assert r.status_code == 422 and "EDM0001" in r.text


def test_analyse_signale_aussitot_un_visage_deja_enrole(client, admin, creer_agent):
    a1, a2 = creer_agent("EDM0001"), creer_agent("EDM0002")
    image = images_visage(1)[0]
    libre = client.post("/api/agents/enrolement/analyse", json={"image": image, "agent_id": a2["id"]}, headers=admin).json()
    assert libre["deja_enrole"] is None
    assert client.post(f"/api/agents/{a1['id']}/enrolement", json=enrolement(), headers=admin).status_code == 200
    r = client.post("/api/agents/enrolement/analyse", json={"image": image, "agent_id": a2["id"], "reference": image},
                    headers=admin).json()
    assert r["deja_enrole"]["matricule"] == "EDM0001" and r["deja_enrole"]["certain"]
    assert r["meme_personne"] is True  # même photo que la référence


def _vecteur(*composantes: tuple[int, float]):
    """Vecteur unitaire synthétique : chaque « personne » est un axe, une pose est un mélange d'axes."""
    import numpy as np
    v = np.zeros(128, np.float32)
    for axe, poids in composantes:
        v[axe] = poids
    return v / np.linalg.norm(v)


def test_enrolement_refuse_les_poses_d_une_autre_personne(client, admin, creer_agent):
    """Cas réel : deux personnes se relaient devant la caméra pendant l'enrôlement d'un même agent."""
    a1, a2 = creer_agent("EDM0001"), creer_agent("EDM0002")
    with SessionLocale() as db:  # EDM0001 (personne B, axe 1) est déjà enrôlé
        from server.app.securite import chiffrer_gabarit
        db.add(GabaritFacial(agent_id=a1["id"], pose="face", donnees_chiffrees=chiffrer_gabarit(_vecteur((1, 1.0)))))
        db.commit()
        face_a = _vecteur((0, 1.0))
        # Pose « gauche » prise par C, non enrôlé : ressemblance 0,31 avec la face de A, acceptée par l'ancien seuil (0,28)…
        gauche_c = _vecteur((0, 0.31), (3, 0.95))
        try:
            biometrie.verifier_gabarits(db, a2["id"], [("face", face_a), ("gauche", gauche_c)], True)
            raise AssertionError("poses de deux personnes acceptées")
        except biometrie.ErreurEnrolement as e:
            assert "même personne" in str(e)
        # … et B, déjà enrôlé, est reconnu même s'il ne fournit qu'une pose de côté.
        gauche_b = _vecteur((0, 0.62), (1, 0.79))
        try:
            biometrie.verifier_gabarits(db, a2["id"], [("face", face_a), ("gauche", gauche_b)], True)
            raise AssertionError("pose d'un agent déjà enrôlé acceptée")
        except biometrie.ErreurEnrolement as e:
            assert "EDM0001" in str(e)
        # Une vraie pose de côté de A reste acceptée.
        biometrie.verifier_gabarits(db, a2["id"], [("face", face_a), ("gauche", _vecteur((0, 0.8), (2, 0.6)))], True)


def test_suppression_des_donnees_biometriques(client, admin, creer_agent):
    agent = creer_agent()
    client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement(), headers=admin)
    assert client.delete(f"/api/agents/{agent['id']}/gabarits", headers=admin).status_code == 200
    fiche = client.get(f"/api/agents/{agent['id']}", headers=admin).json()
    assert fiche["nb_gabarits"] == 0 and fiche["consentement_le"] is None


def test_actions_sensibles_tracees_dans_l_audit(client, admin, creer_agent):
    agent = creer_agent()
    client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement(), headers=admin)
    client.get("/api/rapports/export.xlsx", headers=admin)
    actions = {l["action"] for l in client.get("/api/audit", headers=admin).json()}
    assert {"CONNEXION", "CREATION_AGENT", "ENROLEMENT", "EXPORT_RAPPORT"} <= actions


# --- Organisation (marque blanche) ----------------------------------------------
def test_personnalisation_de_l_organisation(client, admin):
    assert client.get("/api/organisation").json()["nom"]  # public : écran de connexion
    r = client.put("/api/organisation", json={"nom": "Société Minière du Sahel", "couleur_primaire": "#0A6E4F"},
                   headers=admin)
    assert r.status_code == 200 and r.json()["nom"] == "Société Minière du Sahel"
    assert client.put("/api/organisation", json={"couleur_primaire": "vert"}, headers=admin).status_code == 422
    logo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
    assert client.post("/api/organisation/logo", json={"image": logo}, headers=admin).json()["a_un_logo"] is True
    assert client.get("/api/organisation/logo").headers["content-type"] == "image/png"
    drh = jeton(client, "drh", "Drh@2026")
    assert client.put("/api/organisation", json={"nom": "X"}, headers=drh).status_code == 403
