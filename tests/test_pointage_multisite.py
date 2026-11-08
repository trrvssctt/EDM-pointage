"""Pointage multisite, unicité des événements, synchronisation, tableau de bord, rapports et exports."""
import uuid
from datetime import date, datetime, timedelta

from server.app.database import SessionLocale
from server.app.models import Agent, Organisation, Pointage
from server.app.services.maintenance import purger
from tests.conftest import CLE_KATI, CLE_SIEGE, enrolement

SIEGE = {"X-Terminal-Key": CLE_SIEGE}
KATI = {"X-Terminal-Key": CLE_KATI}


def pointage(matricule, type_, horodatage=None, **kw):
    return {"uuid": str(uuid.uuid4()), "matricule": matricule, "type": type_,
            "horodatage": (horodatage or datetime.now()).isoformat(timespec="seconds"), **kw}


def lignes(client, admin, **filtres):
    q = "&".join(f"{k}={v}" for k, v in filtres.items())
    return client.get(f"/api/pointages?{q}", headers=admin).json()


# --- Terminaux ------------------------------------------------------------------
def test_terminal_inconnu_ou_desactive_refuse(client, admin):
    assert client.get("/api/terminal/configuration", headers={"X-Terminal-Key": "faux"}).status_code == 401
    client.put("/api/terminaux/2", json={"actif": False}, headers=admin)
    assert client.get("/api/terminal/configuration", headers=KATI).status_code == 403


def test_site_non_autorise_au_pointage(client, admin):
    assert client.patch("/api/sites/2/pointage", json={"autorise": False}, headers=admin).json()["actif"] is False
    assert client.get("/api/terminal/configuration", headers=KATI).status_code == 403


def test_terminal_declare_version_et_file_d_attente(client, admin):
    client.get("/api/terminal/configuration", headers={**KATI, "X-Terminal-Version": "1.0.0", "X-Terminal-En-Attente": "37"})
    t = next(t for t in client.get("/api/terminaux", headers=admin).json() if t["code"] == "T-KATI")
    assert t["version"] == "1.0.0" and t["nb_en_attente"] == 37 and t["etat"] == "SYNCHRO"
    site = next(s for s in client.get("/api/sites", headers=admin).json() if s["code"] == "KATI")
    assert site["etat"] == "SYNCHRO" and site["nb_terminaux"] == 1
    assert client.get("/api/tableau-de-bord", headers=admin).json()["en_attente"] == 37


def test_forcer_la_synchronisation(client, admin):
    assert client.post("/api/terminaux/2/synchroniser", headers=admin).json()["synchro_demandee"] is True
    assert client.get("/api/terminal/configuration", headers=KATI).json()["synchro_demandee"] is True
    assert client.get("/api/terminal/configuration", headers=KATI).json()["synchro_demandee"] is False  # consigne lue


def test_nouvelle_cle_invalide_l_ancienne(client, admin):
    cle = client.post("/api/terminaux/2/nouvelle-cle", headers=admin).json()["cle_api"]
    assert client.get("/api/terminal/configuration", headers=KATI).status_code == 401
    assert client.get("/api/terminal/configuration", headers={"X-Terminal-Key": cle}).status_code == 200


def test_nouvelle_cle_propose_l_adresse_des_appareils(client, admin, monkeypatch):
    from server.app import config
    monkeypatch.setattr(config, "URL_APPAREILS", "http://203.0.113.10:8095")
    assert client.post("/api/terminaux/2/nouvelle-cle", headers=admin).json()["url_serveur"] == "http://203.0.113.10:8095"
    monkeypatch.setattr(config, "URL_APPAREILS", "")  # non configurée : la page propose sa propre adresse
    assert client.post("/api/terminaux/2/nouvelle-cle", headers=admin).json()["url_serveur"] is None


# --- Pointage multisite -----------------------------------------------------------
def test_pointage_sur_un_site_different_du_rattachement(client, admin, creer_agent):
    creer_agent("EDM0001", site_id=1)  # rattaché au siège
    r = client.post("/api/terminal/pointages", json={"pointages": [pointage("EDM0001", "ENTREE", score=0.8)]}, headers=KATI)
    assert len(r.json()["acceptes"]) == 1
    p = lignes(client, admin)["elements"][0]
    assert p["site"] == "Agence de Kati" and p["terminal"] == "T-KATI"   # lieu réel et terminal utilisé
    assert p["alerte"] == "HORS_RATTACHEMENT" and p["matricule"] == "EDM0001" and p["type"] == "ENTREE"
    assert 60 <= p["confiance"] <= 99


