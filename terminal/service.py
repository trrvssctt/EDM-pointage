"""Service local du terminal de pointage.

Il pilote la caméra, la reconnaissance faciale, le contrôle de vivacité et la file
hors ligne, et sert l'écran tactile (application React en mode kiosque) sur
http://127.0.0.1:<port_local>.

Usage : python -m terminal.service --config terminal/config/TRM-BKO-03.json [--camera N|video.mp4]
"""
from __future__ import annotations

import argparse
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from common.moteur_facial import SCORE_MIN_DETECTION, SEUIL_SIMILARITE, MoteurFacial, Visage
from common.vivacite import ROTATION, choisir_defi
from terminal.noyau import ENTREE, SORTIE, Configuration, NoyauTerminal

INTERFACE = Path(__file__).resolve().parents[1] / "frontend" / "dist"
journal = logging.getLogger("terminal")

TAILLE_MIN_POINTAGE = 90         # largeur minimale du visage (px)
IMAGES_STABLES = 8               # « Restez immobile une seconde »
DUREE_SUCCES = 5.0               # « Cet écran se ferme dans 5 s »
DUREE_INFO = 4.0                 # visage inconnu, déjà pointé, site non autorisé
DUREE_REFUS_MAX = 20.0           # écran de fraude : retour automatique
DELAI_JOURNAL_INCONNU = 10.0     # limite la journalisation des visages inconnus
DUREE_MODE_FORCE = 30.0          # le choix manuel Entrée / Sortie expire


def initiales(prenom: str, nom: str) -> str:
    return ((prenom[:1] or "") + (nom[:1] or "")).upper() or "?"


