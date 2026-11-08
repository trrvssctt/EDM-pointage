"""Conversion des objets métier en réponses d'API (états calculés, libellés)."""
from __future__ import annotations

from datetime import timedelta

from common.moteur_facial import SEUIL_SIMILARITE
from server.app import config
from server.app.models import Agent, Site, Terminal, Utilisateur, maintenant
from server.app.schemas import AgentSortie, SiteSortie, TerminalCle, TerminalSortie, UtilisateurSortie
from server.app.securite import libelle_perimetre


def confiance(score: float) -> int:
    """Indice de confiance affiché (%) : 60 % au seuil d'acceptation, 99 % pour une similarité ≥ 0,75."""
    if score <= 0:
        return 0
    valeur = 60 + (score - SEUIL_SIMILARITE) / (0.75 - SEUIL_SIMILARITE) * 39
    return int(max(0, min(99, round(valeur))))


def etat_terminal(t: Terminal) -> str:
    if not t.actif:
        return "DESACTIVE"
    if t.dernier_contact is None:
        return "JAMAIS_CONNECTE"
    if maintenant() - t.dernier_contact > timedelta(seconds=config.DELAI_TERMINAL_EN_LIGNE_S):
        return "HORS_LIGNE"
    return "SYNCHRO" if t.nb_en_attente else "EN_LIGNE"


def terminal_sortie(t: Terminal, cle: str | None = None) -> TerminalSortie:
    donnees = dict(id=t.id, code=t.code, libelle=t.libelle, site_id=t.site_id, site_nom=t.site.libelle_court,
                   actif=t.actif, dernier_contact=t.dernier_contact, adresse_ip=t.adresse_ip, version=t.version,
                   nb_en_attente=t.nb_en_attente, synchro_demandee=t.synchro_demandee, type=t.type,
                   etat=etat_terminal(t))
    return TerminalCle(**donnees, cle_api=cle, url_serveur=config.URL_APPAREILS or None) if cle else TerminalSortie(**donnees)


def site_sortie(s: Site, nb_agents: int = 0) -> SiteSortie:
    etats = {etat_terminal(t) for t in s.terminaux if t.actif and t.type.value == "BORNE"}
    etat = next((e for e in ("HORS_LIGNE", "SYNCHRO", "EN_LIGNE") if e in etats),
                "JAMAIS_CONNECTE" if etats else "AUCUN_TERMINAL")
    return SiteSortie(id=s.id, code=s.code, nom=s.nom, nom_court=s.nom_court, type=s.type, ville=s.ville,
                      actif=s.actif, nb_terminaux=sum(1 for t in s.terminaux if t.actif and t.type.value == "BORNE"), etat=etat,
                      nb_agents=nb_agents)


def agent_sortie(a: Agent) -> AgentSortie:
    return AgentSortie(
        id=a.id, matricule=a.matricule, nom=a.nom, prenom=a.prenom, nom_complet=a.nom_complet, fonction=a.fonction,
        email=a.email, telephone=a.telephone, service_id=a.service_id, service_nom=a.service.nom,
        site_rattachement_id=a.site_rattachement_id, site_rattachement_nom=a.site_rattachement.libelle_court,
        horaire_id=a.horaire_id, horaire_nom=a.horaire.nom, tous_sites=a.tous_sites,
        sites_autorises=[s.id for s in a.sites_autorises], actif=a.actif, nb_gabarits=len(a.gabarits),
        consentement_le=a.consentement_le, cree_le=a.cree_le)


def utilisateur_sortie(u: Utilisateur) -> UtilisateurSortie:
    return UtilisateurSortie(
        id=u.id, identifiant=u.identifiant, email=u.email, nom_complet=u.nom_complet, fonction=u.fonction,
        role=u.role, service_id=u.service_id, site_id=u.site_id, perimetre=libelle_perimetre(u), actif=u.actif,
        deux_etapes=u.deux_etapes, derniere_connexion=u.derniere_connexion,
        reinitialisation_demandee=u.reinitialisation_demandee)
