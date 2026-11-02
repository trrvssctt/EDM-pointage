"""Connexion, vérification en deux étapes, comptes utilisateurs, droits et journal d'audit."""
from datetime import timedelta

import pyotp
import segno
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from server.app.database import get_db
from server.app.models import JournalAudit, Organisation, Role, Utilisateur, maintenant
from server.app.schemas import (ChangementMotDePasse, CodeDeuxEtapes, Connexion, MotDePasseOublie, ReponseConnexion,
                                Session_, UtilisateurCreation, UtilisateurModification, UtilisateurSortie)
from server.app.securite import (DROITS, auditer, chiffrer_texte, creer_jeton, dechiffrer_texte, droits_de,
                                 exiger_droit, exiger_roles, hacher_mot_de_passe, lire_jeton, utilisateur_courant,
                                 valider_robustesse, verifier_mot_de_passe)
from server.app.services.vues import utilisateur_sortie

router = APIRouter(prefix="/api", tags=["Authentification et utilisateurs"])

ECHECS_MAX = 5
DUREE_BLOCAGE = timedelta(minutes=15)


def _session(u: Utilisateur) -> Session_:
    return Session_(utilisateur=utilisateur_sortie(u), droits=droits_de(u))


def _ouvrir_session(db: Session, u: Utilisateur, rester_connecte: bool, request: Request) -> ReponseConnexion:
    u.echecs_connexion = 0
    u.bloque_jusqua = None
    u.derniere_connexion = maintenant()
    auditer(db, u.identifiant, "CONNEXION", "session longue" if rester_connecte else "", request)
    db.commit()
    return ReponseConnexion(jeton=creer_jeton(u, rester_connecte), session=_session(u))


@router.post("/auth/connexion", response_model=ReponseConnexion)
def connexion(donnees: Connexion, request: Request, db: Session = Depends(get_db)):
    saisie = donnees.identifiant.strip()
    u = db.query(Utilisateur).filter(or_(func.lower(Utilisateur.identifiant) == saisie.lower(),
                                         func.lower(Utilisateur.email) == saisie.lower())).first()
    if u and u.bloque_jusqua and u.bloque_jusqua > maintenant():
        raise HTTPException(423, "Compte temporairement bloqué après plusieurs échecs. Réessayez dans 15 minutes.")
    if u is None or not u.actif or not verifier_mot_de_passe(donnees.mot_de_passe, u.mot_de_passe_hash):
        if u:
            u.echecs_connexion += 1
            if u.echecs_connexion >= ECHECS_MAX:
                u.bloque_jusqua = maintenant() + DUREE_BLOCAGE
                u.echecs_connexion = 0
        auditer(db, saisie[:60], "ECHEC_CONNEXION", request=request)
        db.commit()
        raise HTTPException(401, "Identifiant ou mot de passe incorrect")
    if u.deux_etapes and u.secret_totp:
        auditer(db, u.identifiant, "CONNEXION_ETAPE_1", request=request)
        db.commit()
        temporaire = creer_jeton(u, donnees.rester_connecte, usage="deux_etapes")
        return ReponseConnexion(deux_etapes_requise=True, jeton_temporaire=temporaire)
    return _ouvrir_session(db, u, donnees.rester_connecte, request)


@router.post("/auth/deux-etapes", response_model=ReponseConnexion)
def verifier_deux_etapes(donnees: CodeDeuxEtapes, request: Request, db: Session = Depends(get_db)):
    charge = lire_jeton(donnees.jeton_temporaire, usage="deux_etapes")
    u = db.get(Utilisateur, int(charge["sub"]))
    if u is None or not u.actif or not u.secret_totp:
        raise HTTPException(401, "Session invalide")
    if not pyotp.TOTP(dechiffrer_texte(u.secret_totp)).verify(donnees.code, valid_window=1):
        auditer(db, u.identifiant, "ECHEC_DEUX_ETAPES", request=request)
        db.commit()
        raise HTTPException(401, "Code de vérification incorrect")
    return _ouvrir_session(db, u, bool(charge.get("rc")), request)


