"""Remet les données de démonstration à jour, par exemple le matin d'une présentation.

Les données fictives de server/seed.py s'arrêtent au jour de l'installation. Ce script :
- complète l'historique des agents FICTIFS jusqu'à maintenant (entrées, sorties, retards, absences,
  missions sur d'autres sites, pointages différés), sans jamais créer d'heure dans le futur ;
- ajoute quelques tentatives refusées (anomalies du jour à traiter) et les lots de synchronisation ;
- renseigne le dernier contact des bornes d'après leurs pointages (au lieu de « jamais connectée ») ;
- sur demande (--corriger-fuseau), corrige une seule fois l'heure des événements mobiles enregistrés avant le
  réglage du fuseau horaire : uniquement sur un serveur qui tournait en UTC+1 (le VPS d'EDM, jusqu'au 08/11/2026).

Ne touche ni aux comptes, ni aux clés des appareils, ni aux agents réellement enrôlés et à leurs pointages.
Relançable sans risque : rien n'est créé deux fois (identifiants déterministes). Sur le VPS :
    cd /opt/edm-pointage && .venv/bin/python -m server.actualiser_demo --corriger-fuseau   # première fois sur le VPS
    cd /opt/edm-pointage && .venv/bin/python -m server.actualiser_demo                     # ensuite
"""
from __future__ import annotations

import argparse
import random
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from server.app.database import SessionLocale
from server.app.models import (Agent, DemandeEnrolement, GabaritFacial, JournalAudit, LotSynchronisation, Pointage,
                               TentativeRejetee, Terminal, TypeAppareil, TypePointage, maintenant)

ESPACE = uuid.UUID("3b0f8f52-6a0e-4c1e-9d55-0e5d2f1a7c41")  # identifiants déterministes des données générées
JOURS = 21
# Avant cet instant (envoi du correctif de fuseau horaire), le serveur enregistrait les heures en UTC+1.
LIMITE_FUSEAU = datetime(2026, 11, 8, 14, 52)


def _uuid(*parties) -> str:
    return str(uuid.uuid5(ESPACE, "|".join(map(str, parties))))


def agents_fictifs(db: Session) -> list[Agent]:
    """Agents de démonstration : gabarits aléatoires de server/seed.py (qualité 0,9), sans visage réel."""
    ids = {g.agent_id for g in db.query(GabaritFacial).filter(GabaritFacial.pose == "face")
           if abs((g.qualite or 0) - 0.9) < 1e-6}
    return (db.query(Agent).options(joinedload(Agent.horaire)).filter(Agent.id.in_(ids), Agent.actif.is_(True))
            .order_by(Agent.matricule).all())


def completer_historique(db: Session, agents: list[Agent], bornes: list[Terminal], debut: date, fin: datetime) -> int:
    par_site: dict[int, list[Terminal]] = {}
    for t in sorted(bornes, key=lambda t: t.code):
        par_site.setdefault(t.site_id, []).append(t)
    sites_equipes = sorted(par_site)
    deja = {(a, h.date(), t) for a, h, t in db.query(Pointage.agent_id, Pointage.horodatage, Pointage.type)
            .filter(Pointage.horodatage >= datetime.combine(debut, datetime.min.time()))}
    crees = 0
    for a in agents:
        itinerant = random.Random(f"itinerant|{a.matricule}").random() < 0.18
        jour = debut
        while jour <= fin.date():
            rng = random.Random(f"{a.matricule}|{jour.isoformat()}")
            jour_suivant = jour + timedelta(days=1)
            if jour.weekday() not in a.horaire.jours() or rng.random() < 0.07:  # repos ou absence
                jour = jour_suivant
                continue
            site_id = a.site_rattachement_id
            if (itinerant and rng.random() < 0.5) or site_id not in par_site:
                site_id = rng.choice(sites_equipes)
            t = rng.choice(par_site[site_id])
            retard = rng.choice([0] * 9 + [rng.randint(12, 48)])
            entree = datetime.combine(jour, a.horaire.heure_debut) + timedelta(
                minutes=retard or -rng.randint(2, 25), seconds=rng.randint(0, 59))
            sortie = datetime.combine(jour, a.horaire.heure_fin) + timedelta(minutes=rng.randint(-3, 50), seconds=rng.randint(0, 59))
            differe = t.code == "TRM-SEL-01" and rng.random() < 0.35
            oubli_sortie = rng.random() < 0.03
            for type_, heure in ((TypePointage.ENTREE, entree), (TypePointage.SORTIE, sortie)):
                if heure > fin or (a.id, jour, type_) in deja or (type_ == TypePointage.SORTIE and oubli_sortie):
                    continue
                recu = heure + (timedelta(hours=rng.randint(1, 5)) if differe else timedelta(seconds=2))
                db.add(Pointage(uuid=_uuid("pointage", a.matricule, jour, type_.value), agent_id=a.id, matricule=a.matricule,
                                horodatage=heure, type=type_, site_id=site_id, terminal_id=t.id,
                                score=rng.uniform(0.66, 0.92), hors_ligne=differe, recu_le=min(recu, fin)))
                deja.add((a.id, jour, type_))
                crees += 1
            jour = jour_suivant
    return crees


