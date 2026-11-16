"""Poste de pointage simulé : identification en direct de toutes les personnes filmées par la webcam d'un poste.

Démonstration et contrôle de la galerie : aucun pointage n'est enregistré. Les images ne sont ni conservées ni
journalisées.

Vivacité : être reconnu ne suffit pas. Une photo ou un écran montrant un agent est reconnu comme l'agent.

1. Vivacité passive : le navigateur analyse la vidéo à ~30 images/s avec MediaPipe Face Landmarker
   (frontend/src/admin/vivacitePassive.ts) et compte les clignements naturels (toutes les 3 à 5 s, sans y
   penser) ; une photo ne cligne pas. Un clignement survenu après la première reconnaissance de la personne,
   seule dans le champ, prouve sa vivacité, sans consigne. Ce compteur vient du navigateur : il est fiable
   ici (poste d'un administrateur connecté), pas face à un utilisateur qui maîtrise son navigateur.
2. Secours : sans clignement au bout de 5 s (ou si le navigateur ne peut pas charger MediaPipe), défi de
   rotation de la tête dans un sens tiré au hasard, suivi d'un retour face à la caméra (common.vivacite). Le défi est lancé quand une seule personne reconnue est dans le champ ; il suit
ensuite ce visage même s'il n'est plus reconnu une fois tourné (SFace est moins fiable de profil), et l'identité
est revérifiée de face à la fin. La vivacité prouvée reste acquise tant que la personne reste visible. Les modèles « image seule » gratuits (MiniFASNet, détection de téléphone) ont été essayés : ils
laissent passer une photo affichée sur un téléphone, d'où ce défi.

Sont signalés comme tentative de fraude (ECHEC_VIVACITE) un visage resté parfaitement rigide pendant tout le
défi (photo ou écran) et comme usurpation d'identité (CHANGEMENT_VISAGE) un visage différent à la fin du défi, avec l'agent dont l'identité était présentée,
dans l'historique des pointages et le tableau de bord, comme pour une borne. L'appareil est le terminal virtuel
POSTE-WEB.
"""
from __future__ import annotations

import random
import secrets
import threading
import time
import uuid

import cv2
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from common.moteur_facial import SEUIL_SIMILARITE, ErreurVisage, Galerie, decoder_image
from common.vivacite import DROITE, GAUCHE, DefiVivacite
from server.app.database import get_db
from server.app.models import (Agent, GabaritFacial, Site, Terminal, TentativeRejetee, TypeAppareil, Utilisateur,
                               maintenant as horodatage)
from server.app.securite import auditer, empreinte_cle, exiger_droit
from server.app.services import biometrie
from server.app.services.vues import confiance

router = APIRouter(prefix="/api/reconnaissance", tags=["Reconnaissance en direct"])
# Écart minimal entre les deux agents les plus ressemblants : en dessous, l'identité est jugée ambiguë.
MARGE_AMBIGUITE = 0.06
LARGEUR_MIN = 60   # pixels : visage trop éloigné en dessous
MAX_VISAGES = 10

# Défi de vivacité adapté au navigateur (1 à 3 images par seconde) : 2 images tenues, 12 s maximum.
IMAGES_DEFI = 2
DUREE_DEFI = 12.0
DUREE_ECHEC = 4.0      # affichage d'un échec avant un nouveau défi
DUREE_PRESENCE = 3.0   # la vivacité prouvée est perdue après 3 s hors du champ ; le défi est abandonné de même
# En dessous de cette variation du lacet sur tout le défi, le visage est rigide : photo ou écran. Au-dessus,
# la personne a bougé sans réussir le défi (consigne mal comprise) : non prouvé, mais pas signalé.
AMPLITUDE_PHOTO = 0.06
OBSERVATION = 5.0      # secondes d'attente d'un clignement naturel avant le défi de rotation
ECART_DEFI = 0.10      # rotation demandée au navigateur : un léger quart de tour suffit
DUREE_SESSION = 120.0
DELAI_SIGNALEMENT = 60.0  # au plus un signalement par personne présentée et par minute
CODE_POSTE_WEB = "POSTE-WEB"

_cache: dict = {"cle": None, "galerie": Galerie(), "agents": {}}
_verrou_cache = threading.Lock()
_sessions: dict[tuple[int, str], dict] = {}
_verrou_sessions = threading.Lock()


class Passif(BaseModel):
    """Vivacité passive mesurée par le navigateur (MediaPipe) au moment de l'envoi de l'image."""
    clignements: int = Field(ge=0)  # clignements vus depuis l'ouverture, une seule personne dans le champ
    visages: int = Field(ge=0)      # visages vus par MediaPipe sur la dernière image


class ImageDirect(BaseModel):
    image: str
    debut: bool = False  # première image d'une session : tracée dans le journal d'audit
    session: str = ""    # identifiant tiré par le navigateur : suivi du défi de vivacité d'une image à l'autre
    passif: Passif | None = None  # absent si MediaPipe n'a pas pu être chargé : défi de rotation seul


