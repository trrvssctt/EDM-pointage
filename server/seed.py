"""Initialisation de la base : organisation, référentiels, comptes, terminaux et données de démonstration.

Usage : python -m server.seed [--demo] [--reinitialiser]
"""
import argparse
import json
import os
import random
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np

from server.app.database import Base, SessionLocale, engine, initialiser_base
from server.app.models import (Agent, GabaritFacial, Horaire, LotSynchronisation, Organisation, Pointage, Role,
                               Service, Site, TentativeRejetee, Terminal, TypeAppareil, TypePointage, TypeSite,
                               Utilisateur)
from server.app.securite import chiffrer_gabarit, empreinte_cle, generer_cle_terminal, hacher_mot_de_passe

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CONFIG_TERMINAUX = RACINE / "terminal" / "config"
LOGO = RACINE / "server" / "ressources" / "logo-edm.png"
# Adresse publique du serveur, inscrite dans la configuration des terminaux générée ici.
URL_SERVEUR = os.environ.get("EDM_URL_PUBLIQUE", "http://127.0.0.1:8000")

SERVICES = [("DIST", "Distribution"), ("PROD", "Production"), ("MAINT", "Maintenance"), ("COM", "Commercial"),
            ("FRH", "Finances et RH"), ("RESX", "Réseau et exploitation")]
SITES = [  # code, nom, nom court, type, ville
    ("BKO-SIEGE", "Siège social · Bamako", "Siège · Bamako", TypeSite.SIEGE, "Bamako"),
    ("DR-SIK", "Direction régionale de Sikasso", "DR Sikasso", TypeSite.DIRECTION_REGIONALE, "Sikasso"),
    ("DR-KYS", "Direction régionale de Kayes", "DR Kayes", TypeSite.DIRECTION_REGIONALE, "Kayes"),
    ("CT-SEL", "Centrale de Sélingué", "Centrale de Sélingué", TypeSite.CENTRALE, "Sélingué"),
    ("AG-BDL", "Agence Badalabougou", "Agence Badalabougou", TypeSite.AGENCE, "Bamako"),
    ("ST-SOT", "Centre technique · Sotuba", "Centre technique Sotuba", TypeSite.SERVICE_TECHNIQUE, "Bamako"),
]
HORAIRES = [("Administratif 07h30 – 16h00", time(7, 30), time(16, 0), 10, "0,1,2,3,4"),
            ("Quart technique 06h00 – 14h00", time(6, 0), time(14, 0), 5, "0,1,2,3,4,5")]
# identifiant, e-mail, nom, fonction, mot de passe, rôle, service, site, actif
UTILISATEURS = [
    ("admin", "b.haidara@edm.example", "Boubacar Haïdara", "Administrateur système", "Admin@2026", Role.ADMIN,
     None, None, True),
    ("drh", "f.maiga@edm.example", "Fanta Maïga", "Direction des RH", "Drh@2026", Role.DRH, None, None, True),
    ("s.bagayoko", "s.bagayoko@edm.example", "Souleymane Bagayoko", "Direction des RH", "Drh@2026", Role.DRH,
     None, None, True),
    ("resp.sikasso", "m.cisse@edm.example", "Mariam Cissé", "Cheffe de la DR Sikasso", "Resp@2026",
     Role.RESPONSABLE, None, "DR-SIK", True),
    ("resp.sotuba", "d.sacko@edm.example", "Drissa Sacko", "Chef du service maintenance", "Resp@2026",
     Role.RESPONSABLE, "MAINT", "ST-SOT", True),
    ("a.samake", "a.samake@edm.example", "Adama Samaké", "Chef d'agence", "Resp@2026", Role.RESPONSABLE,
     None, "AG-BDL", False),
]
# Terminaux : code, emplacement, site. Un fichier de configuration est généré pour chacun.
TERMINAUX = [("TRM-BKO-03", "Hall d'accueil du siège", "BKO-SIEGE"), ("TRM-BKO-04", "Entrée parking du siège", "BKO-SIEGE"),
             ("TRM-SIK-01", "Accueil DR Sikasso", "DR-SIK"), ("TRM-SIK-02", "Atelier DR Sikasso", "DR-SIK"),
             ("TRM-KYS-01", "Accueil DR Kayes", "DR-KYS"), ("TRM-KYS-02", "Magasin DR Kayes", "DR-KYS"),
             ("TRM-SEL-01", "Poste de garde de la centrale", "CT-SEL"), ("TRM-BDL-01", "Agence Badalabougou", "AG-BDL"),
             ("TRM-SOT-01", "Entrée du centre technique", "ST-SOT")]