def test_entree_sur_un_site_sortie_sur_un_autre(client, creer_agent):
    creer_agent("EDM0001")
    client.post("/api/terminal/pointages", json={"pointages": [pointage("EDM0001", "ENTREE")]}, headers=SIEGE)
    etat = client.get("/api/terminal/etat-agent/EDM0001", headers=KATI).json()
    assert etat["dernier_type"] == "ENTREE" and etat["site"] == "Siège"


def test_agent_limite_a_certains_sites(client, admin, creer_agent):
    creer_agent("EDM0001", site_id=1, tous_sites=False, sites_autorises=[3])
    r = client.post("/api/terminal/pointages", json={"pointages": [pointage("EDM0001", "ENTREE")]}, headers=KATI).json()
    assert list(r["rejetes"].values()) == ["site non autorisé pour cet agent"]
    r = client.post("/api/terminal/pointages", json={"pointages": [pointage("EDM0001", "ENTREE")]}, headers=SIEGE).json()
    assert len(r["acceptes"]) == 1  # le site de rattachement reste toujours autorisé


def test_un_evenement_n_est_enregistre_qu_une_fois(client, admin, creer_agent):
    creer_agent("EDM0001")
    p = pointage("EDM0001", "ENTREE")
    r1 = client.post("/api/terminal/pointages", json={"pointages": [p, p]}, headers=SIEGE).json()
    r2 = client.post("/api/terminal/pointages", json={"pointages": [p]}, headers=SIEGE).json()  # renvoi après coupure
    assert r1["acceptes"] == [p["uuid"]] and r1["doublons"] == [p["uuid"]]
    assert r2["doublons"] == [p["uuid"]]
    assert lignes(client, admin)["total"] == 1
    lots = client.get("/api/synchronisation/lots", headers=admin).json()
    assert {(l["recus"], l["doublons"]) for l in lots} == {(1, 1), (0, 1)}


def test_pointage_differe_conserve_son_heure_reelle(client, admin, creer_agent):
    creer_agent("EDM0001")
    heure = datetime.now().replace(microsecond=0) - timedelta(hours=3)
    client.post("/api/terminal/pointages", json={"pointages": [pointage("EDM0001", "ENTREE", heure, hors_ligne=True)]},
                headers=SIEGE)
    p = lignes(client, admin)["elements"][0]
    assert datetime.fromisoformat(p["horodatage"]) == heure and p["synchro"] == "DIFFERE"
    assert lignes(client, admin, alerte="DIFFERE")["total"] == 1


def test_rejets_matricule_inconnu_et_horodatage_futur(client, creer_agent):
    creer_agent("EDM0001")
    inconnu = pointage("INCONNU", "ENTREE")
    futur = pointage("EDM0001", "ENTREE", datetime.now() + timedelta(days=1))
    r = client.post("/api/terminal/pointages", json={"pointages": [inconnu, futur]}, headers=SIEGE).json()
    assert set(r["rejetes"]) == {inconnu["uuid"], futur["uuid"]}


def test_ce_n_est_pas_moi_annule_le_pointage(client, admin, creer_agent):
    creer_agent("EDM0001")
    p = pointage("EDM0001", "ENTREE")
    client.post("/api/terminal/pointages", json={"pointages": [p]}, headers=KATI)
    assert client.post("/api/terminal/annulations", json={"uuids": [p["uuid"]]}, headers=SIEGE).json()["rejetes"]
    assert client.post("/api/terminal/annulations", json={"uuids": [p["uuid"]]}, headers=KATI).json()["acceptes"]
    assert lignes(client, admin)["elements"][0]["alerte"] == "ANNULE"
    # Un pointage annulé ne compte pas dans les présences ni dans le calcul entrée / sortie
    assert client.get("/api/terminal/etat-agent/EDM0001", headers=KATI).json()["dernier_type"] is None
    assert client.get("/api/tableau-de-bord", headers=admin).json()["presents"] == 0


def test_galerie_versionnee_avec_sites_autorises(client, admin, creer_agent):
    agent = creer_agent("EDM0001")
    client.post(f"/api/agents/{agent['id']}/enrolement", json=enrolement(), headers=admin)
    g = client.get("/api/terminal/galerie", headers=SIEGE).json()
    entree = g["agents"][0]
    assert entree["matricule"] == "EDM0001" and len(entree["gabarits"]) == 4 and entree["tous_sites"] is True
    assert client.get(f"/api/terminal/galerie?version={g['version']}", headers=SIEGE).json()["inchangee"] is True
    client.put(f"/api/agents/{agent['id']}", json={"actif": False}, headers=admin)
    g2 = client.get(f"/api/terminal/galerie?version={g['version']}", headers=SIEGE).json()
    assert g2["inchangee"] is False and g2["agents"] == []