class Automate:
    """Machine à états du pointage : ATTENTE → ANALYSE → DEFI → SUCCES / REFUS / INFO."""

    def __init__(self, noyau: NoyauTerminal, moteur: MoteurFacial, config: Configuration):
        self.noyau, self.moteur, self.config = noyau, moteur, config
        self.verrou = threading.RLock()
        self.etat = "ATTENTE"
        self.stables = 0
        self.defi = None
        self.candidat: tuple[str, float] | None = None
        self.absences = 0
        self.fin_etat = 0.0
        self.resultat: dict | None = None
        self.refus: dict | None = None
        self.dernier_inconnu = 0.0
        self.mode: str | None = None
        self.mode_expire = 0.0
        self.visage: list[float] | None = None
        self.camera_ok = False

    # --- Actions de l'écran tactile -----------------------------------------
    def choisir_mode(self, mode: str | None) -> None:
        with self.verrou:
            self.mode = mode
            self.mode_expire = time.monotonic() + DUREE_MODE_FORCE

    def annuler(self) -> bool:
        with self.verrou:
            if self.etat != "SUCCES" or not self.resultat:
                return False
            self.noyau.annuler(self.resultat["pointage"])
            self._informer("CONTESTE", "Pointage annulé", "Votre pointage a été annulé. Placez-vous à nouveau devant "
                                                          "la caméra ou adressez-vous à votre responsable.")
            return True

    def reessayer(self) -> None:
        with self.verrou:
            self._retour_attente()

    def appeler_superviseur(self) -> None:
        with self.verrou:
            matricule = self.candidat[0] if self.candidat else None
            self.noyau.rejeter("APPEL_SUPERVISEUR", matricule)
            self._informer("SUPERVISEUR", "Superviseur prévenu",
                           "Votre demande d'assistance a été transmise. Merci de patienter.", duree=8)

    # --- Transitions ---------------------------------------------------------
    def _retour_attente(self):
        self.etat, self.stables, self.defi, self.candidat = "ATTENTE", 0, None, None
        self.resultat = self.refus = None

    def _informer(self, code: str, titre: str, message: str, duree: float = DUREE_INFO, etat: str = "INFO"):
        self.etat = etat
        self.refus = {"code": code, "titre": titre, "message": message}
        self.fin_etat = time.monotonic() + duree

    def _fraude(self, motif: str, score: float):
        matricule = self.candidat[0] if self.candidat else None
        self.noyau.rejeter(motif, matricule, score)
        self._informer("FRAUDE", "Photo ou écran détecté",
                       "Le visage présenté semble provenir d'une image. Présentez votre visage devant la caméra, "
                       "sans écran ni photo.", duree=DUREE_REFUS_MAX, etat="REFUS")

    def traiter(self, image: np.ndarray, visage: Visage | None) -> None:
        with self.verrou:
            h, w = image.shape[:2]
            self.visage = ([v / d for v, d in zip(visage.boite, (w, h, w, h))] if visage else None)
            if self.mode and time.monotonic() > self.mode_expire:
                self.mode = None
            if self.etat in ("SUCCES", "INFO", "REFUS"):
                if time.monotonic() > self.fin_etat:
                    self._retour_attente()
                return

            if self.etat in ("ATTENTE", "ANALYSE"):
                utilisable = (visage is not None and visage.largeur >= TAILLE_MIN_POINTAGE
                              and visage.score >= SCORE_MIN_DETECTION)
                self.stables = self.stables + 1 if utilisable else 0
                self.etat = "ANALYSE" if self.stables else "ATTENTE"
                if self.stables < IMAGES_STABLES:
                    return
                if len(self.noyau.galerie) == 0:
                    self._informer("GALERIE_VIDE", "Terminal non initialisé",
                                   "Aucun agent enrôlé n'est encore disponible sur ce terminal. "
                                   "Une synchronisation avec le serveur central est nécessaire.")
                    return
                matricule, score = self.noyau.identifier(self.moteur.gabarit(image, visage))
                if matricule is None:
                    if time.monotonic() - self.dernier_inconnu > DELAI_JOURNAL_INCONNU:
                        self.noyau.rejeter("VISAGE_INCONNU", None, score)
                        self.dernier_inconnu = time.monotonic()
                    self._informer("INCONNU", "Visage non reconnu",
                                   "Votre visage n'est pas enrôlé ou n'a pas pu être reconnu. "
                                   "Rapprochez-vous de la caméra ou adressez-vous au service RH.")
                    return
                agent = self.noyau.agent(matricule)
                if self.noyau.deja_pointe(matricule):
                    self._informer("DEJA", f"Bonjour {agent.get('prenom', '')}",
                                   "Votre pointage vient déjà d'être enregistré.")
                    return
                self.candidat = (matricule, score)
                self.defi = choisir_defi(image, visage, tuple(self.config.defis) or (ROTATION,),
                                         self.config.camera_miroir)
                self.absences = 0
                self.etat = "DEFI"
                return

            if self.etat == "DEFI":
                matricule, score = self.candidat
                if visage is None:
                    self.absences += 1
                    if self.absences > 20:
                        self._fraude("ECHEC_VIVACITE", score)
                    return
                self.absences = 0
                if self.defi.expire:
                    self._fraude("ECHEC_VIVACITE", score)
                    return
                if not self.defi.mettre_a_jour(visage, image):
                    return
                # Revérification de l'identité à la fin du défi : la personne n'a pas changé.
                score_final = self.noyau.score_agent(matricule, self.moteur.gabarit(image, visage))
                if score_final < SEUIL_SIMILARITE * 0.85:
                    self._fraude("CHANGEMENT_VISAGE", score_final)
                    return
                r = self.noyau.enregistrer(matricule, max(score, score_final), self.mode)
                agent = self.noyau.agent(matricule)
                if not r.enregistre:
                    if r.message == "SITE_NON_AUTORISE":
                        self._informer("NON_AUTORISE", "Pointage non autorisé sur ce site",
                                       f"{agent.get('prenom', '')}, vous n'êtes pas autorisé(e) à pointer sur ce site. "
                                       "Adressez-vous à votre responsable.")
                    else:
                        self._informer("DEJA", f"Bonjour {agent.get('prenom', '')}",
                                       "Votre pointage vient déjà d'être enregistré.")
                    return
                self.mode = None
                self.resultat = {
                    "type": r.message, "pointage": r.pointage,
                    "agent": {"prenom": agent.get("prenom", ""), "nom": agent.get("nom", ""), "matricule": matricule,
                              "initiales": initiales(agent.get("prenom", ""), agent.get("nom", ""))},
                    "heure": datetime.now().strftime("%H:%M:%S"),
                    "site_rattachement": agent.get("site_rattachement", ""), "hors_rattachement": r.hors_rattachement,
                    "hors_ligne": r.pointage["hors_ligne"],
                }
                self.etat = "SUCCES"
                self.fin_etat = time.monotonic() + DUREE_SUCCES

    def instantane(self) -> dict:
        with self.verrou:
            synchro = self.noyau.synchro
            site = synchro.config_serveur
            maintenant = time.monotonic()
            propose = self.mode or (ENTREE if datetime.now().hour < 12 else SORTIE)
            defi = None
            if self.etat == "DEFI" and self.defi:
                defi = {"type": self.defi.type, "direction": self.defi.direction, "consigne": self.defi.consigne,
                        "restant": max(0, round(7 - (maintenant - self.defi.debut), 1))}
            resultat = None
            if self.resultat:
                resultat = {k: v for k, v in self.resultat.items() if k != "pointage"}
            return {
                "etat": self.etat if self.camera_ok else "CAMERA",
                "visage": self.visage, "progression": min(1.0, self.stables / IMAGES_STABLES),
                "defi": defi, "resultat": resultat, "refus": self.refus,
                "fin_dans": max(0, int(self.fin_etat - maintenant + 0.99)) if self.etat in ("SUCCES", "INFO", "REFUS")
                else None,
                "mode": self.mode, "type_propose": propose,
                "terminal": {
                    "code": self.config.code_terminal, "site": site.get("site_nom", ""),
                    "reseau": synchro.etat, "message_reseau": synchro.message,
                    "en_attente": self.noyau.stockage.nb_en_attente(), "agents": len(self.noyau.galerie),
                    "organisation": site.get("organisation", {}),
                },
                "horloge": datetime.now().isoformat(timespec="seconds"),
            }


