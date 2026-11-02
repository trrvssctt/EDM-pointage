"""Terminal : reconnaissance, vivacité, automate de pointage, file locale et synchronisation après coupure."""
import socket
import threading
import time

import cv2
import numpy as np
import pytest
import uvicorn

from common.moteur_facial import Galerie, MoteurFacial, Visage, vecteur_vers_b64
from common.vivacite import DROITE, GAUCHE, DefiClignement, DefiVivacite
from server.app.main import app
from terminal.noyau import Configuration, NoyauTerminal
from terminal.service import IMAGES_STABLES, Automate
from tests.conftest import CLE_KATI, IMAGE_VISAGE, enrolement


def visage_synthetique(x_nez: float) -> Visage:
    """Yeux en x=100 et x=200, nez à la position donnée."""
    return Visage(np.array([50, 50, 200, 200, 100, 100, 200, 100, x_nez, 150, 110, 200, 190, 200, 0.95], np.float32))


# --- Vivacité ------------------------------------------------------------------
def test_vivacite_reussie_si_la_tete_tourne_dans_le_bon_sens():
    defi = DefiVivacite(visage_synthetique(150), direction=DROITE)
    assert [defi.mettre_a_jour(visage_synthetique(x)) for x in (145, 135, 125, 125, 125)][-1] is True


def test_vivacite_echoue_avec_une_photo_plane():
    """Une photo inclinée ou déplacée garde le nez au milieu des yeux."""
    defi = DefiVivacite(visage_synthetique(150), direction=GAUCHE)
    assert not any(defi.mettre_a_jour(visage_synthetique(150 + d)) for d in (0, 1, -1, 2, 0, 1, 2, -2))


def test_vivacite_echoue_dans_le_mauvais_sens():
    defi = DefiVivacite(visage_synthetique(150), direction=GAUCHE)
    assert not any(defi.mettre_a_jour(visage_synthetique(120)) for _ in range(10))


def test_clignement_exige_une_fermeture_franche(monkeypatch):
    sequence = iter([2, 2, 0, 2] + [2, 2, 0, 0, 0, 2])  # 1 image fermée : ignoré ; 3 images : clignement
    monkeypatch.setattr("common.vivacite.yeux_ouverts", lambda *_: next(sequence))
    defi, image = DefiClignement(), np.zeros((10, 10, 3), np.uint8)
    resultats = [defi.mettre_a_jour(visage_synthetique(150), image) for _ in range(10)]
    assert resultats.index(True) == 9


# --- Reconnaissance --------------------------------------------------------------
def test_identification_1_n():
    moteur = MoteurFacial()
    image = cv2.imread(str(IMAGE_VISAGE))
    vecteur = moteur.gabarit_enrolement(image)
    autre = np.random.default_rng(0).normal(size=128).astype(np.float32)
    autre /= np.linalg.norm(autre)
    galerie = Galerie([{"matricule": "A", "nom": "", "prenom": "", "gabarits": [vecteur_vers_b64(vecteur)]},
                       {"matricule": "B", "nom": "", "prenom": "", "gabarits": [vecteur_vers_b64(autre)]}])
    variante = moteur.gabarit_enrolement(cv2.resize(cv2.convertScaleAbs(image, alpha=1.2), None, fx=0.9, fy=0.9))
    assert galerie.identifier(variante)[0] == "A"
    assert galerie.identifier(-variante)[0] is None  # visage inconnu


