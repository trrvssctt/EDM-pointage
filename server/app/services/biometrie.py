"""Enrôlement biométrique guidé (5 poses), contrôle qualité et galerie distribuée aux terminaux."""
from __future__ import annotations

import hashlib
import os
import threading

import cv2
import numpy as np
from sqlalchemy.orm import Session, joinedload

from common.moteur_facial import (SEUIL_SIMILARITE, ErreurVisage, Galerie, MoteurFacial, Visage, decoder_image,
                                  similarite, vecteur_vers_b64)
from common.vivacite import rapport_lacet, rapport_tangage
from server.app.models import Agent, GabaritFacial
from server.app.securite import chiffrer_gabarit, dechiffrer_gabarit

# Écart de lacet minimal entre les poses « gauche » et « droite » : preuve d'un visage en relief.
ECART_VIVACITE_ENROLEMENT = 0.15
# Orientation acceptée (lacet : position du nez entre les yeux, 0,5 = de face). Au-delà de ces limites,
# le visage est trop de profil : le modèle SFace, conçu pour des visages proches de la face, produit alors
# des gabarits peu distinctifs (deux profils de personnes différentes finissent par se ressembler).
ECART_MAX_FACE = float(os.environ.get("EDM_ENROLEMENT_ECART_FACE", "0.22"))
ECART_MAX_PROFIL = 0.40
# Ressemblance minimale de chaque pose avec la photo de face de la même personne. 0,363 est le seuil
# « même personne » publié pour SFace (similarité cosinus) : en dessous, une autre personne a pu prendre la pose.
SEUIL_COHERENCE = float(os.environ.get("EDM_ENROLEMENT_COHERENCE", "0.36"))
VIVACITE_OBLIGATOIRE = os.environ.get("EDM_ENROLEMENT_VIVACITE_OBLIGATOIRE", "1") != "0"

_moteur: MoteurFacial | None = None
_verrou = threading.Lock()


def moteur() -> MoteurFacial:
    global _moteur
    with _verrou:
        if _moteur is None:
            _moteur = MoteurFacial()
        return _moteur


class ErreurEnrolement(ValueError):
    pass


def _qualite(image: np.ndarray, visage: Visage) -> dict:
    x, y, w, h = visage.boite
    zone = cv2.cvtColor(image[max(0, y):y + h, max(0, x):x + w], cv2.COLOR_BGR2GRAY)
    if zone.size == 0:
        return {"luminosite": 0.0, "nettete": 0.0}
    zone = cv2.resize(zone, (160, 160))
    return {"luminosite": float(zone.mean()), "nettete": float(cv2.Laplacian(zone, cv2.CV_64F).var())}


def analyser(image_b64: str, db: Session | None = None, agent_id: int | None = None, reference: str | None = None) -> dict:
    """Retour en direct pour l'écran d'enrôlement : qualité de la capture et orientation de la tête.

    Avec un agent : signale aussitôt un visage déjà enrôlé pour un autre agent et, si la photo de face
    déjà prise est fournie (reference), vérifie qu'il s'agit bien de la même personne."""
    image = decoder_image(image_b64)
    m = moteur()
    with _verrou:
        visages = [v for v in m.detecter(image) if v.score >= 0.6]
    resultat = {"nb_visages": len(visages), "luminosite": None, "nettete": None, "lacet": None, "tangage": None,
                "taille_ok": False, "boite": None, "score": None, "trop_tourne": False, "largeur_image": image.shape[1], "hauteur_image": image.shape[0]}
    if len(visages) != 1:
        return resultat
    v = visages[0]
    q = _qualite(image, v)
    lum, net = q["luminosite"], q["nettete"]
    resultat.update(
        luminosite="CORRECTE" if 70 <= lum <= 200 else ("SOMBRE" if lum < 70 else "SUREXPOSEE"),
        nettete="BONNE" if net >= 60 else ("CORRECTE" if net >= 25 else "FLOUE"),
        lacet=round(rapport_lacet(v), 3), tangage=round(rapport_tangage(v), 3), score=round(v.score, 3),
        trop_tourne=abs(rapport_lacet(v) - 0.5) > ECART_MAX_PROFIL, taille_ok=v.largeur >= 80, boite=list(v.boite))
    if db is not None and agent_id is not None:
        resultat.update(meme_personne=None, deja_enrole=None)
        with _verrou:
            vecteur = m.gabarit(image, v)
        propre = None
        if reference:
            try:
                image_ref = decoder_image(reference)
                with _verrou:
                    vecteur_ref = m.gabarit_enrolement(image_ref)
                propre = similarite(vecteur, vecteur_ref)
                resultat["meme_personne"] = propre >= SEUIL_COHERENCE
            except (ErreurVisage, ValueError, cv2.error):
                pass
        trouve = _autre_titulaire(_gabarits_des_autres(db, agent_id), vecteur, propre)
        if trouve:
            autre, certain = trouve
            resultat["deja_enrole"] = {"matricule": autre.matricule, "nom_complet": autre.nom_complet, "certain": certain}
    return resultat