def test_tentatives_dans_l_historique_et_le_tableau_de_bord(client, admin):
    t = {"uuid": str(uuid.uuid4()), "horodatage": datetime.now().isoformat(), "motif": "ECHEC_VIVACITE",
         "matricule_suppose": None, "score": 0.6}
    client.post("/api/terminal/tentatives", json={"tentatives": [t, t]}, headers=KATI)
    refus = lignes(client, admin, type="REFUSE")
    assert refus["total"] == 1 and refus["elements"][0]["alerte"] == "FRAUDE"
    anomalies = client.get("/api/tableau-de-bord", headers=admin).json()["anomalies"]
    fraude = next(a for a in anomalies if a["type"] == "FRAUDE")
    client.post(f"/api/tentatives/{fraude['id']}/traiter", headers=admin)
    assert not any(a["type"] == "FRAUDE" for a in client.get("/api/tableau-de-bord", headers=admin).json()["anomalies"])


# --- Rapports et exports -------------------------------------------------------------
def _historique_deux_jours(client, creer_agent):
    a = creer_agent("EDM0001")
    hier, avant_hier = date.today() - timedelta(days=1), date.today() - timedelta(days=2)
    with SessionLocale() as db:  # agent créé avant la période
        db.get(Agent, a["id"]).cree_le = datetime.combine(avant_hier, datetime.min.time())
        db.commit()
    minuit = datetime.combine(hier, datetime.min.time())
    lot = [pointage("EDM0001", "ENTREE", minuit + timedelta(hours=8)),  # 30 min de retard
           pointage("EDM0001", "SORTIE", minuit + timedelta(hours=16, minutes=5))]
    client.post("/api/terminal/pointages", json={"pointages": lot}, headers=KATI)
    return hier, avant_hier


def test_rapport_presence_retard_absence(client, admin, creer_agent):
    hier, avant_hier = _historique_deux_jours(client, creer_agent)
    r = client.get(f"/api/rapports?date_debut={avant_hier}&date_fin={hier}&regroupement=agent", headers=admin).json()
    detail = {j["date"]: j for j in r["detail"]}
    assert detail[avant_hier.isoformat()]["statut"] == "ABSENT"
    j = detail[hier.isoformat()]
    assert j["statut"] == "RETARD" and j["retard_minutes"] == 30
    assert j["duree_minutes"] == 485 and "Pointage hors site de rattachement" in j["anomalies"]
    l = r["lignes"][0]
    assert (l["effectif"], l["jours_ouvres"], l["presences"], l["absences"], l["retards"]) == (1, 2, 1, 1, 1)
    assert r["indicateurs"]["taux_presence"] == 50.0
    retards = client.get(f"/api/rapports?type_rapport=retards&date_debut={avant_hier}&date_fin={hier}", headers=admin).json()
    assert [x["statut"] for x in retards["detail"]] == ["RETARD"]


def test_exports_pdf_et_excel(client, admin, creer_agent):
    hier, avant_hier = _historique_deux_jours(client, creer_agent)
    q = f"date_debut={avant_hier}&date_fin={hier}"
    pdf = client.get(f"/api/rapports/export.pdf?{q}", headers=admin)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    for chemin in (f"/api/rapports/export.xlsx?{q}", f"/api/pointages/export.xlsx?{q}", "/api/tableau-de-bord/export.xlsx"):
        r = client.get(chemin, headers=admin)
        assert r.status_code == 200 and r.content.startswith(b"PK"), chemin  # classeur Office Open XML


def test_tableau_de_bord(client, admin, creer_agent):
    creer_agent("EDM0001")
    client.post("/api/terminal/pointages", json={"pointages": [pointage("EDM0001", "ENTREE")]}, headers=KATI)
    d = client.get("/api/tableau-de-bord", headers=admin).json()
    assert d["presents"] == 1 and d["presence_par_site"][0]["presents"] == 1
    assert any(a["type"] == "HORS_RATTACHEMENT" for a in d["anomalies"])
    assert any(t["code"] == "T-KATI" and t["etat"] == "EN_LIGNE" for t in d["terminaux"])
    assert len(d["evolution"]) == 7


def test_purge_selon_la_duree_de_conservation(client, creer_agent):
    creer_agent("EDM0001")
    ancien = datetime.now() - timedelta(days=60)
    client.post("/api/terminal/pointages", json={"pointages": [pointage("EDM0001", "ENTREE", ancien),
                                                               pointage("EDM0001", "ENTREE")]}, headers=KATI)
    with SessionLocale() as db:
        db.query(Organisation).one().duree_conservation_jours = 30
        db.commit()
        assert purger(db)["pointages"] == 1
        assert db.query(Pointage).count() == 1