def _session(utilisateur_id: int, cle: str) -> dict:
    maintenant = time.monotonic()
    with _verrou_sessions:
        for k in [k for k, v in _sessions.items() if maintenant - v["vu"] > DUREE_SESSION]:
            del _sessions[k]
        s = _sessions.setdefault((utilisateur_id, cle), {"vu": maintenant, "verifies": {}, "echecs": {}, "defi": None,
                                                          "signales": {}, "arrivees": {}})
        s["vu"] = maintenant
        return s


def _vivacite(s: dict, galerie: Galerie, agents: dict[str, dict], m, image, presents: list[tuple[dict, object]],
              reconnus: list[tuple[dict, object, str]], fraudes: list[tuple[str, str, float]],
              passif: Passif | None = None) -> dict | None:
    """Met à jour la vivacité de la session et renseigne entree["vivacite"] des visages concernés.

    VERIFIEE : clignement naturel, ou rotation et retour réussis, par la même personne ; OBSERVATION : seule dans
    le champ, en attente d'un clignement ; DEFI : consigne de rotation en cours ; ECHEC : visage rigide sans
    clignement (photo ou écran) ou visage changé, signalé dans fraudes (motif, matricule présenté, score) ;
    NON_PROUVEE : délai écoulé alors que la personne bougeait, non signalé ; NON_VERIFIEE : plusieurs personnes
    dans le champ."""
    maintenant = time.monotonic()
    s["verifies"] = {k: t for k, t in s["verifies"].items() if maintenant - t <= DUREE_PRESENCE}
    s["echecs"] = {k: v for k, v in s["echecs"].items() if v[0] > maintenant}
    # Arrivée de chaque personne reconnue : instant et compteur de clignements du navigateur à ce moment-là.
    s["arrivees"] = {k: v for k, v in s["arrivees"].items() if maintenant - v["vu"] <= DUREE_PRESENCE}
    seul = len(presents) == 1 and (passif is None or passif.visages <= 1)
    for entree, _, matricule in reconnus:
        arrivee = s["arrivees"].setdefault(matricule, {"t": maintenant, "clignements": passif.clignements if passif else 0})
        arrivee["vu"] = maintenant
        if passif is not None and passif.clignements < arrivee["clignements"]:
            arrivee["clignements"] = passif.clignements  # page rechargée : le compteur du navigateur repart de zéro
        if matricule in s["verifies"]:
            s["verifies"][matricule] = maintenant
            entree["vivacite"] = "VERIFIEE"
        elif matricule in s["echecs"]:
            entree["vivacite"] = s["echecs"][matricule][1]
        elif seul and passif is not None and passif.clignements > arrivee["clignements"]:
            # Clignement naturel depuis l'arrivée de cette personne, seule dans le champ : vivacité prouvée.
            s["verifies"][matricule] = maintenant
            entree["vivacite"] = "VERIFIEE"
            if s["defi"] and s["defi"]["matricule"] == matricule:
                s["defi"] = None
        else:
            entree["vivacite"] = "NON_VERIFIEE"

    defi = s["defi"]
    if defi is None:
        if not seul or len(reconnus) != 1 or reconnus[0][0]["vivacite"] != "NON_VERIFIEE":
            return None
        entree, visage, matricule = reconnus[0]
        if passif is not None and maintenant - s["arrivees"][matricule]["t"] < OBSERVATION:
            entree["vivacite"] = "OBSERVATION"
            return None
        s["defi"] = defi = {"matricule": matricule, "vu": maintenant, "defi": DefiVivacite(
            visage, direction=random.choice((DROITE, GAUCHE)), images_requises=IMAGES_DEFI, duree_max=DUREE_DEFI,
            retour_face=True, ecart_requis=ECART_DEFI)}
    if len(presents) > 1 or (not presents and maintenant - defi["vu"] > DUREE_PRESENCE):
        s["defi"] = None  # quelqu'un d'autre est entré dans le champ, ou la personne est partie : défi abandonné
        return None
    matricule, d = defi["matricule"], defi["defi"]
    entree = None
    if presents:
        entree, visage = presents[0]
        defi["vu"] = maintenant
        entree["vivacite"] = "DEFI"
        if entree["agent"] is None or entree["statut"] != "RECONNU":
            entree["agent"] = agents.get(matricule)  # visage tourné, moins bien reconnu : c'est toujours lui
            # Un clignement pendant le défi suffit aussi, même si le visage tourné n'est plus reconnu.
            arrivee = s["arrivees"].get(matricule)
            if arrivee and passif is not None and passif.visages <= 1 and passif.clignements > arrivee["clignements"]:
                s["defi"] = None
                s["verifies"][matricule] = maintenant
                entree["vivacite"] = "VERIFIEE"
                return None
        if d.mettre_a_jour(visage):
            s["defi"] = None
            # Revérification de l'identité sur le visage revenu de face (même seuil que la borne).
            score_final = galerie.score_agent(matricule, m.gabarit(image, visage))
            if score_final >= SEUIL_SIMILARITE * 0.85:
                s["verifies"][matricule] = maintenant
                entree["vivacite"] = "VERIFIEE"
                return None
            fraudes.append(("CHANGEMENT_VISAGE", matricule, score_final))
            s["echecs"][matricule] = (maintenant + DUREE_ECHEC, "ECHEC")
            entree["vivacite"] = "ECHEC"
            return None
    if d.expire:
        s["defi"] = None
        # Ni clignement (sinon la vivacité serait déjà prouvée) ni mouvement : photo ou écran.
        if d.amplitude < AMPLITUDE_PHOTO:
            fraudes.append(("ECHEC_VIVACITE", matricule, (entree or {}).get("score") or 0.0))
            etat = "ECHEC"
        else:
            etat = "NON_PROUVEE"
        s["echecs"][matricule] = (maintenant + DUREE_ECHEC, etat)
        s["arrivees"].pop(matricule, None)  # nouvel essai : nouvelle période d'observation
        if entree is not None:
            entree["vivacite"] = etat
        return None
    return {"matricule": matricule, "direction": d.direction, "consigne": d.consigne,
            "phase": "RETOUR" if d.tourne else "ROTATION", "sens_inverse": d.sens_inverse,
            "restant": max(0.0, round(d.duree_max - (maintenant - d.debut), 1))}


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