# Téléphones de l'application terrain (enrôlement, pointage de secours)
MOBILES = [("MOB-BKO-07", "iPhone de l'équipe RH du siège", "BKO-SIEGE")]

# Agents visibles dans les maquettes : matricule, prénom, nom, fonction, service, site, horaire, enrôlé, actif
AGENTS_MAQUETTE = [
    ("EDM-004217", "Mamadou", "Traoré", "Technicien distribution", "DIST", "DR-SIK", 0, True, True),
    ("EDM-001864", "Aïssata", "Keïta", "Comptable principale", "FRH", "BKO-SIEGE", 0, True, True),
    ("EDM-007301", "Moussa", "Coulibaly", "Opérateur de conduite", "PROD", "CT-SEL", 1, True, True),
    ("EDM-003092", "Fatoumata", "Diarra", "Conseillère clientèle", "COM", "AG-BDL", 0, True, True),
    ("EDM-005578", "Oumar", "Sangaré", "Électromécanicien", "MAINT", "ST-SOT", 1, False, True),
    ("EDM-002446", "Kadiatou", "Sidibé", "Gestionnaire paie", "FRH", "BKO-SIEGE", 0, True, True),
    ("EDM-008115", "Seydou", "Konaté", "Chef de quart réseau", "RESX", "DR-KYS", 1, True, False),
    ("EDM-009023", "Awa", "Doumbia", "Chargée commerciale", "COM", "DR-KYS", 0, False, True),
    ("EDM-006712", "Ibrahim", "Camara", "Technicien de maintenance", "MAINT", "ST-SOT", 1, True, True),
    ("EDM-007744", "Bakary", "Dembélé", "Opérateur de conduite", "PROD", "CT-SEL", 1, True, True),
]
PRENOMS = ["Adama", "Alou", "Aminata", "Assitan", "Bintou", "Boubacar", "Cheick", "Daouda", "Djeneba", "Fanta",
           "Hawa", "Issa", "Kadidia", "Lassana", "Mahamadou", "Mariam", "Modibo", "Nana", "Oumou", "Rokia",
           "Salif", "Sekou", "Sira", "Souleymane", "Tiémoko", "Youssouf", "Zoumana", "Habib", "Korotoumou", "Yaya"]
NOMS = ["Bagayoko", "Ballo", "Berthé", "Cissé", "Coulibaly", "Dembélé", "Diakité", "Diallo", "Diarra", "Doumbia",
        "Fofana", "Guindo", "Haïdara", "Kanté", "Keïta", "Koné", "Maïga", "Samaké", "Sangaré", "Sidibé", "Sissoko",
        "Sow", "Tangara", "Touré", "Traoré", "Togola"]
FONCTIONS = {"DIST": "Agent de distribution", "PROD": "Opérateur de production", "MAINT": "Technicien de maintenance",
             "COM": "Agent commercial", "FRH": "Assistant administratif", "RESX": "Technicien réseau"}
SERVICES_PAR_SITE = {"BKO-SIEGE": ["FRH", "COM", "RESX", "DIST"], "DR-SIK": ["DIST", "RESX", "COM", "FRH"],
                     "DR-KYS": ["DIST", "RESX", "COM"], "CT-SEL": ["PROD", "MAINT"], "AG-BDL": ["COM", "DIST"],
                     "ST-SOT": ["MAINT", "RESX"]}
EFFECTIF_DEMO = {"BKO-SIEGE": 22, "DR-SIK": 12, "DR-KYS": 10, "CT-SEL": 9, "AG-BDL": 6, "ST-SOT": 8}


def gabarit_fictif(rng: np.random.Generator) -> bytes:
    """Vecteur aléatoire normalisé : ne correspond à aucun visage réel (données de démonstration)."""
    v = rng.normal(size=128).astype(np.float32)
    return chiffrer_gabarit(v / np.linalg.norm(v))