def extraire_gabarits(images: list[tuple[str, str]]) -> tuple[list[tuple[str, np.ndarray, Visage]], list[str]]:
    """images : [(pose, base64)] -> [(pose, vecteur, visage)], rejets"""
    resultats, rejets = [], []
    m = moteur()
    for pose, image_b64 in images:
        try:
            image = decoder_image(image_b64)
            with _verrou:
                vecteur = m.gabarit_enrolement(image)
                visage = m.visage_principal(image)
            ecart = abs(rapport_lacet(visage) - 0.5)
            if pose == "face" and ecart > ECART_MAX_FACE:
                raise ErreurVisage("l'agent ne regarde pas droit vers l'objectif")
            if pose != "face" and ecart > ECART_MAX_PROFIL:
                raise ErreurVisage("tête trop tournée (profil) : il suffit d'un quart de tour")
            resultats.append((pose, vecteur, visage))
        except (ErreurVisage, ValueError, cv2.error) as e:
            rejets.append(f"pose « {pose} » : {e if not isinstance(e, cv2.error) else 'image inexploitable'}")
    return resultats, rejets


def controle_vivacite(captures: list[tuple[str, np.ndarray, Visage]]) -> bool:
    lacets = {pose: rapport_lacet(v) for pose, _, v in captures}
    if "gauche" not in lacets or "droite" not in lacets:
        return False
    return abs(lacets["gauche"] - lacets["droite"]) >= ECART_VIVACITE_ENROLEMENT


def enroler(db: Session, agent: Agent, captures: list[tuple[str, np.ndarray, Visage]], minimum: int) -> bool:
    if len(captures) < minimum:
        raise ErreurEnrolement(f"{len(captures)} pose(s) exploitable(s), {minimum} requises")
    vivant = controle_vivacite(captures)
    enregistrer_gabarits(db, agent, [(pose, v) for pose, v, _ in captures], vivant)
    return vivant


def verifier_gabarits(db: Session, agent_id: int, vecteurs_poses: list[tuple[str, np.ndarray]], vivant: bool) -> None:
    """Contrôles d'un enrôlement : vivacité, photo de face, cohérence des poses, unicité du visage."""
    if VIVACITE_OBLIGATOIRE and not vivant:
        raise ErreurEnrolement("test de vivacité non concluant : les poses gauche et droite doivent montrer "
                               "une vraie rotation de la tête (photo ou écran suspecté)")
    poses = dict(vecteurs_poses)
    face = poses.get("face")
    if face is None:
        raise ErreurEnrolement("la photo de face est obligatoire (visage non détecté ou mal orienté sur cette photo)")

    autres = _gabarits_des_autres(db, agent_id)
    for pose, v in vecteurs_poses:
        # Cohérence : chaque pose doit montrer la même personne que la photo de face.
        propre = None if pose == "face" else similarite(v, face)
        if propre is not None and propre < SEUIL_COHERENCE:
            raise ErreurEnrolement(f"la photo « {pose} » ne semble pas montrer la même personne que la photo de face")
        # Unicité : CHAQUE pose (pas seulement la face) est comparée aux autres agents enrôlés ; sinon une
        # personne déjà enrôlée pourrait prêter ses poses de côté à l'enrôlement d'un autre agent.
        trouve = _autre_titulaire(autres, v, propre)
        if trouve:
            autre, certain = trouve
            precision = "" if pose == "face" else f" (photo « {pose} »)"
            if certain:
                raise ErreurEnrolement(f"ce visage est déjà enrôlé pour l'agent {autre.matricule} ({autre.nom_complet}){precision}")
            raise ErreurEnrolement(f"la photo « {pose} » ressemble davantage à l'agent {autre.matricule} ({autre.nom_complet}) "
                                   "qu'à la photo de face : la même personne doit poser du début à la fin")
    # Anciens enrôlements sans photo de face : ressemblance moyenne de toutes les poses.
    for autre, gabarits in autres:
        if "face" not in gabarits:
            moyenne = float(np.mean([max(similarite(v, g) for g in gabarits.values()) for v in poses.values()]))
            if moyenne >= SEUIL_SIMILARITE + 0.05:
                raise ErreurEnrolement(f"ce visage est déjà enrôlé pour l'agent {autre.matricule} ({autre.nom_complet})")


