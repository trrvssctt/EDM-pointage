"""Authentification, habilitations (matrice des droits), chiffrement et audit."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import numpy as np
from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Query, Session

from server.app import config
from server.app.database import get_db
from server.app.models import Agent, JournalAudit, Role, Terminal, Utilisateur, maintenant

ITERATIONS_PBKDF2 = 240_000
_fernet = Fernet(config.CLE_BIOMETRIE.encode())
_bearer = HTTPBearer(auto_error=False)

# --- Matrice des droits (identique à l'écran « Utilisateurs et droits ») -----
OUI, NON, PERIMETRE = "oui", "non", "perimetre"
DROITS: list[tuple[str, str, dict[Role, str]]] = [
    ("agents.gerer", "Gérer les dossiers agents", {Role.ADMIN: OUI, Role.DRH: OUI, Role.RESPONSABLE: PERIMETRE}),
    ("biometrie.enroler", "Enrôler et valider les visages", {Role.ADMIN: OUI, Role.DRH: OUI, Role.RESPONSABLE: NON}),
    ("biometrie.proposer", "Proposer un enrôlement (application mobile)",
     {Role.ADMIN: OUI, Role.DRH: OUI, Role.RESPONSABLE: PERIMETRE}),
    ("biometrie.supprimer", "Supprimer un gabarit biométrique",
     {Role.ADMIN: OUI, Role.DRH: OUI, Role.RESPONSABLE: NON}),
    ("pointages.secours", "Pointage de secours (application mobile)",
     {Role.ADMIN: OUI, Role.DRH: OUI, Role.RESPONSABLE: PERIMETRE}),
    ("pointages.consulter", "Consulter les pointages", {Role.ADMIN: OUI, Role.DRH: OUI, Role.RESPONSABLE: PERIMETRE}),
    ("rapports.generer", "Générer les rapports", {Role.ADMIN: OUI, Role.DRH: OUI, Role.RESPONSABLE: PERIMETRE}),
    ("sites.gerer", "Gérer sites et terminaux", {Role.ADMIN: OUI, Role.DRH: NON, Role.RESPONSABLE: NON}),
    ("utilisateurs.gerer", "Gérer utilisateurs et droits", {Role.ADMIN: OUI, Role.DRH: NON, Role.RESPONSABLE: NON}),
    ("audit.consulter", "Consulter le journal d'audit", {Role.ADMIN: OUI, Role.DRH: OUI, Role.RESPONSABLE: NON}),
]
_INDEX_DROITS = {code: valeurs for code, _, valeurs in DROITS}


def a_le_droit(utilisateur: Utilisateur, droit: str) -> bool:
    return _INDEX_DROITS[droit][utilisateur.role] != NON


def droits_de(utilisateur: Utilisateur) -> dict[str, str]:
    return {code: valeurs[utilisateur.role] for code, _, valeurs in DROITS}


def perimetre(requete: Query, utilisateur: Utilisateur) -> Query:
    """Restreint une requête portant sur Agent au périmètre d'un responsable habilité."""
    if utilisateur.role == Role.RESPONSABLE:
        if utilisateur.service_id:
            requete = requete.filter(Agent.service_id == utilisateur.service_id)
        if utilisateur.site_id:
            requete = requete.filter(Agent.site_rattachement_id == utilisateur.site_id)
        if not utilisateur.service_id and not utilisateur.site_id:
            requete = requete.filter(Agent.id == -1)  # périmètre vide par prudence
    return requete


def libelle_perimetre(u: Utilisateur) -> str:
    if u.role != Role.RESPONSABLE:
        return "Tous les sites"
    morceaux = [x for x in ((u.service.nom if u.service else ""), (u.site.libelle_court if u.site else "")) if x]
    return " · ".join(morceaux) or "Aucun"


# --- Mots de passe (PBKDF2-HMAC-SHA256, sel aléatoire) ----------------------
def hacher_mot_de_passe(mot_de_passe: str) -> str:
    sel = secrets.token_bytes(16)
    empreinte = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel, ITERATIONS_PBKDF2)
    return f"pbkdf2_sha256${ITERATIONS_PBKDF2}${base64.b64encode(sel).decode()}${base64.b64encode(empreinte).decode()}"