# --- Automate de pointage (écran du terminal) ---------------------------------------
@pytest.fixture()
def automate(tmp_path, monkeypatch):
    monkeypatch.setattr("terminal.noyau.DOSSIER_DONNEES", tmp_path)
    moteur = MoteurFacial()
    image = cv2.resize(cv2.imread(str(IMAGE_VISAGE)), (640, 480))
    config = Configuration(url_serveur="http://127.0.0.1:9", code_terminal="T-TEST", cle_api="cle", anti_rebond_s=60,
                           defis=["tourner"])
    noyau = NoyauTerminal(config)
    noyau.galerie.charger([{"matricule": "EDM0001", "prenom": "Awa", "nom": "Traoré", "site_rattachement_id": 1,
                            "site_rattachement": "Siège", "tous_sites": True, "sites_autorises": [],
                            "gabarits": [vecteur_vers_b64(moteur.gabarit_enrolement(image))]}])
    a = Automate(noyau, moteur, config)
    a.camera_ok = True
    return a, image, moteur.visage_principal(image)


def _jusqua_defi(a, image, visage):
    for _ in range(IMAGES_STABLES):
        a.traiter(image, visage)
    assert a.etat == "DEFI" and a.candidat[0] == "EDM0001"


def test_photo_refusee_par_le_terminal(automate):
    a, image, visage = automate
    _jusqua_defi(a, image, visage)
    for _ in range(30):
        a.traiter(image, visage)  # photo immobile : le défi ne progresse pas
    a.defi.debut -= 60          # délai écoulé
    a.traiter(image, visage)
    assert a.etat == "REFUS" and a.refus["code"] == "FRAUDE"
    tentatives = a.noyau.stockage.en_attente("tentatives")
    assert tentatives[0]["motif"] == "ECHEC_VIVACITE" and tentatives[0]["matricule_suppose"] == "EDM0001"
    assert a.noyau.stockage.nb_en_attente() == 0  # aucun pointage


def test_pointage_reussi_puis_ce_n_est_pas_moi(automate, monkeypatch):
    a, image, visage = automate
    _jusqua_defi(a, image, visage)
    monkeypatch.setattr(a.defi, "mettre_a_jour", lambda *_: True)  # simule un visage réel qui tourne la tête
    a.traiter(image, visage)
    etat = a.instantane()
    assert etat["etat"] == "SUCCES" and etat["resultat"]["type"] == "ENTREE"
    assert etat["resultat"]["agent"]["initiales"] == "AT" and etat["resultat"]["hors_ligne"] is True
    assert a.noyau.stockage.nb_en_attente() == 1
    assert a.annuler() and a.etat == "INFO" and a.refus["code"] == "CONTESTE"
    assert a.noyau.stockage.nb_en_attente() == 0  # retiré de la file avant envoi
    assert a.noyau.stockage.en_attente("tentatives")[-1]["motif"] == "IDENTITE_CONTESTEE"


def test_choix_manuel_entree_sortie(automate, monkeypatch):
    a, image, visage = automate
    a.choisir_mode("SORTIE")
    _jusqua_defi(a, image, visage)
    monkeypatch.setattr(a.defi, "mettre_a_jour", lambda *_: True)
    a.traiter(image, visage)
    assert a.resultat["type"] == "SORTIE" and a.mode is None  # le choix manuel ne vaut que pour un pointage


def test_site_non_autorise_hors_ligne(automate, monkeypatch):
    a, image, visage = automate
    a.noyau.galerie.agents["EDM0001"].update(tous_sites=False, sites_autorises=[])
    a.noyau.synchro.config_serveur = {"site_id": 2, "site_nom": "Agence de Kati"}
    _jusqua_defi(a, image, visage)
    monkeypatch.setattr(a.defi, "mettre_a_jour", lambda *_: True)
    a.traiter(image, visage)
    assert a.etat == "INFO" and a.refus["code"] == "NON_AUTORISE"
    assert a.noyau.stockage.en_attente("tentatives")[-1]["motif"] == "SITE_NON_AUTORISE"


def test_visage_inconnu(automate):
    a, image, visage = automate
    a.noyau.galerie.charger([{"matricule": "X", "nom": "", "prenom": "", "gabarits": [
        vecteur_vers_b64(np.ones(128, np.float32) / np.sqrt(128))]}])
    for _ in range(IMAGES_STABLES):
        a.traiter(image, visage)
    assert a.etat == "INFO" and a.refus["code"] == "INCONNU"