def creer_referentiels(db):
    org = Organisation()
    if LOGO.exists():
        org.logo, org.logo_type = LOGO.read_bytes(), "image/png"
    db.add(org)
    services = {c: Service(code=c, nom=n) for c, n in SERVICES}
    sites = {c: Site(code=c, nom=n, nom_court=nc, type=t, ville=v) for c, n, nc, t, v in SITES}
    horaires = [Horaire(nom=n, heure_debut=d, heure_fin=f, tolerance_minutes=tol, jours_travailles=j)
                for n, d, f, tol, j in HORAIRES]
    db.add_all([*services.values(), *sites.values(), *horaires])
    db.flush()
    for ident, email, nom, fonction, mdp, role, service, site, actif in UTILISATEURS:
        db.add(Utilisateur(identifiant=ident, email=email, nom_complet=nom, fonction=fonction,
                           mot_de_passe_hash=hacher_mot_de_passe(mdp), role=role, actif=actif,
                           service_id=services[service].id if service else None,
                           site_id=sites[site].id if site else None))
    DOSSIER_CONFIG_TERMINAUX.mkdir(parents=True, exist_ok=True)
    for ancien in DOSSIER_CONFIG_TERMINAUX.glob("*.json"):  # y compris *.mobile.json
        ancien.unlink()
    terminaux = []
    for code, libelle, site in TERMINAUX:
        cle = generer_cle_terminal()
        t = Terminal(code=code, libelle=libelle, site_id=sites[site].id, empreinte_cle=empreinte_cle(cle))
        db.add(t)
        terminaux.append(t)
        fichier = DOSSIER_CONFIG_TERMINAUX / f"{code}.json"
        fichier.write_text(json.dumps({
            "url_serveur": URL_SERVEUR, "code_terminal": code, "cle_api": cle, "camera": 0,
            "camera_miroir": False, "intervalle_synchro_s": 10, "anti_rebond_s": 60, "port_local": 8100,
            "defis": ["tourner", "cligner"],
        }, indent=2), encoding="utf-8")
        fichier.chmod(0o600)
    for code, libelle, site in MOBILES:
        cle = generer_cle_terminal()
        db.add(Terminal(code=code, libelle=libelle, site_id=sites[site].id, empreinte_cle=empreinte_cle(cle),
                        type=TypeAppareil.MOBILE))
        fichier = DOSSIER_CONFIG_TERMINAUX / f"{code}.mobile.json"
        fichier.write_text(json.dumps({"url_serveur": URL_SERVEUR, "code_terminal": code, "cle_api": cle}, indent=2),
                           encoding="utf-8")
        fichier.chmod(0o600)
    db.flush()
    return services, sites, horaires, terminaux


