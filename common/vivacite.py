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
l'identité est revérifiée à la fin du défi (le visage ne doit pas changer). Limite : une
vidéo où la personne tourne la tête des deux côtés, rejouée sur un téléphone, peut réussir
le défi de rotation ; la photo ou l'écran immobile, lui, est écarté.
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
    """Défi de rotation de la tête.

    La progression est mesurée depuis la position la plus opposée vue pendant le défi : une personne qui part
    du mauvais côté (gauche et droite se confondent facilement) puis tourne dans le bon sens réussit. Avec
    retour_face, elle doit ensuite revenir vers la caméra : l'identité est alors revérifiée sur un visage de face,
    plus fiable qu'un visage tourné. amplitude (variation totale du lacet) distingue une photo ou un écran,
    parfaitement rigides, d'une personne qui bouge sans suivre la consigne."""
    type = ROTATION

    def __init__(self, visage_initial: Visage, camera_miroir: bool = False, direction: str | None = None,
                 images_requises: int = IMAGES_CONSECUTIVES, duree_max: float = DUREE_MAX, retour_face: bool = False):
        self.direction = direction or random.choice((DROITE, GAUCHE))
        self.reference = rapport_lacet(visage_initial)
        self.debut = time.monotonic()
        self.duree_max = duree_max
        self._images_requises = images_requises
        self._retour_face = retour_face
        # Caméra non inversée : la droite de l'agent apparaît à gauche de l'image, donc tourner vers sa droite
        # fait diminuer le rapport. _sens ramène la direction demandée à « le rapport augmente ».
        self._sens = (-1.0 if self.direction == DROITE else 1.0) * (-1.0 if camera_miroir else 1.0)
        self._plancher = self._sommet = self._sens * self.reference
        self._lacets = [self.reference]
        self._tenu = 0
        self.tourne = False       # rotation dans le bon sens obtenue (phase de retour si retour_face)
        self.sens_inverse = False  # dernière image : tête tournée du mauvais côté (indication à l'écran)
        self.reussi = False

    @property
    def consigne(self) -> str:
        if self.tourne:
            return "Revenez face à la caméra"
        return f"Tournez lentement la tête vers la {self.direction}"

    @property
    def expire(self) -> bool:
        return not self.reussi and time.monotonic() - self.debut > self.duree_max

    @property
    def amplitude(self) -> float:
        """Variation du lacet pendant le défi, entre les 10e et 90e centiles pour ignorer le tremblement des
        points de repère (un pixel d'écart sur le nez change le rapport de 0,02) : quasi nulle pour une photo."""
        return float(np.percentile(self._lacets, 90) - np.percentile(self._lacets, 10))

    def mettre_a_jour(self, visage: Visage, image: np.ndarray | None = None) -> bool:
        """À appeler à chaque image. Renvoie True quand le défi est réussi."""
        if self.reussi:
            return True
        lacet = rapport_lacet(visage)
        self._lacets.append(lacet)
        valeur = self._sens * lacet
        if not self.tourne:
            self.sens_inverse = valeur <= self._sens * self.reference - ECART_REQUIS
            self._plancher = min(self._plancher, valeur)
            self._tenu = self._tenu + 1 if valeur - self._plancher >= ECART_REQUIS else 0
            if self._tenu >= self._images_requises:
                self.tourne, self.sens_inverse = True, False
                self._sommet = valeur
                self.reussi = not self._retour_face
            return self.reussi
        self._sommet = max(self._sommet, valeur)
        if self._sommet - valeur >= ECART_REQUIS * 0.7:  # nettement revenu vers la caméra
            self.reussi = True
        return self.reussi


class DefiClignement:
    """Défi de clignement des yeux : ouverts -> fermés (1 à 10 images) -> ouverts."""
    type = CLIGNEMENT
    direction = None
    consigne = "Clignez des yeux"

    def __init__(self, duree_max: float = DUREE_MAX):
        self.debut = time.monotonic()
        self.duree_max = duree_max
        self.reussi = False
        self._ouverts_vus = 0
        self._fermes = 0

    @property
    def expire(self) -> bool:
        return not self.reussi and time.monotonic() - self.debut > self.duree_max

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
