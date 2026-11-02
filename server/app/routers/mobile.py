"""API de l'application mobile terrain (iPhone) : enrôlement à valider et pointage de secours.

Chaque requête porte deux preuves : la clé de l'appareil enregistré (X-Terminal-Key, type MOBILE)
et le jeton de l'utilisateur connecté (Authorization: Bearer). Les envois sont idempotents (uuid
créé par le téléphone) : la file hors ligne peut les rejouer sans créer de doublon.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from common.moteur_facial import ErreurVisage, decoder_image, vecteur_vers_b64
from server.app import config
from server.app.database import get_db
from server.app.models import (Agent, DemandeEnrolement, Pointage, StatutDemande, TentativeRejetee, Terminal,
                               TypeAppareil, TypePointage, Utilisateur, maintenant)
from server.app.routers import auth
from server.app.routers.organisation import organisation
from server.app.schemas import Connexion, ImagePose
from server.app.securite import (a_le_droit, auditer, chiffrer_texte, perimetre, terminal_courant, utilisateur_courant)
from server.app.services import biometrie
from server.app.services.vues import confiance

router = APIRouter(prefix="/api/mobile", tags=["Application mobile"])
ANTI_REBOND = timedelta(seconds=60)
MOTIFS = {"VISAGE_INCONNU": "Visage non reconnu", "SITE_NON_AUTORISE": "Agent non autorisé sur ce site",
          "AUCUN_VISAGE": "Aucun visage exploitable sur la photo"}


def appareil_mobile(terminal: Terminal = Depends(terminal_courant)) -> Terminal:
    if terminal.type != TypeAppareil.MOBILE:
        raise HTTPException(403, "Cet appareil n'est pas enregistré comme téléphone de l'application terrain")
    return terminal


def _naive(d: datetime) -> datetime:
    return d.astimezone().replace(tzinfo=None, microsecond=0) if d.tzinfo else d.replace(microsecond=0)


def _appareil(t: Terminal) -> dict:
    return {"code": t.code, "site_id": t.site_id, "site": t.site.libelle_court, "libelle": t.libelle}


# --- Connexion -----------------------------------------------------------------------------
@router.post("/connexion")
def connexion(donnees: Connexion, request: Request, appareil: Terminal = Depends(appareil_mobile),
              db: Session = Depends(get_db)):
    """Connexion d'un utilisateur, uniquement depuis un téléphone enregistré."""
    reponse = auth.connexion(donnees, request, db)
    return {**reponse.model_dump(), "appareil": _appareil(appareil)}


@router.get("/accueil")
def accueil(appareil: Terminal = Depends(appareil_mobile), u: Utilisateur = Depends(utilisateur_courant),
            db: Session = Depends(get_db)):
    """Écran d'accueil : utilisateur, appareil, droits et activité récente de l'appareil."""
    demandes = (db.query(DemandeEnrolement).options(joinedload(DemandeEnrolement.agent))
                .filter(DemandeEnrolement.appareil_id == appareil.id)
                .order_by(DemandeEnrolement.cree_le.desc()).limit(10).all())
    secours = (db.query(Pointage).options(joinedload(Pointage.agent))
               .filter(Pointage.terminal_id == appareil.id).order_by(Pointage.horodatage.desc()).limit(10).all())
    activite = [{"uuid": d.uuid, "nature": "ENROLEMENT", "titre": f"Enrôlement · {d.agent.nom_complet}",
                 "date": d.cree_le, "statut": d.statut.value, "motif": d.motif} for d in demandes]
    activite += [{"uuid": p.uuid, "nature": "SECOURS", "titre": f"Secours · {p.agent.nom_complet}",
                  "date": p.horodatage, "type": p.type.value, "statut": "ANNULE" if p.annule else "SYNCHRONISE"}
                 for p in secours]
    activite.sort(key=lambda x: x["date"], reverse=True)
    org = organisation(db)
    return {"appareil": _appareil(appareil), "utilisateur": auth._session(u).model_dump(),
            "organisation": {"nom": org.nom, "sigle": org.sigle, "couleur_primaire": org.couleur_primaire,
                             "couleur_menu": org.couleur_menu, "prefixe_matricule": org.prefixe_matricule},
            "activite": activite[:10]}


# --- Enrôlement proposé depuis le terrain -------------------------------------------------------
class EnvoiEnrolement(BaseModel):
    uuid: str = Field(min_length=8, max_length=36)
    agent_id: int
    consentement: bool
    capture_le: datetime
    images: list[ImagePose] = Field(min_length=1, max_length=10)


