"""Modèle de données du système de pointage biométrique multisite."""
from __future__ import annotations

import enum
from datetime import datetime, time

from sqlalchemy import (Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, LargeBinary, String, Table, Text,
                        Time, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.app.database import Base


def maintenant() -> datetime:
    return datetime.now().replace(microsecond=0)


class Role(str, enum.Enum):
    ADMIN = "ADMIN"              # administrateur système
    DRH = "DRH"                  # Direction des Ressources Humaines
    RESPONSABLE = "RESPONSABLE"  # responsable habilité (limité à son service ou à son site)


class TypeSite(str, enum.Enum):
    SIEGE = "SIEGE"
    DIRECTION_REGIONALE = "DIRECTION_REGIONALE"
    AGENCE = "AGENCE"
    CENTRALE = "CENTRALE"
    SERVICE_TECHNIQUE = "SERVICE_TECHNIQUE"


class TypePointage(str, enum.Enum):
    ENTREE = "ENTREE"
    SORTIE = "SORTIE"


class TypeAppareil(str, enum.Enum):
    BORNE = "BORNE"    # terminal fixe de pointage
    MOBILE = "MOBILE"  # téléphone de l'application terrain (enrôlement, pointage de secours)


class StatutDemande(str, enum.Enum):
    RECUE = "RECUE"
    GABARIT_CALCULE = "GABARIT_CALCULE"
    VALIDEE = "VALIDEE"
    REJETEE = "REJETEE"


class Organisation(Base):
    """Identité de l'entreprise cliente (marque blanche) : nom, logo, couleurs, politique."""
    __tablename__ = "organisation"
    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120), default="Énergie du Mali")
    sigle: Mapped[str] = mapped_column(String(30), default="EDM S.A.")
    slogan: Mapped[str] = mapped_column(String(200), default="Gestion des présences")
    couleur_primaire: Mapped[str] = mapped_column(String(7), default="#1A3A8F")
    couleur_menu: Mapped[str] = mapped_column(String(7), default="#12286B")
    logo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_type: Mapped[str] = mapped_column(String(40), default="image/png")
    prefixe_matricule: Mapped[str] = mapped_column(String(10), default="EDM-")
    # Politique de sécurité
    deux_etapes_obligatoire_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    duree_conservation_jours: Mapped[int] = mapped_column(Integer, default=1825)  # 5 ans
    modifie_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant, onupdate=maintenant)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    nom: Mapped[str] = mapped_column(String(120))


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    nom: Mapped[str] = mapped_column(String(120))
    nom_court: Mapped[str] = mapped_column(String(60), default="")
    type: Mapped[TypeSite] = mapped_column(Enum(TypeSite, native_enum=False, length=30))
    ville: Mapped[str] = mapped_column(String(80), default="")
    # Faux : le site n'est plus autorisé au pointage (ses terminaux sont refusés).
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    terminaux: Mapped[list[Terminal]] = relationship(back_populates="site")

    @property
    def libelle_court(self) -> str:
        return self.nom_court or self.nom


class Horaire(Base):
    __tablename__ = "horaires"
    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(80), unique=True)
    heure_debut: Mapped[time] = mapped_column(Time)
    heure_fin: Mapped[time] = mapped_column(Time)
    tolerance_minutes: Mapped[int] = mapped_column(Integer, default=10)
    # Jours travaillés, 0 = lundi ... 6 = dimanche
    jours_travailles: Mapped[str] = mapped_column(String(20), default="0,1,2,3,4")

    def jours(self) -> set[int]:
        return {int(j) for j in self.jours_travailles.split(",") if j.strip()}


class Terminal(Base):
    __tablename__ = "terminaux"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    libelle: Mapped[str] = mapped_column(String(120), default="")
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    empreinte_cle: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256 de la clé d'API
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    dernier_contact: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    adresse_ip: Mapped[str] = mapped_column(String(45), default="")
    version: Mapped[str] = mapped_column(String(20), default="")
    nb_en_attente: Mapped[int] = mapped_column(Integer, default=0)  # déclaré par le terminal
    synchro_demandee: Mapped[bool] = mapped_column(Boolean, default=False)
    type: Mapped[TypeAppareil] = mapped_column(Enum(TypeAppareil, native_enum=False, length=10),
                                               default=TypeAppareil.BORNE)
    site: Mapped[Site] = relationship(back_populates="terminaux")


agent_sites = Table(
    "agent_sites_autorises", Base.metadata,
    Column("agent_id", ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("site_id", ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True),
)


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[int] = mapped_column(primary_key=True)
    matricule: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    nom: Mapped[str] = mapped_column(String(80))
    prenom: Mapped[str] = mapped_column(String(80))
    fonction: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    telephone: Mapped[str] = mapped_column(String(30), default="")
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    site_rattachement_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    horaire_id: Mapped[int] = mapped_column(ForeignKey("horaires.id"))
    # Vrai : l'agent peut pointer sur tous les sites équipés ; sinon seulement sur sites_autorises.
    tous_sites: Mapped[bool] = mapped_column(Boolean, default=True)
    consentement_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    modifie_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant, onupdate=maintenant)

    service: Mapped[Service] = relationship()
    site_rattachement: Mapped[Site] = relationship()
    horaire: Mapped[Horaire] = relationship()
    sites_autorises: Mapped[list[Site]] = relationship(secondary=agent_sites)
    gabarits: Mapped[list[GabaritFacial]] = relationship(back_populates="agent", cascade="all, delete-orphan")

    @property
    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom.title() if self.nom.isupper() else self.nom}"

    def peut_pointer_sur(self, site_id: int) -> bool:
        return self.tous_sites or site_id == self.site_rattachement_id or any(
            s.id == site_id for s in self.sites_autorises)


