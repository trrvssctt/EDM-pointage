"""Moteur de reconnaissance faciale partagé par le serveur central et les terminaux.

Détection : YuNet (OpenCV Zoo)  -> boîte englobante + 5 points de repère.
Reconnaissance : SFace (OpenCV Zoo) -> vecteur caractéristique de 128 dimensions.

Seuls ces vecteurs (gabarits) sont conservés : aucune photo n'est stockée.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

DOSSIER_MODELES = Path(os.environ.get("EDM_DOSSIER_MODELES", Path(__file__).resolve().parent.parent / "models"))
MODELE_DETECTION = "face_detection_yunet_2023mar.onnx"
MODELE_RECONNAISSANCE = "face_recognition_sface_2021dec.onnx"

# Seuil de similarité cosinus recommandé pour SFace : 0.363. On prend un peu
# de marge pour réduire les fausses acceptations.
SEUIL_SIMILARITE = float(os.environ.get("EDM_SEUIL_SIMILARITE", "0.42"))
TAILLE_MIN_VISAGE = 80  # pixels (largeur de la boîte)
SCORE_MIN_DETECTION = 0.85
DIMENSION = 128


class ErreurVisage(ValueError):
    """Image inexploitable (aucun visage, plusieurs visages, visage trop petit...)."""


@dataclass
class Visage:
    brut: np.ndarray  # ligne YuNet : x, y, w, h, 5 points (x, y), score

    @property
    def boite(self) -> tuple[int, int, int, int]:
        x, y, w, h = self.brut[:4]
        return int(x), int(y), int(w), int(h)

    @property
    def score(self) -> float:
        return float(self.brut[14])

    @property
    def largeur(self) -> float:
        return float(self.brut[2])

    @property
    def points(self) -> np.ndarray:
        """5 points : oeil, oeil, nez, coin de bouche, coin de bouche."""
        return self.brut[4:14].reshape(5, 2)


class MoteurFacial:
    def __init__(self, dossier_modeles: Path | str = DOSSIER_MODELES):
        dossier = Path(dossier_modeles)
        detection = dossier / MODELE_DETECTION
        reconnaissance = dossier / MODELE_RECONNAISSANCE
        for f in (detection, reconnaissance):
            if not f.exists():
                raise FileNotFoundError(f"Modèle manquant : {f} (lancez ./setup.sh)")
        self._detecteur = cv2.FaceDetectorYN.create(str(detection), "", (320, 320), 0.7, 0.3, 5000)
        self._reconnaisseur = cv2.FaceRecognizerSF.create(str(reconnaissance), "")

    def detecter(self, image: np.ndarray) -> list[Visage]:
        h, w = image.shape[:2]
        if w < 64 or h < 64:  # trop petite pour contenir un visage exploitable
            return []
        self._detecteur.setInputSize((w, h))
        try:
            _, visages = self._detecteur.detect(image)
        except cv2.error:
            return []
        if visages is None:
            return []
        return [Visage(v) for v in visages]

    def visage_principal(self, image: np.ndarray) -> Visage | None:
        visages = self.detecter(image)
        if not visages:
            return None
        return max(visages, key=lambda v: v.largeur)

    def gabarit(self, image: np.ndarray, visage: Visage) -> np.ndarray:
        aligne = self._reconnaisseur.alignCrop(image, visage.brut)
        vecteur = self._reconnaisseur.feature(aligne).flatten().astype(np.float32)
        return vecteur / np.linalg.norm(vecteur)

    def gabarit_enrolement(self, image: np.ndarray) -> np.ndarray:
        """Contrôle qualité strict pour l'enrôlement : un seul visage net et assez grand."""
        visages = [v for v in self.detecter(image) if v.score >= SCORE_MIN_DETECTION]
        if not visages:
            raise ErreurVisage("aucun visage détecté")
        if len(visages) > 1:
            raise ErreurVisage("plusieurs visages détectés")
        visage = visages[0]
        if visage.largeur < TAILLE_MIN_VISAGE:
            raise ErreurVisage("visage trop petit : rapprochez-vous de la caméra")
        return self.gabarit(image, visage)


def similarite(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def decoder_image(donnees: bytes | str) -> np.ndarray:
    """Décode une image JPEG/PNG (octets ou base64, éventuellement data-URL)."""
    if isinstance(donnees, str):
        if donnees.startswith("data:"):
            donnees = donnees.split(",", 1)[1]
        donnees = base64.b64decode(donnees)
    image = cv2.imdecode(np.frombuffer(donnees, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ErreurVisage("image illisible")
    return image


def vecteur_vers_b64(vecteur: np.ndarray) -> str:
    return base64.b64encode(vecteur.astype(np.float32).tobytes()).decode()


def b64_vers_vecteur(texte: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(texte), dtype=np.float32).copy()


class Galerie:
    """Ensemble des gabarits connus d'un terminal, pour l'identification 1:N."""

    def __init__(self, entrees: list[dict] | None = None):
        self.agents: dict[str, dict] = {}
        self._matrice = np.zeros((0, DIMENSION), np.float32)
        self._proprietaires: list[str] = []
        if entrees:
            self.charger(entrees)

    def charger(self, entrees: list[dict]) -> None:
        """entrees : [{matricule, nom, prenom, gabarits: [base64, ...]}, ...]"""
        vecteurs, proprietaires, agents = [], [], {}
        for e in entrees:
            agents[e["matricule"]] = {k: v for k, v in e.items() if k != "gabarits"}
            for g in e["gabarits"]:
                vecteurs.append(b64_vers_vecteur(g))
                proprietaires.append(e["matricule"])
        self.agents = agents
        self._proprietaires = proprietaires
        self._matrice = np.vstack(vecteurs) if vecteurs else np.zeros((0, DIMENSION), np.float32)

    def __len__(self) -> int:
        return len(self.agents)

    def identifier(self, vecteur: np.ndarray, seuil: float = SEUIL_SIMILARITE) -> tuple[str | None, float]:
        """Renvoie (matricule, score) du meilleur candidat, ou (None, score) si sous le seuil."""
        if not self._proprietaires:
            return None, 0.0
        scores = self._matrice @ vecteur
        i = int(np.argmax(scores))
        meilleur = float(scores[i])
        if meilleur < seuil:
            return None, meilleur
        return self._proprietaires[i], meilleur

    def score_agent(self, matricule: str, vecteur: np.ndarray) -> float:
        indices = [i for i, m in enumerate(self._proprietaires) if m == matricule]
        if not indices:
            return 0.0
        return float(np.max(self._matrice[indices] @ vecteur))