def _gabarits_des_autres(db: Session, agent_id: int | None) -> list[tuple[Agent, dict[str, np.ndarray]]]:
    """Gabarits déchiffrés de tous les agents enrôlés, sauf celui en cours d'enrôlement, regroupés par pose."""
    autres: dict[int, tuple[Agent, dict[str, np.ndarray]]] = {}
    requete = db.query(GabaritFacial).options(joinedload(GabaritFacial.agent))
    if agent_id is not None:
        requete = requete.filter(GabaritFacial.agent_id != agent_id)
    for g in requete:
        autres.setdefault(g.agent_id, (g.agent, {}))[1][g.pose or f"g{g.id}"] = dechiffrer_gabarit(g.donnees_chiffrees)
    return list(autres.values())


def _autre_titulaire(autres: list[tuple[Agent, dict[str, np.ndarray]]], vecteur: np.ndarray,
                     ressemblance_propre: float | None = None) -> tuple[Agent, bool] | None:
    """Autre agent dont la photo de face correspond à ce visage : (agent, certain).

    certain : ressemblance au-dessus du seuil d'identification (visage déjà enrôlé). Sinon, la pose ressemble
    plus à cet agent qu'à la photo de face de l'enrôlement en cours (personne probablement différente)."""
    meilleur: tuple[Agent, float] | None = None
    for autre, gabarits in autres:
        face = gabarits.get("face")
        if face is not None and (meilleur is None or similarite(vecteur, face) > meilleur[1]):
            meilleur = (autre, similarite(vecteur, face))
    if meilleur is None:
        return None
    autre, score = meilleur
    if score >= SEUIL_SIMILARITE:
        return autre, True
    if ressemblance_propre is not None and score >= SEUIL_COHERENCE and score > ressemblance_propre:
        return autre, False
    return None


def enregistrer_gabarits(db: Session, agent: Agent, vecteurs_poses: list[tuple[str, np.ndarray]], vivant: bool) -> None:
    """Contrôles puis enregistrement chiffré des gabarits (remplace les précédents)."""
    verifier_gabarits(db, agent.id, vecteurs_poses, vivant)
    face = dict(vecteurs_poses)["face"]
    agent.gabarits.clear()
    for pose, v in vecteurs_poses:
        agent.gabarits.append(GabaritFacial(pose=pose, donnees_chiffrees=chiffrer_gabarit(v), qualite=similarite(v, face)))


def identifier(db: Session, vecteur: np.ndarray) -> tuple[Agent | None, float]:
    """Identification 1:N côté serveur (pointage de secours depuis l'application mobile)."""
    _, entrees = galerie(db)
    matricule, score = Galerie(entrees).identifier(vecteur)
    if matricule is None:
        return None, score
    return db.query(Agent).filter_by(matricule=matricule).first(), score


def galerie(db: Session) -> tuple[str, list[dict]]:
    """Galerie des agents actifs enrôlés + empreinte de version (évite les retéléchargements)."""
    agents = (db.query(Agent).options(joinedload(Agent.gabarits), joinedload(Agent.sites_autorises),
                                      joinedload(Agent.site_rattachement))
              .filter(Agent.actif.is_(True)).order_by(Agent.matricule).all())
    entrees, signature = [], hashlib.sha256()
    for a in agents:
        if not a.gabarits:
            continue
        sites = sorted(s.id for s in a.sites_autorises)
        signature.update(f"{a.matricule}|{a.modifie_le}|{[g.id for g in a.gabarits]}|{a.tous_sites}|{sites}".encode())
        entrees.append({
            "matricule": a.matricule, "nom": a.nom, "prenom": a.prenom,
            "site_rattachement_id": a.site_rattachement_id, "site_rattachement": a.site_rattachement.nom,
            "tous_sites": a.tous_sites, "sites_autorises": sites,
            "gabarits": [vecteur_vers_b64(dechiffrer_gabarit(g.donnees_chiffrees)) for g in a.gabarits],
        })
    return signature.hexdigest()[:16], entrees