def _suivi(d: DemandeEnrolement) -> dict:
    return {"uuid": d.uuid, "statut": d.statut.value, "motif": d.motif, "agent": d.agent.nom_complet,
            "matricule": d.agent.matricule, "nb_photos": d.nb_photos, "recu_le": d.cree_le, "traite_le": d.traite_le}


@router.post("/enrolements", status_code=202)
def envoyer_enrolement(donnees: EnvoiEnrolement, request: Request, appareil: Terminal = Depends(appareil_mobile),
                       u: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    existante = db.query(DemandeEnrolement).filter_by(uuid=donnees.uuid).first()
    if existante:  # renvoi depuis la file d'envoi : aucun doublon
        return _suivi(existante)
    if not a_le_droit(u, "biometrie.proposer"):
        raise HTTPException(403, "Votre profil ne permet pas de proposer un enrôlement")
    agent = perimetre(db.query(Agent), u).filter(Agent.id == donnees.agent_id).first()
    if agent is None:
        raise HTTPException(404, "Agent introuvable ou hors de votre périmètre")
    if not agent.actif:
        raise HTTPException(400, "Agent désactivé")
    if not donnees.consentement:
        raise HTTPException(400, "Le consentement de l'agent est requis")

    captures, rejets = biometrie.extraire_gabarits([(i.pose, i.image) for i in donnees.images])
    d = DemandeEnrolement(uuid=donnees.uuid, agent_id=agent.id, appareil_id=appareil.id, auteur_id=u.id,
                          capture_le=_naive(donnees.capture_le), nb_photos=len(donnees.images),
                          vivacite=biometrie.controle_vivacite(captures), controles="\n".join(rejets),
                          photos_chiffrees=chiffrer_texte(json.dumps(
                              {i.pose: i.image for i in donnees.images})).encode())
    if len(captures) < config.MIN_IMAGES_ENROLEMENT:
        d.statut, d.motif = StatutDemande.REJETEE, (
            f"{len(captures)} photo(s) exploitable(s) sur {len(donnees.images)} : " + "; ".join(rejets))[:300]
        d.photos_chiffrees = None
    else:
        # Contrôles complets dès la réception : l'opérateur sait tout de suite s'il faut refaire les photos.
        try:
            biometrie.verifier_gabarits(db, agent.id, [(pose, v) for pose, v, _ in captures], d.vivacite)
        except biometrie.ErreurEnrolement as e:
            d.statut, d.motif, d.photos_chiffrees = StatutDemande.REJETEE, f"À refaire : {e}"[:300], None
            db.add(d)
            auditer(db, u.identifiant, "ENROLEMENT_PROPOSE", f"{agent.matricule} depuis {appareil.code} : rejeté ({e})", request)
            db.commit()
            return _suivi(d)
        d.statut = StatutDemande.GABARIT_CALCULE
        d.gabarits_chiffres = chiffrer_texte(json.dumps(
            [[pose, vecteur_vers_b64(v)] for pose, v, _ in captures])).encode()
    db.add(d)
    auditer(db, u.identifiant, "ENROLEMENT_PROPOSE", f"{agent.matricule} depuis {appareil.code} : {d.statut.value}",
            request)
    db.commit()
    return _suivi(d)


@router.get("/enrolements/{uuid}")
def suivre_enrolement(uuid: str, appareil: Terminal = Depends(appareil_mobile),
                      _: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    d = db.query(DemandeEnrolement).filter_by(uuid=uuid, appareil_id=appareil.id).first()
    if d is None:
        raise HTTPException(404, "Demande inconnue")
    return _suivi(d)


# --- Pointage de secours ------------------------------------------------------------------------
class PointageSecours(BaseModel):
    uuid: str = Field(min_length=8, max_length=36)
    horodatage: datetime
    type: TypePointage | None = None   # None : déduit du dernier pointage du jour
    image: str
    hors_ligne: bool = False


def _resultat_pointage(p: Pointage, appareil: Terminal) -> dict:
    a = p.agent
    return {"uuid": p.uuid, "resultat": "ENREGISTRE", "type": p.type.value, "horodatage": p.horodatage,
            "agent": {"prenom": a.prenom, "nom": a.nom, "nom_complet": a.nom_complet, "matricule": a.matricule},
            "site": p.site.libelle_court, "rattachement": a.site_rattachement.libelle_court,
            "hors_rattachement": p.site_id != a.site_rattachement_id, "appareil": appareil.code,
            "confiance": confiance(p.score), "annule": p.annule}


@router.post("/secours")
def pointage_secours(donnees: PointageSecours, request: Request, appareil: Terminal = Depends(appareil_mobile),
                     u: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    """Pointage photographié par un responsable quand la borne du site est en panne.

    La reconnaissance est faite par le serveur (même modèle et même galerie que les bornes)."""
    deja = db.query(Pointage).filter_by(uuid=donnees.uuid).first()
    if deja:
        return _resultat_pointage(deja, appareil)
    refus = db.query(TentativeRejetee).filter_by(uuid=donnees.uuid).first()
    if refus:
        return {"uuid": refus.uuid, "resultat": "REFUSE", "motif": refus.motif, "message": MOTIFS.get(refus.motif, "")}
    if not a_le_droit(u, "pointages.secours"):
        raise HTTPException(403, "Votre profil ne permet pas le pointage de secours")
    horodatage = _naive(donnees.horodatage)
    if horodatage > maintenant() + timedelta(minutes=10):
        raise HTTPException(400, "Heure du téléphone incorrecte (dans le futur)")

    def refuser(motif: str, matricule: str | None = None, score: float = 0.0) -> dict:
        db.add(TentativeRejetee(uuid=donnees.uuid, horodatage=horodatage, motif=motif, matricule_suppose=matricule,
                                score=score, terminal_id=appareil.id, site_id=appareil.site_id,
                                hors_ligne=donnees.hors_ligne))
        db.commit()
        return {"uuid": donnees.uuid, "resultat": "REFUSE", "motif": motif, "message": MOTIFS[motif]}

    m = biometrie.moteur()
    try:
        image = decoder_image(donnees.image)
        with biometrie._verrou:
            visage = m.visage_principal(image)
            vecteur = m.gabarit(image, visage) if visage is not None and visage.largeur >= 60 else None
    except (ErreurVisage, ValueError):
        vecteur = None
    if vecteur is None:
        # Photo inexploitable (flou, cadrage) : rien n'est enregistré, l'opérateur reprend la photo.
        return {"uuid": donnees.uuid, "resultat": "REPRENDRE", "message": MOTIFS["AUCUN_VISAGE"]}
    agent, score = biometrie.identifier(db, vecteur)
    if agent is None:
        return refuser("VISAGE_INCONNU", None, score)
    agent = db.query(Agent).options(joinedload(Agent.sites_autorises)).filter_by(id=agent.id).one()
    if not agent.peut_pointer_sur(appareil.site_id):
        return refuser("SITE_NON_AUTORISE", agent.matricule, score)

    recent = (db.query(Pointage).filter(Pointage.agent_id == agent.id, Pointage.annule.is_(False),
                                        Pointage.horodatage > horodatage - ANTI_REBOND,
                                        Pointage.horodatage <= horodatage + ANTI_REBOND).first())
    if recent:
        return {**_resultat_pointage(recent, appareil), "resultat": "DEJA_POINTE"}
    type_ = donnees.type
    if type_ is None:
        dernier = (db.query(Pointage).filter(Pointage.agent_id == agent.id, Pointage.annule.is_(False),
                                             Pointage.horodatage >= datetime.combine(horodatage.date(), datetime.min.time()),
                                             Pointage.horodatage < horodatage)
                   .order_by(Pointage.horodatage.desc()).first())
        type_ = TypePointage.SORTIE if dernier and dernier.type == TypePointage.ENTREE else TypePointage.ENTREE
    p = Pointage(uuid=donnees.uuid, agent_id=agent.id, matricule=agent.matricule, horodatage=horodatage, type=type_,
                 site_id=appareil.site_id, terminal_id=appareil.id, score=score, hors_ligne=donnees.hors_ligne,
                 secours=True)
    db.add(p)
    auditer(db, u.identifiant, "POINTAGE_SECOURS", f"{agent.matricule} {type_.value} sur {appareil.code}", request)
    db.commit()
    db.refresh(p)
    return _resultat_pointage(p, appareil)


@router.post("/secours/{uuid}/annuler")
def annuler_secours(uuid: str, request: Request, appareil: Terminal = Depends(appareil_mobile),
                    u: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    """« Ce n'est pas moi » sur l'écran de résultat."""
    p = db.query(Pointage).filter_by(uuid=uuid, terminal_id=appareil.id).first()
    if p is None:
        raise HTTPException(404, "Pointage inconnu")
    p.annule = True
    db.add(TentativeRejetee(uuid=f"annul-{uuid}"[:36], horodatage=maintenant(), motif="IDENTITE_CONTESTEE",
                            matricule_suppose=p.matricule, score=p.score, terminal_id=appareil.id,
                            site_id=appareil.site_id))
    auditer(db, u.identifiant, "POINTAGE_SECOURS_ANNULE", f"{p.matricule} sur {appareil.code}", request)
    db.commit()
    return _resultat_pointage(p, appareil)
