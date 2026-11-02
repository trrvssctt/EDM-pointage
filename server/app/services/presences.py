"""Calcul des présences, retards, absences et anomalies à partir des pointages."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from server.app.models import Agent, Pointage, TypePointage


@dataclass
class JourneeAgent:
    date: date
    matricule: str
    agent: str
    service: str
    site_rattachement: str
    statut: str = "ABSENT"               # PRESENT | RETARD | ABSENT
    premiere_entree: str | None = None
    derniere_sortie: str | None = None
    retard_minutes: int = 0
    duree_minutes: int = 0
    sites: list[str] = field(default_factory=list)
    nb_pointages: int = 0
    anomalies: list[str] = field(default_factory=list)

    def dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        return d


def _jours(debut: date, fin: date):
    j = debut
    while j <= fin:
        yield j
        j += timedelta(days=1)


def calculer_journees(db: Session, debut: date, fin: date, agents: list[Agent]) -> list[JourneeAgent]:
    fin = min(fin, date.today())
    if fin < debut or not agents:
        return []
    ids = [a.id for a in agents]
    pointages = (
        db.query(Pointage).options(joinedload(Pointage.site))
        .filter(Pointage.agent_id.in_(ids), Pointage.annule.is_(False),
                Pointage.horodatage >= datetime.combine(debut, datetime.min.time()),
                Pointage.horodatage < datetime.combine(fin + timedelta(days=1), datetime.min.time()))
        .order_by(Pointage.horodatage).all()
    )
    par_jour: dict[tuple[int, date], list[Pointage]] = defaultdict(list)
    for p in pointages:
        par_jour[(p.agent_id, p.horodatage.date())].append(p)

    resultats = []
    maintenant = datetime.now()
    for agent in agents:
        horaire = agent.horaire
        jours_travailles = horaire.jours()
        for jour in _jours(max(debut, agent.cree_le.date()), fin):
            evenements = par_jour.get((agent.id, jour), [])
            if jour.weekday() not in jours_travailles and not evenements:
                continue
            j = JourneeAgent(jour, agent.matricule, agent.nom_complet, agent.service.nom,
                             agent.site_rattachement.libelle_court)
            debut_prevu = datetime.combine(jour, horaire.heure_debut)
            fin_prevue = datetime.combine(jour, horaire.heure_fin)
            if not evenements:
                if jour == maintenant.date() and maintenant < debut_prevu + timedelta(minutes=horaire.tolerance_minutes):
                    continue  # la journée n'a pas encore commencé
                resultats.append(j)
                continue

            j.nb_pointages = len(evenements)
            j.sites = sorted({p.site.libelle_court for p in evenements})
            entrees = [p for p in evenements if p.type == TypePointage.ENTREE]
            sorties = [p for p in evenements if p.type == TypePointage.SORTIE]
            if entrees:
                premiere = entrees[0].horodatage
                j.premiere_entree = premiere.strftime("%H:%M:%S")
                retard = (premiere - debut_prevu).total_seconds() / 60
                if retard > horaire.tolerance_minutes:
                    j.retard_minutes = int(retard)
            else:
                j.anomalies.append("Sortie sans entrée")
            if sorties:
                derniere = sorties[-1].horodatage
                j.derniere_sortie = derniere.strftime("%H:%M:%S")
                if derniere < fin_prevue and (entrees and derniere > entrees[0].horodatage):
                    j.anomalies.append("Départ anticipé")
            elif jour < maintenant.date() or maintenant > fin_prevue:
                j.anomalies.append("Entrée sans sortie")

            # Durée de présence : somme des intervalles ENTREE -> SORTIE
            debut_intervalle = None
            for p in evenements:
                if p.type == TypePointage.ENTREE and debut_intervalle is None:
                    debut_intervalle = p.horodatage
                elif p.type == TypePointage.SORTIE and debut_intervalle is not None:
                    j.duree_minutes += int((p.horodatage - debut_intervalle).total_seconds() / 60)
                    debut_intervalle = None

            if any(p.site_id != agent.site_rattachement_id for p in evenements):
                j.anomalies.append("Pointage hors site de rattachement")
            if jour.weekday() not in jours_travailles:
                j.anomalies.append("Pointage un jour non travaillé")
            j.statut = "RETARD" if j.retard_minutes else "PRESENT"
            resultats.append(j)
    resultats.sort(key=lambda r: (r.date, r.matricule))
    return resultats


def synthese(journees: list[JourneeAgent], cle: str) -> list[dict]:
    """Agrégation par 'matricule', 'service' ou 'site_rattachement'."""
    groupes: dict[str, dict] = {}
    agents: dict[str, set] = {}
    for j in journees:
        k = getattr(j, cle)
        agents.setdefault(k, set()).add(j.matricule)
        g = groupes.setdefault(k, {"cle": k, cle: k, "jours_ouvres": 0, "presences": 0, "retards": 0,
                                   "absences": 0, "minutes_retard": 0, "heures_travaillees": 0.0, "anomalies": 0})
        if cle == "matricule":
            g["agent"] = j.agent
            g["service"] = j.service
        g["jours_ouvres"] += 1
        if j.statut == "ABSENT":
            g["absences"] += 1
        else:
            g["presences"] += 1
        if j.statut == "RETARD":
            g["retards"] += 1
            g["minutes_retard"] += j.retard_minutes
        g["heures_travaillees"] = round(g["heures_travaillees"] + j.duree_minutes / 60, 2)
        g["anomalies"] += len(j.anomalies)
    for k, g in groupes.items():
        g["effectif"] = len(agents[k])
        g["taux_presence"] = round(100 * g["presences"] / g["jours_ouvres"], 1) if g["jours_ouvres"] else 0.0
    return sorted(groupes.values(), key=lambda g: str(g[cle]))


def total(lignes: list[dict]) -> dict:
    t = {k: sum(l[k] for l in lignes) for k in ("effectif", "jours_ouvres", "presences", "retards", "absences",
                                                 "minutes_retard", "anomalies")}
    t["heures_travaillees"] = round(sum(l["heures_travaillees"] for l in lignes), 2)
    t["taux_presence"] = round(100 * t["presences"] / t["jours_ouvres"], 1) if t["jours_ouvres"] else 0.0
    return t