class GabaritFacial(Base):
    """Vecteur biométrique (128 flottants) chiffré. Aucune photo n'est conservée."""
    __tablename__ = "gabarits_faciaux"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    pose: Mapped[str] = mapped_column(String(10), default="")
    donnees_chiffrees: Mapped[bytes] = mapped_column(LargeBinary)
    qualite: Mapped[float] = mapped_column(Float, default=0.0)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    agent: Mapped[Agent] = relationship(back_populates="gabarits")


class Pointage(Base):
    __tablename__ = "pointages"
    __table_args__ = (UniqueConstraint("uuid", name="uq_pointage_uuid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    # Identifiant généré par le terminal : garantit l'unicité de l'événement
    # même s'il est transmis plusieurs fois (resynchronisation).
    uuid: Mapped[str] = mapped_column(String(36))
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    matricule: Mapped[str] = mapped_column(String(20), index=True)
    horodatage: Mapped[datetime] = mapped_column(DateTime, index=True)
    type: Mapped[TypePointage] = mapped_column(Enum(TypePointage, native_enum=False, length=10))
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    terminal_id: Mapped[int] = mapped_column(ForeignKey("terminaux.id"))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    hors_ligne: Mapped[bool] = mapped_column(Boolean, default=False)  # enregistré pendant une coupure
    annule: Mapped[bool] = mapped_column(Boolean, default=False)      # « Ce n'est pas moi »
    secours: Mapped[bool] = mapped_column(Boolean, default=False)     # pointage de secours (téléphone)
    recu_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)

    agent: Mapped[Agent] = relationship()
    site: Mapped[Site] = relationship()
    terminal: Mapped[Terminal] = relationship()


class TentativeRejetee(Base):
    """Événement refusé ou signalé sur un terminal : visage inconnu, fraude, contestation, appel superviseur."""
    __tablename__ = "tentatives_rejetees"
    __table_args__ = (UniqueConstraint("uuid", name="uq_tentative_uuid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36))
    horodatage: Mapped[datetime] = mapped_column(DateTime, index=True)
    motif: Mapped[str] = mapped_column(String(40))
    matricule_suppose: Mapped[str | None] = mapped_column(String(20), nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    terminal_id: Mapped[int] = mapped_column(ForeignKey("terminaux.id"))
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    hors_ligne: Mapped[bool] = mapped_column(Boolean, default=False)
    traitee: Mapped[bool] = mapped_column(Boolean, default=False)
    terminal: Mapped[Terminal] = relationship()
    site: Mapped[Site] = relationship()


class LotSynchronisation(Base):
    """Journal des lots reçus des terminaux (preuve de l'absence de doublons)."""
    __tablename__ = "lots_synchronisation"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=maintenant, index=True)
    terminal_id: Mapped[int] = mapped_column(ForeignKey("terminaux.id"))
    recus: Mapped[int] = mapped_column(Integer, default=0)
    doublons: Mapped[int] = mapped_column(Integer, default=0)
    rejetes: Mapped[int] = mapped_column(Integer, default=0)
    terminal: Mapped[Terminal] = relationship()


class DemandeEnrolement(Base):
    """Enrôlement proposé depuis l'application mobile, en attente de validation par la DRH.

    Les photos sont chiffrées et conservées uniquement jusqu'à la décision, puis effacées."""
    __tablename__ = "demandes_enrolement"
    __table_args__ = (UniqueConstraint("uuid", name="uq_demande_uuid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36))
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    appareil_id: Mapped[int] = mapped_column(ForeignKey("terminaux.id"))
    auteur_id: Mapped[int] = mapped_column(ForeignKey("utilisateurs.id"))
    photos_chiffrees: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    gabarits_chiffres: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    nb_photos: Mapped[int] = mapped_column(Integer, default=0)
    vivacite: Mapped[bool] = mapped_column(Boolean, default=False)
    controles: Mapped[str] = mapped_column(Text, default="")
    statut: Mapped[StatutDemande] = mapped_column(Enum(StatutDemande, native_enum=False, length=20),
                                                  default=StatutDemande.RECUE)
    motif: Mapped[str] = mapped_column(String(300), default="")
    capture_le: Mapped[datetime] = mapped_column(DateTime)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    traite_par: Mapped[str] = mapped_column(String(60), default="")
    traite_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    agent: Mapped[Agent] = relationship()
    appareil: Mapped[Terminal] = relationship()
    auteur: Mapped["Utilisateur"] = relationship()


class Utilisateur(Base):
    __tablename__ = "utilisateurs"
    id: Mapped[int] = mapped_column(primary_key=True)
    identifiant: Mapped[str] = mapped_column(String(50), unique=True)  # matricule ou identifiant de connexion
    email: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    nom_complet: Mapped[str] = mapped_column(String(120), default="")
    fonction: Mapped[str] = mapped_column(String(120), default="")
    mot_de_passe_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=20))
    # Périmètre d'un RESPONSABLE : un service, un site, ou les deux.
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    echecs_connexion: Mapped[int] = mapped_column(Integer, default=0)
    bloque_jusqua: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    derniere_connexion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    secret_totp: Mapped[str | None] = mapped_column(String(255), nullable=True)   # chiffré
    deux_etapes: Mapped[bool] = mapped_column(Boolean, default=False)
    reinitialisation_demandee: Mapped[bool] = mapped_column(Boolean, default=False)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    service: Mapped[Service | None] = relationship()
    site: Mapped[Site | None] = relationship()


class JournalAudit(Base):
    __tablename__ = "journal_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=maintenant, index=True)
    acteur: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(60))
    details: Mapped[str] = mapped_column(Text, default="")
    adresse_ip: Mapped[str] = mapped_column(String(45), default="")
