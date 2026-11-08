"""Schémas d'échange (API REST)."""
from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field

from server.app.models import Role, TypeAppareil, TypePointage, TypeSite


class Lecture(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Organisation (marque blanche) ------------------------------------------
class OrganisationSortie(Lecture):
    nom: str
    sigle: str
    slogan: str
    couleur_primaire: str
    couleur_menu: str
    prefixe_matricule: str
    deux_etapes_obligatoire_admin: bool
    duree_conservation_jours: int
    a_un_logo: bool = False


class OrganisationModification(BaseModel):
    nom: str | None = None
    sigle: str | None = None
    slogan: str | None = None
    couleur_primaire: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    couleur_menu: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    prefixe_matricule: str | None = None
    deux_etapes_obligatoire_admin: bool | None = None
    duree_conservation_jours: int | None = Field(None, ge=30, le=3650)


# --- Authentification / utilisateurs ---------------------------------------
class Connexion(BaseModel):
    identifiant: str = Field(description="Matricule, identifiant ou adresse e-mail")
    mot_de_passe: str
    rester_connecte: bool = False


class CodeDeuxEtapes(BaseModel):
    jeton_temporaire: str
    code: str = Field(min_length=6, max_length=6)


class UtilisateurSortie(BaseModel):
    id: int
    identifiant: str
    email: str | None
    nom_complet: str
    fonction: str
    role: Role
    service_id: int | None
    site_id: int | None
    perimetre: str
    actif: bool
    deux_etapes: bool
    derniere_connexion: datetime | None
    reinitialisation_demandee: bool


class Session_(BaseModel):
    utilisateur: UtilisateurSortie
    droits: dict[str, str]


class ReponseConnexion(BaseModel):
    jeton: str | None = None
    deux_etapes_requise: bool = False
    jeton_temporaire: str | None = None
    session: Session_ | None = None


class UtilisateurCreation(BaseModel):
    identifiant: str = Field(min_length=3, max_length=50)
    email: str | None = None
    nom_complet: str = ""
    fonction: str = ""
    mot_de_passe: str
    role: Role
    service_id: int | None = None
    site_id: int | None = None


class UtilisateurModification(BaseModel):
    email: str | None = None
    nom_complet: str | None = None
    fonction: str | None = None
    role: Role | None = None
    service_id: int | None = None
    site_id: int | None = None
    actif: bool | None = None
    mot_de_passe: str | None = None
    desactiver_deux_etapes: bool | None = None


class ChangementMotDePasse(BaseModel):
    ancien: str
    nouveau: str


class MotDePasseOublie(BaseModel):
    identifiant: str


# --- Référentiels -----------------------------------------------------------
class ServiceEntree(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    nom: str


class ServiceSortie(Lecture, ServiceEntree):
    id: int


class SiteEntree(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    nom: str
    nom_court: str = ""
    type: TypeSite
    ville: str = ""
    actif: bool = True


class SiteSortie(Lecture, SiteEntree):
    id: int
    nb_terminaux: int = 0
    etat: str = "AUCUN_TERMINAL"   # EN_LIGNE | SYNCHRO | HORS_LIGNE | AUCUN_TERMINAL
    nb_agents: int = 0


class HoraireEntree(BaseModel):
    nom: str
    heure_debut: time
    heure_fin: time
    tolerance_minutes: int = Field(10, ge=0, le=240)
    jours_travailles: str = "0,1,2,3,4"


class HoraireSortie(Lecture, HoraireEntree):
    id: int


class TerminalEntree(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    libelle: str = ""
    site_id: int
    type: TypeAppareil = TypeAppareil.BORNE


class TerminalModification(BaseModel):
    libelle: str | None = None
    site_id: int | None = None
    actif: bool | None = None


class TerminalSortie(BaseModel):
    id: int
    code: str
    libelle: str
    site_id: int
    site_nom: str
    actif: bool
    dernier_contact: datetime | None
    adresse_ip: str
    version: str
    nb_en_attente: int
    synchro_demandee: bool
    type: TypeAppareil
    etat: str  # EN_LIGNE | SYNCHRO | HORS_LIGNE | DESACTIVE | JAMAIS_CONNECTE


class TerminalCle(TerminalSortie):
    cle_api: str  # affichée une seule fois
    url_serveur: str | None = None  # adresse à inscrire dans la configuration de l'appareil


# --- Agents -----------------------------------------------------------------
class AgentEntree(BaseModel):
    matricule: str = Field(min_length=1, max_length=20)
    nom: str = Field(min_length=1)
    prenom: str = Field(min_length=1)
    fonction: str = ""
    email: str = ""
    telephone: str = ""
    service_id: int
    site_rattachement_id: int
    horaire_id: int
    tous_sites: bool = True
    sites_autorises: list[int] = []


class AgentModification(BaseModel):
    nom: str | None = None
    prenom: str | None = None
    fonction: str | None = None
    email: str | None = None
    telephone: str | None = None
    service_id: int | None = None
    site_rattachement_id: int | None = None
    horaire_id: int | None = None
    tous_sites: bool | None = None
    sites_autorises: list[int] | None = None
    actif: bool | None = None


class AgentSortie(BaseModel):
    id: int
    matricule: str
    nom: str
    prenom: str
    nom_complet: str
    fonction: str
    email: str
    telephone: str
    service_id: int
    service_nom: str
    site_rattachement_id: int
    site_rattachement_nom: str
    horaire_id: int
    horaire_nom: str
    tous_sites: bool
    sites_autorises: list[int]
    actif: bool
    nb_gabarits: int
    consentement_le: datetime | None
    cree_le: datetime


class ImagePose(BaseModel):
    pose: str = Field(pattern="^(face|gauche|droite|haut|bas)$")
    image: str = Field(description="Image JPEG/PNG en base64 (data-URL acceptée)")


class Enrolement(BaseModel):
    consentement: bool
    images: list[ImagePose] = Field(min_length=1, max_length=15)


class AnalyseImage(BaseModel):
    image: str


class EnrolementResultat(BaseModel):
    gabarits_enregistres: int
    images_rejetees: list[str]
    vivacite: bool


class PageResultats(BaseModel):
    total: int
    elements: list


# --- Échanges avec les terminaux --------------------------------------------
class PointageTerminal(BaseModel):
    uuid: str = Field(min_length=8, max_length=36)
    matricule: str
    horodatage: datetime
    type: TypePointage
    score: float = 0.0
    hors_ligne: bool = False


class LotPointages(BaseModel):
    pointages: list[PointageTerminal] = Field(max_length=500)


class TentativeTerminal(BaseModel):
    uuid: str = Field(min_length=8, max_length=36)
    horodatage: datetime
    motif: str = Field(max_length=40)
    matricule_suppose: str | None = None
    score: float = 0.0
    hors_ligne: bool = False


class LotTentatives(BaseModel):
    tentatives: list[TentativeTerminal] = Field(max_length=500)


class LotAnnulations(BaseModel):
    uuids: list[str] = Field(max_length=500)


class ResultatSynchro(BaseModel):
    acceptes: list[str]
    doublons: list[str]
    rejetes: dict[str, str]
