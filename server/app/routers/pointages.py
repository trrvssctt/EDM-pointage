"""Historique des pointages, tableau de bord, rapports et exports."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import literal, or_, select, union_all, func
from sqlalchemy.orm import Session, joinedload

from server.app.database import get_db
from server.app.models import (Agent, DemandeEnrolement, Pointage, Role, Site, StatutDemande, TentativeRejetee,
                               Terminal, TypeAppareil, Utilisateur)
from server.app.routers.organisation import organisation
from server.app.securite import auditer, exiger_droit, perimetre, utilisateur_courant
from server.app.services import exports
from server.app.services.presences import calculer_journees, synthese, total
from server.app.services.vues import confiance, etat_terminal

router = APIRouter(prefix="/api", tags=["Pointages, tableau de bord et rapports"])
consultation = exiger_droit("pointages.consulter")
rapports = exiger_droit("rapports.generer")

MOTIFS_FRAUDE = {"ECHEC_VIVACITE", "CHANGEMENT_VISAGE"}
LIBELLES_MOTIF = {
    "VISAGE_INCONNU": "Visage inconnu", "ECHEC_VIVACITE": "Fraude suspectée", "CHANGEMENT_VISAGE": "Fraude suspectée",
    "SITE_NON_AUTORISE": "Site non autorisé", "IDENTITE_CONTESTEE": "Identité contestée",
    "APPEL_SUPERVISEUR": "Appel superviseur",
}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre"]


def date_longue(d: date) -> str:
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"


def _bornes(date_debut: date | None, date_fin: date | None) -> tuple[date, date]:
    fin = date_fin or date.today()
    debut = date_debut or fin
    if debut > fin:
        raise HTTPException(400, "La date de début doit précéder la date de fin")
    if (fin - debut).days > 366:
        raise HTTPException(400, "Période limitée à un an")
    return debut, fin


def _intervalle(debut: date, fin: date) -> tuple[datetime, datetime]:
    return datetime.combine(debut, datetime.min.time()), datetime.combine(fin + timedelta(days=1), datetime.min.time())


def initiales(nom: str) -> str:
    morceaux = [m for m in nom.replace("-", " ").split() if m]
    return (morceaux[0][0] + (morceaux[-1][0] if len(morceaux) > 1 else "")).upper() if morceaux else "?"


# --- Historique unifié (pointages + tentatives refusées) ---------------------
def _requetes_historique(db: Session, u: Utilisateur, debut: date, fin: date, q: str, site_id, terminal_id,
                         service_id, type_: str, alerte: str):
    d0, d1 = _intervalle(debut, fin)
    sel_p = (select(literal("P").label("nature"), Pointage.id.label("id"), Pointage.horodatage.label("horodatage"))
             .join(Agent, Agent.id == Pointage.agent_id)
             .where(Pointage.horodatage >= d0, Pointage.horodatage < d1))
    sel_t = (select(literal("T").label("nature"), TentativeRejetee.id.label("id"),
                    TentativeRejetee.horodatage.label("horodatage"))
             .outerjoin(Agent, Agent.matricule == TentativeRejetee.matricule_suppose)
             .where(TentativeRejetee.horodatage >= d0, TentativeRejetee.horodatage < d1))
    if u.role == Role.RESPONSABLE:
        ids = [i for (i,) in perimetre(db.query(Agent.id), u)]
        sel_p = sel_p.where(Pointage.agent_id.in_(ids))
        cond = [Agent.id.in_(ids)] + ([TentativeRejetee.site_id == u.site_id] if u.site_id else [])
        sel_t = sel_t.where(or_(*cond))
    if q:
        motif = f"%{q.strip()}%"
        filtre = or_(Agent.matricule.ilike(motif), Agent.nom.ilike(motif), Agent.prenom.ilike(motif),
                     (Agent.prenom + " " + Agent.nom).ilike(motif))
        sel_p, sel_t = sel_p.where(filtre), sel_t.where(filtre)
    if site_id:
        sel_p, sel_t = sel_p.where(Pointage.site_id == site_id), sel_t.where(TentativeRejetee.site_id == site_id)
    if terminal_id:
        sel_p = sel_p.where(Pointage.terminal_id == terminal_id)
        sel_t = sel_t.where(TentativeRejetee.terminal_id == terminal_id)
    if service_id:
        sel_p, sel_t = sel_p.where(Agent.service_id == service_id), sel_t.where(Agent.service_id == service_id)
    if alerte == "HORS_RATTACHEMENT":
        sel_p = sel_p.where(Pointage.site_id != Agent.site_rattachement_id)
    elif alerte == "DIFFERE":
        sel_p, sel_t = sel_p.where(Pointage.hors_ligne.is_(True)), sel_t.where(TentativeRejetee.hors_ligne.is_(True))
    elif alerte == "FRAUDE":
        sel_t = sel_t.where(TentativeRejetee.motif.in_(MOTIFS_FRAUDE))
    elif alerte == "ANNULE":
        sel_p = sel_p.where(Pointage.annule.is_(True))
    selections = []
    if type_ in ("", "ENTREE", "SORTIE") and alerte != "FRAUDE":
        selections.append(sel_p.where(Pointage.type == type_) if type_ else sel_p)
    if type_ in ("", "REFUSE") and alerte not in ("HORS_RATTACHEMENT", "ANNULE"):
        selections.append(sel_t)
    return selections


def _ligne_pointage(p: Pointage) -> dict:
    hors = p.site_id != p.agent.site_rattachement_id
    return {
        "id": f"P{p.id}", "nature": "POINTAGE", "horodatage": p.horodatage, "agent": p.agent.nom_complet,
        "initiales": initiales(p.agent.nom_complet), "matricule": p.matricule, "service": p.agent.service.nom,
        "site": p.site.libelle_court, "site_rattachement": p.agent.site_rattachement.libelle_court,
        "terminal": p.terminal.code, "type": p.type.value,
        "alerte": "ANNULE" if p.annule else ("HORS_RATTACHEMENT" if hors else None),
        "libelle_alerte": "Annulé par l'agent" if p.annule else ("Hors rattachement" if hors else None),
        "synchro": "DIFFERE" if p.hors_ligne else "SYNCHRONISE", "confiance": confiance(p.score),
        "secours": p.secours, "recu_le": p.recu_le}


def _ligne_tentative(t: TentativeRejetee, agents: dict[str, Agent]) -> dict:
    a = agents.get(t.matricule_suppose or "")
    nom = a.nom_complet if a and t.motif != "VISAGE_INCONNU" else "Visage inconnu"
    return {
        "id": f"T{t.id}", "nature": "REFUS", "horodatage": t.horodatage, "agent": nom,
        "initiales": initiales(nom) if a else "?", "matricule": t.matricule_suppose, "service": a.service.nom if a else "",
        "site": t.site.libelle_court, "site_rattachement": a.site_rattachement.libelle_court if a else "",
        "terminal": t.terminal.code, "type": "REFUSE", "motif": t.motif,
        "alerte": "FRAUDE" if t.motif in MOTIFS_FRAUDE else t.motif,
        "libelle_alerte": LIBELLES_MOTIF.get(t.motif, t.motif), "traitee": t.traitee,
        "synchro": "DIFFERE" if t.hors_ligne else "SYNCHRONISE", "confiance": None, "recu_le": None}


def _historique(db: Session, u: Utilisateur, debut, fin, q, site_id, terminal_id, service_id, type_, alerte,
                page: int, taille: int) -> tuple[int, list[dict]]:
    selections = _requetes_historique(db, u, debut, fin, q, site_id, terminal_id, service_id, type_, alerte)
    if not selections:
        return 0, []
    union = union_all(*selections).subquery()
    total_lignes = db.execute(select(func.count()).select_from(union)).scalar_one()
    rangs = db.execute(select(union.c.nature, union.c.id).order_by(union.c.horodatage.desc(), union.c.id.desc())
                       .offset((page - 1) * taille).limit(taille)).all()
    ids_p = [i for n, i in rangs if n == "P"]
    ids_t = [i for n, i in rangs if n == "T"]
    pointages = {p.id: p for p in db.query(Pointage).options(
        joinedload(Pointage.agent).joinedload(Agent.service), joinedload(Pointage.agent).joinedload(Agent.site_rattachement),
        joinedload(Pointage.site), joinedload(Pointage.terminal)).filter(Pointage.id.in_(ids_p))} if ids_p else {}
    tentatives = {t.id: t for t in db.query(TentativeRejetee).options(
        joinedload(TentativeRejetee.site), joinedload(TentativeRejetee.terminal))
        .filter(TentativeRejetee.id.in_(ids_t))} if ids_t else {}
    matricules = {t.matricule_suppose for t in tentatives.values() if t.matricule_suppose}
    agents = {a.matricule: a for a in db.query(Agent).options(joinedload(Agent.service), joinedload(
        Agent.site_rattachement)).filter(Agent.matricule.in_(matricules))} if matricules else {}
    lignes = [_ligne_pointage(pointages[i]) if n == "P" else _ligne_tentative(tentatives[i], agents) for n, i in rangs]
    return total_lignes, lignes


@router.get("/pointages")
def historique(date_debut: date | None = None, date_fin: date | None = None, q: str = "",
               site_id: int | None = None, terminal_id: int | None = None, service_id: int | None = None,
               type: str = Query("", pattern="^(|ENTREE|SORTIE|REFUSE)$"),
               alerte: str = Query("", pattern="^(|HORS_RATTACHEMENT|DIFFERE|FRAUDE|ANNULE)$"),
               page: int = Query(1, ge=1), taille: int = Query(25, ge=1, le=500),
               u: Utilisateur = Depends(consultation), db: Session = Depends(get_db)):
    debut, fin = _bornes(date_debut, date_fin)
    nb, lignes = _historique(db, u, debut, fin, q, site_id, terminal_id, service_id, type, alerte, page, taille)
    return {"total": nb, "elements": lignes}


@router.get("/pointages/export.xlsx")
def exporter_historique(request: Request, date_debut: date | None = None, date_fin: date | None = None, q: str = "",
                        site_id: int | None = None, terminal_id: int | None = None, service_id: int | None = None,
                        type: str = "", alerte: str = "", u: Utilisateur = Depends(consultation),
                        db: Session = Depends(get_db)):
    debut, fin = _bornes(date_debut, date_fin)
    _, lignes = _historique(db, u, debut, fin, q, site_id, terminal_id, service_id, type, alerte, 1, 100_000)
    feuille = exports.Feuille("Pointages", ["Date", "Heure", "Agent", "Matricule", "Service", "Site de pointage",
                                            "Site de rattachement", "Terminal", "Type", "Alerte", "Synchro",
                                            "Confiance (%)"],
                              [[l["horodatage"].strftime("%d/%m/%Y"), l["horodatage"].strftime("%H:%M:%S"), l["agent"],
                                l["matricule"] or "", l["service"], l["site"], l["site_rattachement"], l["terminal"],
                                {"ENTREE": "Entrée", "SORTIE": "Sortie", "REFUSE": "Refusé"}[l["type"]],
                                l["libelle_alerte"] or "", "Différé · hors ligne" if l["synchro"] == "DIFFERE"
                                else "Synchronisé", l["confiance"] if l["confiance"] is not None else ""]
                               for l in lignes])
    auditer(db, u.identifiant, "EXPORT_POINTAGES", f"{debut} → {fin}, {len(lignes)} lignes", request)
    db.commit()
    contenu = exports.excel(organisation(db), "Historique des pointages", _periode(debut, fin), [feuille])
    return _fichier(contenu, f"pointages_{debut}_{fin}.xlsx")


@router.post("/tentatives/{tentative_id}/traiter")
def traiter_tentative(tentative_id: int, request: Request, u: Utilisateur = Depends(consultation),
                      db: Session = Depends(get_db)):
    t = db.get(TentativeRejetee, tentative_id)
    if t is None:
        raise HTTPException(404, "Tentative introuvable")
    t.traitee = True
    auditer(db, u.identifiant, "TENTATIVE_TRAITEE", f"{t.motif} {t.terminal.code} {t.horodatage}", request)
    db.commit()
    return {"message": "Tentative marquée comme traitée"}


# --- Tableau de bord ---------------------------------------------------------
def _agents_perimetre(db: Session, u: Utilisateur, service_id=None, site_id=None, matricule=""):
    requete = perimetre(db.query(Agent), u).filter(Agent.actif.is_(True)).options(
        joinedload(Agent.horaire), joinedload(Agent.service), joinedload(Agent.site_rattachement))
    if service_id:
        requete = requete.filter(Agent.service_id == service_id)
    if site_id:
        requete = requete.filter(Agent.site_rattachement_id == site_id)
    if matricule:
        requete = requete.filter(Agent.matricule == matricule.strip().upper())
    return requete.order_by(Agent.nom).all()


def _pct(n: int, d: int) -> float:
    return round(100 * n / d, 1) if d else 0.0


@router.get("/tableau-de-bord")
def tableau_de_bord(jour: date | None = None, u: Utilisateur = Depends(consultation), db: Session = Depends(get_db)):
    jour = jour or date.today()
    agents = _agents_perimetre(db, u)
    journees = calculer_journees(db, jour, jour, agents)
    statuts = Counter(j.statut for j in journees)
    attendus = len(journees)
    presents = statuts["PRESENT"] + statuts["RETARD"]
    terminaux = db.query(Terminal).options(joinedload(Terminal.site)).order_by(Terminal.code).all()
    en_attente = [t for t in terminaux if t.actif and t.nb_en_attente]

    # Présence par site de rattachement
    par_site: dict[str, list[int]] = {}
    for j in journees:
        c = par_site.setdefault(j.site_rattachement, [0, 0])
        c[1] += 1
        c[0] += j.statut != "ABSENT"
    presence_sites = sorted(({"site": s, "presents": p, "attendus": a, "taux": _pct(p, a)}
                             for s, (p, a) in par_site.items()), key=lambda x: -x["attendus"])

    # Sept derniers jours
    debut_semaine = jour - timedelta(days=6)
    semaine = calculer_journees(db, debut_semaine, jour, agents)
    evolution = []
    for i in range(7):
        d = debut_semaine + timedelta(days=i)
        evolution.append({"date": d.isoformat(), "presents": sum(1 for j in semaine if j.date == d
                                                                 and j.statut != "ABSENT"),
                          "week_end": d.weekday() >= 5})

    # Anomalies à traiter
    anomalies = []
    d0, d1 = _intervalle(jour, jour)
    for t in (db.query(TentativeRejetee).options(joinedload(TentativeRejetee.terminal))
              .filter(TentativeRejetee.horodatage >= d0, TentativeRejetee.horodatage < d1,
                      TentativeRejetee.motif.in_(MOTIFS_FRAUDE | {"APPEL_SUPERVISEUR"}),
                      TentativeRejetee.traitee.is_(False))
              .order_by(TentativeRejetee.horodatage.desc()).limit(3)):
        fraude = t.motif in MOTIFS_FRAUDE
        anomalies.append({"type": "FRAUDE" if fraude else "SUPERVISEUR", "id": t.id,
                          "titre": "Tentative de fraude suspectée" if fraude else "Appel du superviseur",
                          "detail": f"{t.terminal.code} · {t.horodatage:%H:%M} · "
                                    + ("photo ou écran détecté" if fraude else "assistance demandée sur le terminal"),
                          "lien": {"page": "pointages", "alerte": "FRAUDE", "date": jour.isoformat()}})
    veille = jour - timedelta(days=1)
    sans_sortie = [j for j in calculer_journees(db, veille, veille, agents) if "Entrée sans sortie" in j.anomalies]
    if sans_sortie:
        anomalies.append({"type": "SANS_SORTIE", "titre": "Entrée sans sortie",
                          "detail": f"{len(sans_sortie)} agent{'s' if len(sans_sortie) > 1 else ''} · journée du "
                                    f"{veille.day} {MOIS[veille.month - 1]}",
                          "lien": {"page": "rapports", "date": veille.isoformat()}})
    for t in terminaux:
        if etat_terminal(t) == "HORS_LIGNE" and t.type == TypeAppareil.BORNE:
            depuis = t.dernier_contact.strftime("%H:%M") if t.dernier_contact.date() == jour else \
                t.dernier_contact.strftime("%d/%m %H:%M")
            anomalies.append({"type": "TERMINAL", "titre": "Terminal hors ligne",
                              "detail": f"{t.code} · depuis {depuis} · {t.nb_en_attente} pointages en attente",
                              "lien": {"page": "sites", "terminal": t.id}})
    hors = {j.matricule for j in journees if "Pointage hors site de rattachement" in j.anomalies}
    if hors:
        anomalies.append({"type": "HORS_RATTACHEMENT", "titre": "Pointages hors rattachement",
                          "detail": f"{len(hors)} agent{'s' if len(hors) > 1 else ''} ce jour · autorisés",
                          "lien": {"page": "pointages", "alerte": "HORS_RATTACHEMENT", "date": jour.isoformat()}})
    if u.role != Role.RESPONSABLE:
        a_valider = db.query(DemandeEnrolement).filter(DemandeEnrolement.statut == StatutDemande.GABARIT_CALCULE).count()
        if a_valider:
            anomalies.append({"type": "ENROLEMENT", "titre": "Enrôlements à valider",
                              "detail": f"{a_valider} demande{'s' if a_valider > 1 else ''} envoyée{'s' if a_valider > 1 else ''} "
                                        "depuis l'application mobile",
                              "lien": {"page": "enrolement", "onglet": "validation"}})
    if u.role == Role.ADMIN:
        demandes = db.query(Utilisateur).filter(Utilisateur.reinitialisation_demandee.is_(True)).count()
        if demandes:
            anomalies.append({"type": "MOT_DE_PASSE", "titre": "Mot de passe oublié",
                              "detail": f"{demandes} demande{'s' if demandes > 1 else ''} de réinitialisation",
                              "lien": {"page": "utilisateurs"}})

    return {
        "date": jour.isoformat(), "date_longue": date_longue(jour),
        "attendus": attendus, "presents": presents, "taux_presence": _pct(presents, attendus),
        "retards": statuts["RETARD"], "taux_retard": _pct(statuts["RETARD"], attendus),
        "absences": statuts["ABSENT"], "taux_absence": _pct(statuts["ABSENT"], attendus),
        "en_attente": sum(t.nb_en_attente for t in en_attente), "terminaux_en_attente": len(en_attente),
        "presence_par_site": presence_sites, "evolution": evolution, "anomalies": anomalies,
        "terminaux": [{"id": t.id, "code": t.code, "site": t.site.libelle_court, "etat": etat_terminal(t),
                       "en_attente": t.nb_en_attente, "type": t.type.value} for t in terminaux],
    }


@router.get("/tableau-de-bord/export.xlsx")
def exporter_journee(request: Request, jour: date | None = None, u: Utilisateur = Depends(consultation),
                     db: Session = Depends(get_db)):
    """« Exporter la journée » : présences de chaque agent et liste des pointages."""
    jour = jour or date.today()
    journees = calculer_journees(db, jour, jour, _agents_perimetre(db, u))
    _, lignes = _historique(db, u, jour, jour, "", None, None, None, "", "", 1, 100_000)
    presences = exports.Feuille("Présences", ["Matricule", "Agent", "Service", "Site de rattachement", "Statut",
                                              "Arrivée", "Départ", "Retard (min)", "Sites de pointage", "Anomalies"],
                                [[j.matricule, j.agent, j.service, j.site_rattachement, _statut(j.statut),
                                  j.premiere_entree or "", j.derniere_sortie or "", j.retard_minutes or "",
                                  ", ".join(j.sites), " · ".join(j.anomalies)] for j in journees])
    pointages = exports.Feuille("Pointages", ["Heure", "Agent", "Matricule", "Site", "Terminal", "Type", "Alerte",
                                              "Synchro"],
                                [[l["horodatage"].strftime("%H:%M:%S"), l["agent"], l["matricule"] or "", l["site"],
                                  l["terminal"], l["type"], l["libelle_alerte"] or "", l["synchro"]] for l in lignes])
    auditer(db, u.identifiant, "EXPORT_JOURNEE", jour.isoformat(), request)
    db.commit()
    contenu = exports.excel(organisation(db), f"Journée du {date_longue(jour)}", "Présences et pointages",
                            [presences, pointages])
    return _fichier(contenu, f"journee_{jour}.xlsx")


# --- Rapports ----------------------------------------------------------------
REGROUPEMENTS = {"service": ("service", "Service"), "site": ("site_rattachement", "Site de rattachement"),
                 "agent": ("matricule", "Agent")}


def _statut(s: str) -> str:
    return {"PRESENT": "Présent", "RETARD": "En retard", "ABSENT": "Absent"}.get(s, s)


def _periode(debut: date, fin: date) -> str:
    return f"Journée du {date_longue(debut)}" if debut == fin else \
        f"Du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}"


def _rapport(db, u, type_rapport, date_debut, date_fin, site_id, service_id, regroupement, matricule):
    debut, fin = _bornes(date_debut, date_fin)
    journees = calculer_journees(db, debut, fin, _agents_perimetre(db, u, service_id, site_id, matricule))
    cle, _ = REGROUPEMENTS[regroupement]
    lignes = synthese(journees, cle)
    tot = total(lignes)
    if type_rapport == "retards":
        detail = [j.dict() for j in journees if j.statut == "RETARD"]
    elif type_rapport == "absences":
        detail = [j.dict() for j in journees if j.statut == "ABSENT"]
    else:
        detail = [j.dict() for j in journees]
    site = db.get(Site, site_id).libelle_court if site_id else "Tous les sites"
    return {"titre": {"presence": "Rapport de présence", "retards": "Rapport des retards",
                      "absences": "Rapport des absences"}[type_rapport],
            "periode": _periode(debut, fin), "perimetre": f"{site} · regroupé par {REGROUPEMENTS[regroupement][1].lower()}",
            "debut": debut.isoformat(), "fin": fin.isoformat(), "regroupement": regroupement,
            "indicateurs": {"taux_presence": tot["taux_presence"], "retards": tot["retards"],
                            "absences": tot["absences"], "minutes_retard": tot["minutes_retard"]},
            "lignes": lignes, "total": tot, "detail": detail}


def _parametres_rapport(type_rapport: str = Query("presence", pattern="^(presence|retards|absences)$"),
                        date_debut: date | None = None, date_fin: date | None = None, site_id: int | None = None,
                        service_id: int | None = None,
                        regroupement: str = Query("service", pattern="^(service|site|agent)$"), matricule: str = ""):
    return dict(type_rapport=type_rapport, date_debut=date_debut, date_fin=date_fin, site_id=site_id,
                service_id=service_id, regroupement=regroupement, matricule=matricule)


@router.get("/rapports")
def rapport(p: dict = Depends(_parametres_rapport), u: Utilisateur = Depends(rapports), db: Session = Depends(get_db)):
    return _rapport(db, u, **p)


def _feuille_rapport(r: dict) -> exports.Feuille:
    """Synthèse regroupée (service, site ou agent) avec ligne de total."""
    _, titre_groupe = REGROUPEMENTS[r["regroupement"]]
    lignes = [[(f"{l['agent']} ({l['matricule']})" if r["regroupement"] == "agent" else l["cle"]), l["effectif"],
               l["jours_ouvres"], l["presences"], l["retards"], l["minutes_retard"], l["absences"],
               l["heures_travaillees"], f"{l['taux_presence']} %"] for l in r["lignes"]]
    t = r["total"]
    return exports.Feuille("Synthèse", [titre_groupe, "Effectif", "Jours attendus", "Présences", "Dont retards",
                                        "Cumul retard (min)", "Absences", "Heures travaillées", "Taux de présence"],
                           lignes, ["Total", t["effectif"], t["jours_ouvres"], t["presences"], t["retards"],
                                    t["minutes_retard"], t["absences"], t["heures_travaillees"],
                                    f"{t['taux_presence']} %"])


def _feuille_detail(r: dict) -> exports.Feuille:
    return exports.Feuille("Détail journalier", ["Date", "Matricule", "Agent", "Service", "Site de rattachement",
                                                 "Statut", "Arrivée", "Départ", "Retard (min)", "Durée (h)",
                                                 "Sites de pointage", "Anomalies"],
                           [[j["date"], j["matricule"], j["agent"], j["service"], j["site_rattachement"],
                             _statut(j["statut"]), j["premiere_entree"] or "", j["derniere_sortie"] or "",
                             j["retard_minutes"] or "", round(j["duree_minutes"] / 60, 2) if j["duree_minutes"] else "",
                             ", ".join(j["sites"]), " · ".join(j["anomalies"])] for j in r["detail"]])


def _fichier(contenu: bytes, nom: str) -> Response:
    types = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "pdf": "application/pdf"}
    return Response(contenu, media_type=types[nom.rsplit(".", 1)[1]],
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})


@router.get("/rapports/export.xlsx")
def rapport_excel(request: Request, p: dict = Depends(_parametres_rapport), u: Utilisateur = Depends(rapports),
                  db: Session = Depends(get_db)):
    r = _rapport(db, u, **p)
    auditer(db, u.identifiant, "EXPORT_RAPPORT", f"{r['titre']} Excel {r['debut']} → {r['fin']}", request)
    db.commit()
    contenu = exports.excel(organisation(db), r["titre"], f"{r['periode']} · {r['perimetre']}",
                            [_feuille_rapport(r), _feuille_detail(r)])
    return _fichier(contenu, f"{p['type_rapport']}_{r['debut']}_{r['fin']}.xlsx")


@router.get("/rapports/export.pdf")
def rapport_pdf(request: Request, p: dict = Depends(_parametres_rapport), u: Utilisateur = Depends(rapports),
                db: Session = Depends(get_db)):
    r = _rapport(db, u, **p)
    auditer(db, u.identifiant, "EXPORT_RAPPORT", f"{r['titre']} PDF {r['debut']} → {r['fin']}", request)
    db.commit()
    i = r["indicateurs"]
    indicateurs = [("Taux de présence", f"{i['taux_presence']} %".replace(".", ",")), ("Retards", str(i["retards"])),
                   ("Absences", str(i["absences"])), ("Cumul des retards", f"{i['minutes_retard']} min")]
    feuille = _feuille_rapport(r)
    if p["type_rapport"] != "presence" and p["regroupement"] != "agent":
        details = r["detail"][:400]
        feuille = exports.Feuille("Détail", ["Date", "Agent", "Matricule", "Service", "Site de rattachement",
                                             "Arrivée" if p["type_rapport"] == "retards" else "Statut",
                                             "Retard (min)" if p["type_rapport"] == "retards" else "Anomalies"],
                                  [[j["date"], j["agent"], j["matricule"], j["service"], j["site_rattachement"],
                                    j["premiere_entree"] if p["type_rapport"] == "retards" else "Absent",
                                    j["retard_minutes"] if p["type_rapport"] == "retards" else ""]
                                   for j in details])
    contenu = exports.pdf(organisation(db), f"{r['titre']} · {r['periode']}", r["perimetre"], indicateurs, feuille)
    return _fichier(contenu, f"{p['type_rapport']}_{r['debut']}_{r['fin']}.pdf")
