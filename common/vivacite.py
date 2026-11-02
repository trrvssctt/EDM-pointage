"""Détection de vivacité (anti-fraude photo / écran / vidéo) par défi-réponse aléatoire.

Deux défis, tirés au hasard :

* Rotation de la tête : sur un visage réel (3D), le nez se déplace nettement par
  rapport aux yeux quand la tête tourne. Sur une photo ou un écran (surface plane),
  même inclinés, ce rapport reste constant : une rotation d'un plan comprime
  l'image uniformément et le nez reste au milieu des yeux.
* Clignement des yeux : les yeux, détectés ouverts, doivent disparaître brièvement
  (fermeture de 2 à 10 images) puis réapparaître. Une photo ne cligne pas.
  Si les yeux ne sont pas détectables (lunettes teintées, contre-jour), le terminal
  bascule automatiquement sur le défi de rotation.

Le tirage aléatoire (défi et direction) empêche de rejouer une vidéo préparée, et
l'identité est revérifiée à la fin du défi (le visage ne doit pas changer).
"""
from __future__ import annotations

import random
import time

import cv2
import numpy as np

from common.moteur_facial import Visage

ECART_REQUIS = 0.13       # déplacement relatif minimal du nez (rotation)
IMAGES_CONSECUTIVES = 3   # nombre d'images où la pose doit être tenue
DUREE_MAX = 7.0           # secondes
DROITE, GAUCHE = "droite", "gauche"
ROTATION, CLIGNEMENT = "tourner", "cligner"

_detecteur_yeux = None


def rapport_lacet(visage: Visage) -> float:
    """Position horizontale du nez entre les deux yeux (≈0.5 de face)."""
    p = visage.points
    x_yeux = sorted((p[0][0], p[1][0]))
    ecart = x_yeux[1] - x_yeux[0]
    if ecart < 1:
        return 0.5
    return float((p[2][0] - x_yeux[0]) / ecart)


def rapport_tangage(visage: Visage) -> float:
    """Position verticale du nez entre la ligne des yeux et celle de la bouche (≈0.5 de face)."""
    p = visage.points
    y_yeux = (p[0][1] + p[1][1]) / 2
    y_bouche = (p[3][1] + p[4][1]) / 2
    ecart = y_bouche - y_yeux
    if ecart < 1:
        return 0.5
    return float((p[2][1] - y_yeux) / ecart)


def yeux_ouverts(image: np.ndarray, visage: Visage) -> int:
    """Nombre d'yeux ouverts détectés dans la moitié haute du visage (détecteur de Haar)."""
    global _detecteur_yeux
    if _detecteur_yeux is None:
        _detecteur_yeux = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml")
    x, y, w, h = visage.boite
    zone = image[max(0, y):max(0, y) + int(h * 0.6), max(0, x):max(0, x) + w]
    if zone.size == 0:
        return 0
    gris = cv2.equalizeHist(cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY))
    yeux = _detecteur_yeux.detectMultiScale(gris, 1.1, 4, minSize=(max(8, w // 10), max(8, w // 10)))
    return len(yeux)


class DefiVivacite:
    """Défi de rotation de la tête."""
    type = ROTATION

    def __init__(self, visage_initial: Visage, camera_miroir: bool = False, direction: str | None = None):
        self.direction = direction or random.choice((DROITE, GAUCHE))
        self.reference = rapport_lacet(visage_initial)
        self.debut = time.monotonic()
        self._miroir = camera_miroir
        self._tenu = 0
        self.reussi = False

    @property
    def consigne(self) -> str:
        return f"Tournez lentement la tête vers la {self.direction}"

    @property
    def expire(self) -> bool:
        return not self.reussi and time.monotonic() - self.debut > DUREE_MAX

    def mettre_a_jour(self, visage: Visage, image: np.ndarray | None = None) -> bool:
        """À appeler à chaque image. Renvoie True quand le défi est réussi."""
        delta = rapport_lacet(visage) - self.reference
        # Caméra non inversée : la droite de l'agent apparaît à gauche de
        # l'image, donc tourner vers sa droite fait diminuer le rapport.
        if self._miroir:
            delta = -delta
        attendu = -delta if self.direction == DROITE else delta
        self._tenu = self._tenu + 1 if attendu >= ECART_REQUIS else 0
        if self._tenu >= IMAGES_CONSECUTIVES:
            self.reussi = True
        return self.reussi


class DefiClignement:
    """Défi de clignement des yeux : ouverts -> fermés (1 à 10 images) -> ouverts."""
    type = CLIGNEMENT
    direction = None
    consigne = "Clignez des yeux"

    def __init__(self):
        self.debut = time.monotonic()
        self.reussi = False
        self._ouverts_vus = 0
        self._fermes = 0

    @property
    def expire(self) -> bool:
        return not self.reussi and time.monotonic() - self.debut > DUREE_MAX

    def mettre_a_jour(self, visage: Visage, image: np.ndarray | None = None) -> bool:
        if image is None:
            return False
        ouverts = yeux_ouverts(image, visage) > 0
        if ouverts:
            if self._ouverts_vus >= 2 and 2 <= self._fermes <= 10:  # au moins 2 images : un vrai clignement
                self.reussi = True
            self._ouverts_vus += 1
            self._fermes = 0
        elif self._ouverts_vus >= 2:
            self._fermes += 1
            if self._fermes > 10:  # yeux fermés trop longtemps ou regard détourné : on recommence
                self._ouverts_vus, self._fermes = 0, 0
        return self.reussi


def choisir_defi(image: np.ndarray, visage: Visage, types: tuple[str, ...] = (ROTATION, CLIGNEMENT),
                 camera_miroir: bool = False):
    """Tire un défi au hasard ; le clignement n'est proposé que si les yeux sont détectables."""
    choix = random.choice(types)
    if choix == CLIGNEMENT and yeux_ouverts(image, visage) > 0:
        return DefiClignement()
    return DefiVivacite(visage, camera_miroir)