def ajouter_tentatives(db: Session, agents: list[Agent], bornes: list[Terminal], debut: date, fin: datetime) -> int:
    """Une à deux tentatives refusées par jour ouvré ; celles du jour restent à traiter (anomalies)."""
    connues = {u for (u,) in db.query(TentativeRejetee.uuid)}
    crees, jour = 0, debut
    while jour <= fin.date():
        rng = random.Random(f"tentatives|{jour.isoformat()}")
        for i in range(rng.choice([1, 1, 2]) if jour.weekday() < 5 else 0):
            u = _uuid("tentative", jour, i)
            quand = datetime.combine(jour, datetime.min.time()) + timedelta(hours=7, minutes=rng.randint(0, 100))
            if u in connues or quand > fin:
                continue
            t = rng.choice(sorted(bornes, key=lambda b: b.code))
            motif = rng.choice(["VISAGE_INCONNU", "ECHEC_VIVACITE", "VISAGE_INCONNU", "CHANGEMENT_VISAGE"])
            db.add(TentativeRejetee(uuid=u, terminal_id=t.id, site_id=t.site_id, horodatage=quand, motif=motif,
                                    score=rng.uniform(0.1, 0.35) if motif == "VISAGE_INCONNU" else 0.7,
                                    matricule_suppose=None if motif == "VISAGE_INCONNU" else rng.choice(agents).matricule,
                                    traitee=jour < fin.date()))
            crees += 1
        jour += timedelta(days=1)
    return crees


def mettre_a_jour_bornes(db: Session, bornes: list[Terminal], fin: datetime) -> int:
    """Dernier contact = dernier pointage reçu ; un lot de synchronisation par borne active aujourd'hui."""
    debut_jour = datetime.combine(fin.date(), datetime.min.time())
    lots = 0
    for t in bornes:
        dernier = db.query(func.max(Pointage.recu_le)).filter(Pointage.terminal_id == t.id).scalar()
        if dernier and (t.dernier_contact is None or t.dernier_contact < dernier):
            t.dernier_contact = min(dernier, fin)
            t.version = t.version or "1.0.0"
        du_jour = (db.query(func.count(Pointage.id)).filter(Pointage.terminal_id == t.id, Pointage.recu_le >= debut_jour)
                   .scalar())
        if du_jour and not db.query(LotSynchronisation).filter(LotSynchronisation.terminal_id == t.id,
                                                              LotSynchronisation.date >= debut_jour).first():
            db.add(LotSynchronisation(terminal_id=t.id, date=t.dernier_contact or fin, recus=du_jour, doublons=0, rejetes=0))
            lots += 1
    return lots


def corriger_fuseau(db: Session) -> int:
    """Une seule fois : les événements mobiles d'avant le réglage du fuseau avaient une heure d'avance."""
    if db.query(JournalAudit).filter(JournalAudit.action == "CORRECTION_FUSEAU").first():
        return 0
    mobiles = [t.id for t in db.query(Terminal).filter(Terminal.type == TypeAppareil.MOBILE)]
    n = 0
    for p in db.query(Pointage).filter(Pointage.terminal_id.in_(mobiles), Pointage.recu_le < LIMITE_FUSEAU):
        p.horodatage -= timedelta(hours=1)
        p.recu_le -= timedelta(hours=1)
        n += 1
    for r in db.query(TentativeRejetee).filter(TentativeRejetee.terminal_id.in_(mobiles), TentativeRejetee.horodatage < LIMITE_FUSEAU):
        r.horodatage -= timedelta(hours=1)
        n += 1
    for d in db.query(DemandeEnrolement).filter(DemandeEnrolement.cree_le < LIMITE_FUSEAU):
        d.cree_le -= timedelta(hours=1)
        d.capture_le -= timedelta(hours=1)
        if d.traite_le and d.traite_le < LIMITE_FUSEAU:
            d.traite_le -= timedelta(hours=1)
        n += 1
    db.add(JournalAudit(acteur="systeme", action="CORRECTION_FUSEAU",
                        details=f"{n} événement(s) mobile(s) antérieurs au {LIMITE_FUSEAU:%d/%m/%Y %H:%M} recalés d'une heure"))
    return n


def actualiser(db: Session, fin: datetime | None = None, corriger: bool = False) -> dict:
    fin = (fin or maintenant()).replace(microsecond=0)
    debut = fin.date() - timedelta(days=JOURS)
    agents = agents_fictifs(db)
    bornes = db.query(Terminal).filter(Terminal.type == TypeAppareil.BORNE, Terminal.actif.is_(True)).all()
    bilan = {"agents_fictifs": len(agents), "pointages": 0, "tentatives": 0, "lots": 0, "fuseau": 0}
    if agents and bornes:
        bilan["pointages"] = completer_historique(db, agents, bornes, debut, fin)
        bilan["tentatives"] = ajouter_tentatives(db, agents, bornes, debut, fin)
        db.flush()
        bilan["lots"] = mettre_a_jour_bornes(db, bornes, fin)
    if corriger:
        bilan["fuseau"] = corriger_fuseau(db)
    db.add(JournalAudit(acteur="systeme", action="ACTUALISATION_DEMO",
                        details=f"{bilan['pointages']} pointage(s) et {bilan['tentatives']} tentative(s) de démonstration ajoutés"))
    db.commit()
    return bilan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corriger-fuseau", action="store_true",
                        help="recaler d'une heure les événements mobiles d'avant le réglage du fuseau (VPS d'EDM uniquement)")
    args = parser.parse_args()
    with SessionLocale() as session:
        b = actualiser(session, corriger=args.corriger_fuseau)
    print(f"Agents fictifs : {b['agents_fictifs']} · pointages ajoutés : {b['pointages']} · tentatives : {b['tentatives']}"
          f" · lots de synchronisation : {b['lots']} · événements mobiles recalés : {b['fuseau']}")
    print("Relancez la commande juste avant la présentation pour ajouter les pointages des dernières heures.")
