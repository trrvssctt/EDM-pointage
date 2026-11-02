"""Validation, dans l'application web, des enrôlements proposés depuis l'application mobile."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from common.moteur_facial import b64_vers_vecteur
from server.app.database import get_db
from server.app.models import Agent, DemandeEnrolement, StatutDemande, Utilisateur, maintenant
from server.app.securite import auditer, dechiffrer_texte, exiger_droit, perimetre
from server.app.services import biometrie

router = APIRouter(prefix="/api/enrolements/demandes", tags=["Agents et enrôlement"])
validation = exiger_droit("biometrie.enroler")


def _demande(db: Session, uuid: str, u: Utilisateur) -> DemandeEnrolement:
    d = (db.query(DemandeEnrolement).options(joinedload(DemandeEnrolement.agent), joinedload(DemandeEnrolement.appareil),
                                             joinedload(DemandeEnrolement.auteur))
         .filter(DemandeEnrolement.uuid == uuid).first())
    if d is None or not perimetre(db.query(Agent), u).filter(Agent.id == d.agent_id).first():
        raise HTTPException(404, "Demande introuvable")
    return d


def _resume(d: DemandeEnrolement) -> dict:
    return {"uuid": d.uuid, "statut": d.statut.value, "motif": d.motif, "agent_id": d.agent_id,
            "agent": d.agent.nom_complet, "matricule": d.agent.matricule, "service": d.agent.service.nom,
            "site_rattachement": d.agent.site_rattachement.libelle_court, "appareil": d.appareil.code,
            "auteur": d.auteur.nom_complet or d.auteur.identifiant, "nb_photos": d.nb_photos, "vivacite": d.vivacite,
            "controles": d.controles, "capture_le": d.capture_le, "recu_le": d.cree_le, "traite_par": d.traite_par,
            "traite_le": d.traite_le}


@router.get("")
def lister(statut: StatutDemande | None = None, u: Utilisateur = Depends(validation), db: Session = Depends(get_db)):
    requete = db.query(DemandeEnrolement).options(joinedload(DemandeEnrolement.agent).joinedload(Agent.service),
                                                  joinedload(DemandeEnrolement.agent).joinedload(Agent.site_rattachement),
                                                  joinedload(DemandeEnrolement.appareil),
                                                  joinedload(DemandeEnrolement.auteur))
    if statut:
        requete = requete.filter(DemandeEnrolement.statut == statut)
    ids = {i for (i,) in perimetre(db.query(Agent.id), u)}
    return [_resume(d) for d in requete.order_by(DemandeEnrolement.cree_le.desc()).limit(200) if d.agent_id in ids]


@router.get("/{uuid}")
def consulter(uuid: str, u: Utilisateur = Depends(validation), db: Session = Depends(get_db)):
    """Détail avec les photos (déchiffrées pour l'affichage, jamais stockées en clair)."""
    d = _demande(db, uuid, u)
    photos = json.loads(dechiffrer_texte(d.photos_chiffrees.decode())) if d.photos_chiffrees else {}
    return {**_resume(d), "photos": photos}


@router.post("/{uuid}/valider")
def valider(uuid: str, request: Request, u: Utilisateur = Depends(validation), db: Session = Depends(get_db)):
    d = _demande(db, uuid, u)
    if d.statut != StatutDemande.GABARIT_CALCULE:
        raise HTTPException(409, "Cette demande a déjà été traitée")
    vecteurs = [(pose, b64_vers_vecteur(v)) for pose, v in json.loads(dechiffrer_texte(d.gabarits_chiffres.decode()))]
    try:
        biometrie.enregistrer_gabarits(db, d.agent, vecteurs, d.vivacite)
    except biometrie.ErreurEnrolement as e:
        db.rollback()
        raise HTTPException(422, f"Validation impossible : {e}. Rejetez la demande et refaites les photos.")
    d.agent.consentement_le = d.capture_le
    d.agent.modifie_le = maintenant()
    d.statut, d.traite_par, d.traite_le = StatutDemande.VALIDEE, u.identifiant, maintenant()
    d.photos_chiffrees = d.gabarits_chiffres = None  # les photos ne sont jamais conservées après décision
    auditer(db, u.identifiant, "ENROLEMENT_VALIDE", f"{d.agent.matricule} (proposé depuis {d.appareil.code})", request)
    db.commit()
    return _resume(d)


@router.post("/{uuid}/rejeter")
def rejeter(uuid: str, corps: dict, request: Request, u: Utilisateur = Depends(validation), db: Session = Depends(get_db)):
    d = _demande(db, uuid, u)
    if d.statut != StatutDemande.GABARIT_CALCULE:
        raise HTTPException(409, "Cette demande a déjà été traitée")
    d.statut, d.motif = StatutDemande.REJETEE, str(corps.get("motif") or "Photos non conformes")[:300]
    d.traite_par, d.traite_le = u.identifiant, maintenant()
    d.photos_chiffrees = d.gabarits_chiffres = None
    auditer(db, u.identifiant, "ENROLEMENT_REJETE", f"{d.agent.matricule} : {d.motif}", request)
    db.commit()
    return _resume(d)