# --- Synchronisation réelle avec un serveur HTTP ---------------------------------------
@pytest.fixture()
def serveur(db_vide):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    class Pilote:
        url = f"http://127.0.0.1:{port}"
        fil = None

        def demarrer(self):
            srv.should_exit = False
            self.fil = threading.Thread(target=srv.run, daemon=True)
            self.fil.start()
            while not srv.started:
                time.sleep(0.05)

        def arreter(self):
            srv.should_exit = True
            self.fil.join()
            srv.started = False

    pilote = Pilote()
    yield pilote
    if pilote.fil and pilote.fil.is_alive():
        pilote.arreter()


def test_pointages_conserves_hors_ligne_puis_synchronises(serveur, client, admin, creer_agent, tmp_path, monkeypatch):
    monkeypatch.setattr("terminal.noyau.DOSSIER_DONNEES", tmp_path)
    creer_agent("EDM0001")
    noyau = NoyauTerminal(Configuration(url_serveur=serveur.url, code_terminal="T-KATI", cle_api=CLE_KATI,
                                        anti_rebond_s=0))

    # 1. Coupure réseau : le terminal enregistre localement
    with pytest.raises(Exception):
        noyau.synchro.cycle()
    entree = noyau.enregistrer("EDM0001", 0.8)
    sortie = noyau.enregistrer("EDM0001", 0.8)
    assert (entree.message, sortie.message) == ("ENTREE", "SORTIE")
    assert entree.pointage["hors_ligne"] is True
    assert noyau.stockage.nb_en_attente() == 2

    # 2. Retour du réseau : synchronisation
    serveur.demarrer()
    noyau.synchro.cycle()
    assert noyau.stockage.nb_en_attente() == 0
    pointages = client.get("/api/pointages", headers=admin).json()
    assert pointages["total"] == 2
    assert {p["type"] for p in pointages["elements"]} == {"ENTREE", "SORTIE"}
    assert all(p["synchro"] == "DIFFERE" and p["site"] == "Agence de Kati" for p in pointages["elements"])

    # 3. Renvoi accidentel (réponse perdue) : aucun doublon côté serveur
    with noyau.stockage._connexion() as cx:
        cx.execute("UPDATE pointages SET synchronise = 0")
    noyau.synchro.cycle()
    assert client.get("/api/pointages", headers=admin).json()["total"] == 2

    # 4. « Ce n'est pas moi » sur un pointage déjà transmis : annulation envoyée au serveur
    noyau.annuler(sortie.pointage)
    noyau.synchro.cycle()
    alertes = {p["type"]: p["alerte"] for p in client.get("/api/pointages?type=SORTIE", headers=admin).json()["elements"]}
    assert alertes == {"SORTIE": "ANNULE"}


def test_identite_du_site_et_galerie_disponibles_hors_ligne(serveur, client, admin, creer_agent, tmp_path, monkeypatch):
    monkeypatch.setattr("terminal.noyau.DOSSIER_DONNEES", tmp_path)
    agent = creer_agent("EDM0001")
    client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement(), headers=admin)
    logo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
    client.post("/api/organisation/logo", json={"image": logo}, headers=admin)
    config = Configuration(url_serveur=serveur.url, code_terminal="T-KATI", cle_api=CLE_KATI)
    serveur.demarrer()
    NoyauTerminal(config).synchro.cycle()
    serveur.arreter()
    # Redémarrage du terminal sans réseau : galerie, site et logo relus depuis le stockage local
    noyau = NoyauTerminal(config)
    assert len(noyau.galerie) == 1
    assert noyau.synchro.config_serveur["site_nom"] == "Agence de Kati"
    assert noyau.stockage.charger_logo()[1] == "image/png"
    assert b"EDM0001" not in (tmp_path / "T-KATI" / "galerie.chiffree").read_bytes()  # cache chiffré