def _poste_web(db: Session) -> Terminal:
    """Terminal virtuel auquel sont rattachés les signalements du poste simulé (aucune clé utilisable)."""
    t = db.query(Terminal).filter_by(code=CODE_POSTE_WEB).first()
    if t is None:
        t = Terminal(code=CODE_POSTE_WEB, libelle="Poste de pointage simulé (navigateur)", type=TypeAppareil.WEB,
                     site_id=db.query(Site.id).order_by(Site.id).limit(1).scalar(), empreinte_cle=empreinte_cle(secrets.token_hex(32)))
        db.add(t)
        db.flush()
    return t


def _signaler(db: Session, s: dict, u: Utilisateur, request: Request, fraudes: list[tuple[str, str, float]]) -> bool:
    """Enregistre les tentatives de fraude ou d'usurpation d'identité (une par personne présentée et par minute)."""
    maintenant = time.monotonic()
    s["signales"] = {k: t for k, t in s["signales"].items() if maintenant - t < DELAI_SIGNALEMENT}
    a_enregistrer = [f for f in fraudes if f[1] not in s["signales"]]
    if not a_enregistrer:
        return bool(fraudes)
    poste = _poste_web(db)
    poste.dernier_contact = horodatage()
    for motif, matricule, score in a_enregistrer:
        agent = db.query(Agent).filter_by(matricule=matricule).first()
        db.add(TentativeRejetee(uuid=str(uuid.uuid4()), horodatage=horodatage(), motif=motif, matricule_suppose=matricule,
                                score=round(float(score), 3), terminal_id=poste.id,
                                site_id=agent.site_rattachement_id if agent else poste.site_id))
        nature = "usurpation d'identité (visage changé pendant le défi)" if motif == "CHANGEMENT_VISAGE" \
            else "fraude (photo, écran ou vidéo : défi de vivacité échoué)"
        auditer(db, u.identifiant, "FRAUDE_SUSPECTEE", f"{CODE_POSTE_WEB} : {nature}, identité présentée {matricule}", request)
        s["signales"][matricule] = maintenant
    db.commit()
    return True


@router.post("/identifier")
def identifier(donnees: ImageDirect, request: Request, u: Utilisateur = Depends(exiger_droit("biometrie.enroler")),
               db: Session = Depends(get_db)):
    """Identifie chaque visage d'une image de la webcam : RECONNU, AMBIGU, INCONNU ou TROP_LOIN, avec sa position.

    Chaque visage reconnu porte aussi son état de vivacité (VERIFIEE, OBSERVATION, DEFI, ECHEC, NON_PROUVEE,
    NON_VERIFIEE) ;
    « defi » donne la consigne en cours quand une seule personne est dans le champ."""
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
    visages, reconnus, presents = [], [], []
    with biometrie._verrou:
        detectes = sorted((v for v in m.detecter(image) if v.score >= 0.7), key=lambda v: v.largeur, reverse=True)
        for v in detectes[:MAX_VISAGES]:
            x, y, w, h = v.boite
            entree = {"boite": [x, y, w, h], "statut": "TROP_LOIN", "agent": None, "score": None, "confiance": None,
                      "autre": None, "vivacite": None}
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
                    else:
                        reconnus.append((entree, v, meilleur[0]))
            visages.append(entree)
            presents.append((entree, v))
        session = _session(u.id, donnees.session)
        fraudes: list[tuple[str, str, float]] = []
        defi = _vivacite(session, galerie, agents, m, image, presents, reconnus, fraudes, donnees.passif)
    signale = _signaler(db, session, u, request, fraudes) if fraudes else False
    return {"visages": visages, "defi": defi, "fraude_signalee": signale, "largeur": image.shape[1], "hauteur": image.shape[0],
            "agents_enroles": len(galerie), "seuil": SEUIL_SIMILARITE,
            "duree_ms": round((time.perf_counter() - debut) * 1000)}
