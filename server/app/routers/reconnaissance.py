"""Poste de pointage simulé : identification en direct de toutes les personnes filmées par la webcam d'un poste.

Démonstration et contrôle de la galerie : aucun pointage n'est enregistré (pas de défi de vivacité possible
avec plusieurs personnes à la fois). Les images ne sont ni conservées ni journalisées.
"""
from __future__ import annotations

import threading
import time

import cv2
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from common.moteur_facial import SEUIL_SIMILARITE, ErreurVisage, Galerie, decoder_image
from server.app.database import get_db
from server.app.models import Agent, GabaritFacial, Utilisateur
from server.app.securite import auditer, exiger_droit
from server.app.services import biometrie
from server.app.services.vues import confiance

router = APIRouter(prefix="/api/reconnaissance", tags=["Reconnaissance en direct"])
# Écart minimal entre les deux agents les plus ressemblants : en dessous, l'identité est jugée ambiguë.
MARGE_AMBIGUITE = 0.06
LARGEUR_MIN = 60   # pixels : visage trop éloigné en dessous
MAX_VISAGES = 10

_cache: dict = {"cle": None, "galerie": Galerie(), "agents": {}}
_verrou_cache = threading.Lock()


class ImageDirect(BaseModel):
    image: str
    debut: bool = False  # première image d'une session : tracée dans le journal d'audit


def _galerie(db: Session) -> tuple[Galerie, dict[str, dict]]:
    """Galerie des agents actifs, reconstruite seulement quand les gabarits ou les agents changent."""
    cle = (db.query(func.count(GabaritFacial.id), func.max(GabaritFacial.id)).one(),
           db.query(func.count(Agent.id), func.max(Agent.modifie_le)).filter(Agent.actif.is_(True)).one())
    with _verrou_cache:
        if _cache["cle"] != cle:
            _, entrees = biometrie.galerie(db)
            fiches = {a.matricule: a for a in db.query(Agent).options(joinedload(Agent.service), joinedload(Agent.site_rattachement))
                      .filter(Agent.matricule.in_([e["matricule"] for e in entrees]))}
            _cache.update(cle=cle, galerie=Galerie(entrees), agents={
                m: {"matricule": m, "nom_complet": a.nom_complet, "service": a.service.nom,
                    "site_rattachement": a.site_rattachement.libelle_court} for m, a in fiches.items()})
        return _cache["galerie"], _cache["agents"]


@router.post("/identifier")
def identifier(donnees: ImageDirect, request: Request, u: Utilisateur = Depends(exiger_droit("biometrie.enroler")),
               db: Session = Depends(get_db)):
    """Identifie chaque visage d'une image de la webcam : RECONNU, AMBIGU, INCONNU ou TROP_LOIN, avec sa position."""
    debut = time.perf_counter()
    try:
        image = decoder_image(donnees.image)
    except (ErreurVisage, ValueError, cv2.error):
        raise HTTPException(400, "Image illisible")
    if donnees.debut:
        auditer(db, u.identifiant, "RECONNAISSANCE_DIRECT", "ouverture du poste de pointage simulé", request)
        db.commit()
    galerie, agents = _galerie(db)
    m = biometrie.moteur()
    visages = []
    with biometrie._verrou:
        detectes = sorted((v for v in m.detecter(image) if v.score >= 0.7), key=lambda v: v.largeur, reverse=True)
        for v in detectes[:MAX_VISAGES]:
            x, y, w, h = v.boite
            entree = {"boite": [x, y, w, h], "statut": "TROP_LOIN", "agent": None, "score": None, "confiance": None,
                      "autre": None}
            if v.largeur >= LARGEUR_MIN:
                classement = galerie.classement(m.gabarit(image, v))
                meilleur = classement[0] if classement else (None, 0.0)
                second = classement[1] if len(classement) > 1 else (None, -1.0)
                entree["score"] = round(meilleur[1], 3)
                if meilleur[0] is None or meilleur[1] < SEUIL_SIMILARITE:
                    entree["statut"] = "INCONNU"
                else:
                    entree.update(agent=agents.get(meilleur[0]), confiance=confiance(meilleur[1]))
                    ambigu = second[0] is not None and meilleur[1] - second[1] < MARGE_AMBIGUITE
                    entree["statut"] = "AMBIGU" if ambigu else "RECONNU"
                    if ambigu:
                        entree["autre"] = {**(agents.get(second[0]) or {"matricule": second[0]}), "score": round(second[1], 3)}
            visages.append(entree)
    return {"visages": visages, "largeur": image.shape[1], "hauteur": image.shape[0], "agents_enroles": len(galerie),
            "seuil": SEUIL_SIMILARITE, "duree_ms": round((time.perf_counter() - debut) * 1000)}