class Camera(threading.Thread):
    """Capture, analyse et diffusion des images (flux MJPEG pour l'écran)."""

    def __init__(self, automate: Automate, moteur: MoteurFacial, source: int | str, miroir: bool):
        super().__init__(daemon=True, name="camera")
        self.automate, self.moteur, self.source, self.miroir = automate, moteur, source, miroir
        self.jpeg: bytes | None = None
        self.nouvelle_image = threading.Condition()
        self.actif = True

    def run(self) -> None:
        while self.actif:
            capture = cv2.VideoCapture(self.source)
            if not capture.isOpened():
                self.automate.camera_ok = False
                journal.error("Caméra %r indisponible, nouvel essai dans 3 s", self.source)
                time.sleep(3)
                continue
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            fichier = isinstance(self.source, str)
            pause = 1 / (capture.get(cv2.CAP_PROP_FPS) or 15) if fichier else 0
            self.automate.camera_ok = True
            while self.actif:
                ok, image = capture.read()
                if not ok:
                    if fichier:  # vidéo de démonstration : lecture en boucle
                        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    self.automate.camera_ok = False
                    break
                self.automate.traiter(image, self.moteur.visage_principal(image))
                affichage = image if self.miroir else cv2.flip(image, 1)  # effet miroir pour l'agent
                ok, tampon = cv2.imencode(".jpg", affichage, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    with self.nouvelle_image:
                        self.jpeg = tampon.tobytes()
                        self.nouvelle_image.notify_all()
                if pause:
                    time.sleep(pause)
            capture.release()

    def flux(self):
        while True:
            with self.nouvelle_image:
                self.nouvelle_image.wait(timeout=2)
                image = self.jpeg
            if image:
                yield b"--image\r\nContent-Type: image/jpeg\r\n\r\n" + image + b"\r\n"


class Mode(BaseModel):
    mode: str | None = None


def creer_application(config: Configuration) -> FastAPI:
    noyau = NoyauTerminal(config)
    moteur = MoteurFacial()
    automate = Automate(noyau, moteur, config)
    camera = Camera(automate, moteur, config.camera, config.camera_miroir)

    @asynccontextmanager
    async def cycle_de_vie(_: FastAPI):
        noyau.demarrer()
        camera.start()
        yield
        camera.actif = False
        noyau.arreter()

    app = FastAPI(title=f"Terminal {config.code_terminal}", docs_url=None, redoc_url=None, lifespan=cycle_de_vie)

    @app.get("/api/etat")
    def etat():
        return automate.instantane()

    @app.get("/video.mjpg")
    def video():
        return StreamingResponse(camera.flux(), media_type="multipart/x-mixed-replace; boundary=image")

    @app.post("/api/mode")
    def mode(m: Mode):
        if m.mode not in (None, ENTREE, SORTIE):
            raise HTTPException(400, "Mode inconnu")
        automate.choisir_mode(m.mode)
        return automate.instantane()

    @app.post("/api/annuler")
    def annuler():
        if not automate.annuler():
            raise HTTPException(409, "Aucun pointage à annuler")
        return automate.instantane()

    @app.post("/api/reessayer")
    def reessayer():
        automate.reessayer()
        return automate.instantane()

    @app.post("/api/superviseur")
    def superviseur():
        automate.appeler_superviseur()
        return automate.instantane()

    @app.get("/api/logo")
    def logo():
        contenu = noyau.stockage.charger_logo()
        if contenu is None:
            return Response(status_code=204)
        return Response(contenu[0], media_type=contenu[1])

    if (INTERFACE / "assets").exists():
        app.mount("/assets", StaticFiles(directory=INTERFACE / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def ecran():
        page = INTERFACE / "terminal.html"
        if not page.exists():
            raise HTTPException(503, "Interface non compilée : lancez ./setup.sh")
        return FileResponse(page)

    app.state.automate, app.state.noyau, app.state.camera = automate, noyau, camera
    return app


def main():
    parser = argparse.ArgumentParser(description="Service du terminal de pointage")
    parser.add_argument("--config", required=True, help="fichier JSON de configuration du terminal")
    parser.add_argument("--camera", help="index de caméra ou chemin d'une vidéo (remplace la configuration)")
    parser.add_argument("--port", type=int, help="port local de l'écran (défaut : configuration, 8100)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = Configuration.charger(args.config)
    if args.camera is not None:
        config.camera = int(args.camera) if args.camera.isdigit() else args.camera
    if args.port:
        config.port_local = args.port
    uvicorn.run(creer_application(config), host="127.0.0.1", port=config.port_local, log_level="warning")


if __name__ == "__main__":
    main()