def verifier_mot_de_passe(mot_de_passe: str, stocke: str) -> bool:
    try:
        _, iterations, sel, empreinte = stocke.split("$")
        calcul = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), base64.b64decode(sel), int(iterations))
        return hmac.compare_digest(calcul, base64.b64decode(empreinte))
    except ValueError:
        return False


def valider_robustesse(mot_de_passe: str) -> None:
    if (len(mot_de_passe) < 8 or not any(c.isdigit() for c in mot_de_passe)
            or not any(c.isalpha() for c in mot_de_passe)):
        raise HTTPException(400, "Mot de passe trop faible : 8 caractères minimum, avec des lettres et des chiffres.")


# --- Jetons JWT -------------------------------------------------------------
def creer_jeton(utilisateur: Utilisateur, rester_connecte: bool = False, usage: str = "session") -> str:
    if usage == "deux_etapes":
        duree = timedelta(minutes=5)
    else:
        duree = timedelta(days=30) if rester_connecte else timedelta(minutes=config.DUREE_JETON_MINUTES)
    charge = {"sub": str(utilisateur.id), "role": utilisateur.role.value, "usage": usage,
              "rc": rester_connecte, "exp": datetime.now(timezone.utc) + duree}
    return jwt.encode(charge, config.CLE_JWT, algorithm="HS256")


def lire_jeton(jeton: str, usage: str = "session") -> dict:
    try:
        charge = jwt.decode(jeton, config.CLE_JWT, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée, reconnectez-vous")
    if charge.get("usage", "session") != usage:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide")
    return charge


def utilisateur_courant(
    identifiants: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Utilisateur:
    if identifiants is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise")
    charge = lire_jeton(identifiants.credentials)
    utilisateur = db.get(Utilisateur, int(charge["sub"]))
    if utilisateur is None or not utilisateur.actif:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte inactif")
    return utilisateur


def exiger_droit(droit: str):
    def verification(utilisateur: Utilisateur = Depends(utilisateur_courant)) -> Utilisateur:
        if not a_le_droit(utilisateur, droit):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Votre profil ne permet pas cette action")
        return utilisateur
    return verification


def exiger_roles(*roles: Role):
    def verification(utilisateur: Utilisateur = Depends(utilisateur_courant)) -> Utilisateur:
        if utilisateur.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Votre profil ne permet pas cette action")
        return utilisateur
    return verification


# --- Terminaux de pointage (clé d'API) --------------------------------------
def empreinte_cle(cle: str) -> str:
    return hashlib.sha256(cle.encode()).hexdigest()


def generer_cle_terminal() -> str:
    return "edmt_" + secrets.token_urlsafe(32)


def terminal_courant(
    request: Request,
    x_terminal_key: str = Header(..., alias="X-Terminal-Key"),
    x_terminal_version: str = Header("", alias="X-Terminal-Version"),
    x_terminal_en_attente: int | None = Header(None, alias="X-Terminal-En-Attente"),
    db: Session = Depends(get_db),
) -> Terminal:
    terminal = db.query(Terminal).filter_by(empreinte_cle=empreinte_cle(x_terminal_key)).first()
    if terminal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Terminal inconnu")
    if not terminal.actif or not terminal.site.actif:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Terminal ou site non autorisé au pointage")
    terminal.dernier_contact = maintenant()
    terminal.adresse_ip = request.client.host if request.client else ""
    if x_terminal_version:
        terminal.version = x_terminal_version[:20]
    if x_terminal_en_attente is not None:
        terminal.nb_en_attente = max(0, x_terminal_en_attente)
    db.commit()
    return terminal


# --- Chiffrement (gabarits biométriques, secrets TOTP) ----------------------
def chiffrer_gabarit(vecteur: np.ndarray) -> bytes:
    return _fernet.encrypt(vecteur.astype(np.float32).tobytes())


def dechiffrer_gabarit(donnees: bytes) -> np.ndarray:
    return np.frombuffer(_fernet.decrypt(donnees), dtype=np.float32).copy()


def chiffrer_texte(texte: str) -> str:
    return _fernet.encrypt(texte.encode()).decode()


def dechiffrer_texte(texte: str) -> str:
    return _fernet.decrypt(texte.encode()).decode()


# --- Journal d'audit --------------------------------------------------------
def auditer(db: Session, acteur: str, action: str, details: str = "", request: Request | None = None) -> None:
    ip = request.client.host if request is not None and request.client else ""
    db.add(JournalAudit(acteur=acteur, action=action, details=details, adresse_ip=ip))