@router.post("/auth/mot-de-passe-oublie")
def mot_de_passe_oublie(donnees: MotDePasseOublie, request: Request, db: Session = Depends(get_db)):
    """Signale la demande à l'administrateur (réinitialisation manuelle, sans envoi d'e-mail)."""
    saisie = donnees.identifiant.strip().lower()
    u = db.query(Utilisateur).filter(or_(func.lower(Utilisateur.identifiant) == saisie,
                                         func.lower(Utilisateur.email) == saisie)).first()
    if u:
        u.reinitialisation_demandee = True
        auditer(db, u.identifiant, "MOT_DE_PASSE_OUBLIE", request=request)
        db.commit()
    # Réponse identique que le compte existe ou non (pas d'énumération des comptes).
    return {"message": "Votre demande a été transmise à l'administrateur, qui vous communiquera un nouveau mot de passe."}


@router.get("/auth/session", response_model=Session_)
def session(u: Utilisateur = Depends(utilisateur_courant)):
    return _session(u)


@router.post("/auth/mot-de-passe")
def changer_mot_de_passe(donnees: ChangementMotDePasse, request: Request,
                         u: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    if not verifier_mot_de_passe(donnees.ancien, u.mot_de_passe_hash):
        raise HTTPException(400, "Mot de passe actuel incorrect")
    valider_robustesse(donnees.nouveau)
    u.mot_de_passe_hash = hacher_mot_de_passe(donnees.nouveau)
    auditer(db, u.identifiant, "CHANGEMENT_MOT_DE_PASSE", request=request)
    db.commit()
    return {"message": "Mot de passe modifié"}


@router.post("/auth/deux-etapes/preparer")
def preparer_deux_etapes(u: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    """Génère un secret et le QR code à scanner avec une application d'authentification."""
    secret = pyotp.random_base32()
    u.secret_totp = chiffrer_texte(secret)
    u.deux_etapes = False
    db.commit()
    organisation = db.query(Organisation).first()
    uri = pyotp.TOTP(secret).provisioning_uri(name=u.identifiant,
                                              issuer_name=organisation.sigle if organisation else "Pointage")
    return {"secret": secret, "qr_svg": segno.make(uri, error="m").svg_inline(scale=4)}


@router.post("/auth/deux-etapes/activer")
def activer_deux_etapes(donnees: dict, request: Request, u: Utilisateur = Depends(utilisateur_courant),
                        db: Session = Depends(get_db)):
    if not u.secret_totp or not pyotp.TOTP(dechiffrer_texte(u.secret_totp)).verify(str(donnees.get("code", "")),
                                                                                   valid_window=1):
        raise HTTPException(400, "Code incorrect : vérifiez l'heure de votre téléphone et réessayez")
    u.deux_etapes = True
    auditer(db, u.identifiant, "ACTIVATION_DEUX_ETAPES", request=request)
    db.commit()
    return {"message": "Vérification en deux étapes activée"}


# --- Utilisateurs (gestion réservée à l'administrateur) ---------------------
@router.get("/utilisateurs", response_model=list[UtilisateurSortie])
def lister_utilisateurs(_: Utilisateur = Depends(exiger_roles(Role.ADMIN, Role.DRH)), db: Session = Depends(get_db)):
    return [utilisateur_sortie(u) for u in db.query(Utilisateur).order_by(Utilisateur.role, Utilisateur.nom_complet)]


@router.get("/droits")
def matrice_droits(_: Utilisateur = Depends(utilisateur_courant)):
    return [{"code": code, "libelle": libelle, **{r.value: v for r, v in valeurs.items()}}
            for code, libelle, valeurs in DROITS]


def _verifier_perimetre(role: Role, service_id, site_id):
    if role == Role.RESPONSABLE and not service_id and not site_id:
        raise HTTPException(400, "Un responsable habilité doit avoir un périmètre : un service et/ou un site")


@router.post("/utilisateurs", response_model=UtilisateurSortie, status_code=201)
def creer_utilisateur(donnees: UtilisateurCreation, request: Request,
                      acteur: Utilisateur = Depends(exiger_droit("utilisateurs.gerer")), db: Session = Depends(get_db)):
    if db.query(Utilisateur).filter(func.lower(Utilisateur.identifiant) == donnees.identifiant.lower()).first():
        raise HTTPException(409, "Cet identifiant existe déjà")
    if donnees.email and db.query(Utilisateur).filter(func.lower(Utilisateur.email) == donnees.email.lower()).first():
        raise HTTPException(409, "Cette adresse e-mail est déjà utilisée")
    _verifier_perimetre(donnees.role, donnees.service_id, donnees.site_id)
    valider_robustesse(donnees.mot_de_passe)
    valeurs = donnees.model_dump(exclude={"mot_de_passe"})
    valeurs["email"] = valeurs["email"] or None
    if donnees.role != Role.RESPONSABLE:
        valeurs.update(service_id=None, site_id=None)
    u = Utilisateur(**valeurs, mot_de_passe_hash=hacher_mot_de_passe(donnees.mot_de_passe))
    db.add(u)
    auditer(db, acteur.identifiant, "CREATION_UTILISATEUR", f"{u.identifiant} ({u.role.value})", request)
    db.commit()
    db.refresh(u)
    return utilisateur_sortie(u)


@router.put("/utilisateurs/{utilisateur_id}", response_model=UtilisateurSortie)
def modifier_utilisateur(utilisateur_id: int, donnees: UtilisateurModification, request: Request,
                         acteur: Utilisateur = Depends(exiger_droit("utilisateurs.gerer")),
                         db: Session = Depends(get_db)):
    u = db.get(Utilisateur, utilisateur_id)
    if u is None:
        raise HTTPException(404, "Utilisateur introuvable")
    valeurs = donnees.model_dump(exclude_unset=True)
    if u.id == acteur.id and (valeurs.get("actif") is False or valeurs.get("role", Role.ADMIN) != Role.ADMIN):
        raise HTTPException(400, "Vous ne pouvez pas retirer vos propres droits d'administrateur")
    mot_de_passe = valeurs.pop("mot_de_passe", None)
    if mot_de_passe:
        valider_robustesse(mot_de_passe)
        u.mot_de_passe_hash = hacher_mot_de_passe(mot_de_passe)
        u.bloque_jusqua = None
        u.reinitialisation_demandee = False
    if valeurs.pop("desactiver_deux_etapes", False):
        u.deux_etapes, u.secret_totp = False, None
    if "email" in valeurs:
        valeurs["email"] = valeurs["email"] or None
    for k, v in valeurs.items():
        setattr(u, k, v)
    if u.role != Role.RESPONSABLE:
        u.service_id = u.site_id = None
    _verifier_perimetre(u.role, u.service_id, u.site_id)
    champs = sorted(valeurs) + (["mot_de_passe"] if mot_de_passe else [])
    auditer(db, acteur.identifiant, "MODIFICATION_UTILISATEUR", f"{u.identifiant} : {', '.join(champs)}", request)
    db.commit()
    return utilisateur_sortie(u)


@router.get("/audit")
def journal_audit(limite: int = 300, acteur: str = "", action: str = "",
                  _: Utilisateur = Depends(exiger_droit("audit.consulter")), db: Session = Depends(get_db)):
    requete = db.query(JournalAudit)
    if acteur:
        requete = requete.filter(JournalAudit.acteur.ilike(f"%{acteur}%"))
    if action:
        requete = requete.filter(JournalAudit.action == action)
    lignes = requete.order_by(JournalAudit.id.desc()).limit(min(limite, 2000)).all()
    return [{"date": l.date, "acteur": l.acteur, "action": l.action, "details": l.details,
             "adresse_ip": l.adresse_ip} for l in lignes]