def creer_demo(db, services, sites, horaires, terminaux):
    """Agents, historique de trois semaines, tentatives et lots de synchronisation (données fictives)."""
    rng = random.Random(2026)
    nrng = np.random.default_rng(2026)
    debut = date.today() - timedelta(days=21)
    creation = datetime.combine(debut - timedelta(days=30), time(9, 0))
    terminaux_par_site: dict[int, list[Terminal]] = {}
    for t in terminaux:
        terminaux_par_site.setdefault(t.site_id, []).append(t)

    lignes = list(AGENTS_MAQUETTE)
    pris = {l[0] for l in lignes}
    for site, effectif in EFFECTIF_DEMO.items():
        for _ in range(effectif):
            matricule = f"EDM-{rng.randint(1000, 9999):06d}"
            while matricule in pris:
                matricule = f"EDM-{rng.randint(1000, 9999):06d}"
            pris.add(matricule)
            service = rng.choice(SERVICES_PAR_SITE[site])
            lignes.append((matricule, rng.choice(PRENOMS), rng.choice(NOMS), FONCTIONS[service], service, site,
                           1 if service in ("PROD", "MAINT") and rng.random() < 0.6 else 0, rng.random() > 0.07, True))

    agents = []
    for mat, prenom, nom, fonction, service, site, h, enrole, actif in lignes:
        a = Agent(matricule=mat, prenom=prenom, nom=nom, fonction=fonction, service_id=services[service].id,
                  site_rattachement_id=sites[site].id, horaire_id=horaires[h].id, actif=actif, cree_le=creation,
                  email=f"{prenom[0].lower()}.{nom.lower().replace('ï', 'i').replace('é', 'e')}@edm.example")
        if enrole:
            a.consentement_le = creation
            a.gabarits = [GabaritFacial(pose=p, donnees_chiffrees=gabarit_fictif(nrng), qualite=0.9)
                          for p in ("face", "gauche", "droite", "haut", "bas")]
        db.add(a)
        agents.append(a)
    db.flush()

    sites_equipes = list(terminaux_par_site)
    maintenant = datetime.now().replace(microsecond=0)
    for a in agents:
        if not a.gabarits:
            continue
        horaire = horaires[0] if a.horaire_id == horaires[0].id else horaires[1]
        mobile = rng.random() < 0.18  # agents itinérants : missions sur d'autres sites
        jour = debut
        while jour <= date.today():
            if jour.weekday() not in horaire.jours() or rng.random() < 0.07 or (not a.actif and jour > debut + timedelta(days=10)):
                jour += timedelta(days=1)
                continue
            site_id = a.site_rattachement_id
            if (mobile and rng.random() < 0.5) or site_id not in terminaux_par_site:
                site_id = rng.choice(sites_equipes)
            t = rng.choice(terminaux_par_site[site_id])
            retard = rng.choice([0] * 9 + [rng.randint(12, 48)])
            entree = datetime.combine(jour, horaire.heure_debut) + timedelta(
                minutes=retard or -rng.randint(2, 25), seconds=rng.randint(0, 59))
            sortie = datetime.combine(jour, horaire.heure_fin) + timedelta(minutes=rng.randint(-3, 50),
                                                                           seconds=rng.randint(0, 59))
            differe = t.code == "TRM-SEL-01" and rng.random() < 0.35
            for type_, heure in ((TypePointage.ENTREE, entree), (TypePointage.SORTIE, sortie)):
                if heure > maintenant or (type_ == TypePointage.SORTIE and rng.random() < 0.03):
                    continue
                db.add(Pointage(uuid=str(uuid.uuid4()), agent_id=a.id, matricule=a.matricule, horodatage=heure,
                                type=type_, site_id=site_id, terminal_id=t.id, score=rng.uniform(0.66, 0.92),
                                hors_ligne=differe,
                                recu_le=heure + (timedelta(hours=rng.randint(1, 5)) if differe else timedelta(seconds=2))))
            jour += timedelta(days=1)

    for i in range(14):
        t = rng.choice(terminaux)
        quand = datetime.combine(date.today() - timedelta(days=rng.randint(0, 20)), time(7, 0)) + \
            timedelta(minutes=rng.randint(0, 90))
        if quand > maintenant:
            continue
        motif = rng.choice(["VISAGE_INCONNU", "ECHEC_VIVACITE", "VISAGE_INCONNU", "CHANGEMENT_VISAGE"])
        db.add(TentativeRejetee(uuid=str(uuid.uuid4()), terminal_id=t.id, site_id=t.site_id, horodatage=quand,
                                motif=motif, score=rng.uniform(0.1, 0.35) if motif == "VISAGE_INCONNU" else 0.7,
                                matricule_suppose=None if motif == "VISAGE_INCONNU" else rng.choice(agents).matricule,
                                traitee=quand.date() < date.today()))
    for i in range(12):
        t = rng.choice(terminaux)
        db.add(LotSynchronisation(terminal_id=t.id, date=maintenant - timedelta(minutes=37 * (i + 1)),
                                  recus=rng.randint(8, 35), doublons=rng.choice([0, 0, 0, 1, 2]), rejetes=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="ajoute des agents fictifs et un historique")
    parser.add_argument("--reinitialiser", action="store_true", help="supprime toutes les données existantes")
    args = parser.parse_args()

    if args.reinitialiser:
        Base.metadata.drop_all(engine)
    initialiser_base()
    with SessionLocale() as db:
        if db.query(Utilisateur).count():
            print("Base déjà initialisée (utilisez --reinitialiser pour repartir de zéro).")
            return
        services, sites, horaires, terminaux = creer_referentiels(db)
        if args.demo:
            creer_demo(db, services, sites, horaires, terminaux)
        db.commit()
    print("Base initialisée.")
    print("Comptes : " + ", ".join(f"{u[0]} / {u[4]} ({u[5].value})" for u in UTILISATEURS if u[8]))
    print(f"Configurations des terminaux écrites dans {DOSSIER_CONFIG_TERMINAUX}")


if __name__ == "__main__":
    main()
