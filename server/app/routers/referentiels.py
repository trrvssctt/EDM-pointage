"""Services, sites, horaires, terminaux et journal de synchronisation."""
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from server.app.database import get_db
from server.app.models import Agent, Horaire, LotSynchronisation, Service, Site, Terminal, Utilisateur
from server.app.schemas import (HoraireEntree, HoraireSortie, ServiceEntree, ServiceSortie, SiteEntree, SiteSortie,
                                TerminalCle, TerminalEntree, TerminalModification, TerminalSortie)
from server.app.securite import (auditer, empreinte_cle, exiger_droit, generer_cle_terminal, utilisateur_courant)
from server.app.services.vues import site_sortie, terminal_sortie

router = APIRouter(prefix="/api", tags=["Sites, terminaux et référentiels"])
gestion_sites = exiger_droit("sites.gerer")
gestion_agents = exiger_droit("agents.gerer")


def _unique(db: Session, modele, **critere):
    if db.query(modele).filter_by(**critere).first():
        raise HTTPException(409, f"« {list(critere.values())[0]} » existe déjà")


def _obtenir(db: Session, modele, ident: int, nom: str):
    objet = db.get(modele, ident)
    if objet is None:
        raise HTTPException(404, f"{nom} introuvable")
    return objet


# --- Services ---------------------------------------------------------------
@router.get("/services", response_model=list[ServiceSortie])
def lister_services(_: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    return db.query(Service).order_by(Service.nom).all()


@router.post("/services", response_model=ServiceSortie, status_code=201)
def creer_service(donnees: ServiceEntree, request: Request, acteur: Utilisateur = Depends(exiger_droit("sites.gerer")),
                  db: Session = Depends(get_db)):
    _unique(db, Service, code=donnees.code)
    s = Service(**donnees.model_dump())
    db.add(s)
    auditer(db, acteur.identifiant, "CREATION_SERVICE", s.code, request)
    db.commit()
    return s


# --- Sites ------------------------------------------------------------------
@router.get("/sites", response_model=list[SiteSortie])
def lister_sites(_: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    effectifs = Counter(sid for (sid,) in db.query(Agent.site_rattachement_id).filter(Agent.actif.is_(True)))
    sites = db.query(Site).options(joinedload(Site.terminaux)).order_by(Site.type, Site.nom).all()
    return [site_sortie(s, effectifs[s.id]) for s in sites]


@router.post("/sites", response_model=SiteSortie, status_code=201)
def creer_site(donnees: SiteEntree, request: Request, acteur: Utilisateur = Depends(gestion_sites),
               db: Session = Depends(get_db)):
    _unique(db, Site, code=donnees.code)
    s = Site(**donnees.model_dump())
    db.add(s)
    auditer(db, acteur.identifiant, "CREATION_SITE", s.code, request)
    db.commit()
    db.refresh(s)
    return site_sortie(s)


@router.put("/sites/{site_id}", response_model=SiteSortie)
def modifier_site(site_id: int, donnees: SiteEntree, request: Request, acteur: Utilisateur = Depends(gestion_sites),
                  db: Session = Depends(get_db)):
    s = _obtenir(db, Site, site_id, "Site")
    avant = s.actif
    for k, v in donnees.model_dump().items():
        setattr(s, k, v)
    action = "MODIFICATION_SITE"
    if avant != s.actif:
        action = "AUTORISATION_SITE" if s.actif else "SUSPENSION_SITE"
    auditer(db, acteur.identifiant, action, s.code, request)
    db.commit()
    return site_sortie(s)


@router.patch("/sites/{site_id}/pointage", response_model=SiteSortie)
def autoriser_pointage(site_id: int, donnees: dict, request: Request, acteur: Utilisateur = Depends(gestion_sites),
                       db: Session = Depends(get_db)):
    """Interrupteur « Pointage autorisé » de l'écran Sites et terminaux."""
    s = _obtenir(db, Site, site_id, "Site")
    s.actif = bool(donnees.get("autorise"))
    auditer(db, acteur.identifiant, "AUTORISATION_SITE" if s.actif else "SUSPENSION_SITE", s.code, request)
    db.commit()
    return site_sortie(s)


# --- Horaires ---------------------------------------------------------------
@router.get("/horaires", response_model=list[HoraireSortie])
def lister_horaires(_: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    return db.query(Horaire).order_by(Horaire.nom).all()


@router.post("/horaires", response_model=HoraireSortie, status_code=201)
def creer_horaire(donnees: HoraireEntree, request: Request, acteur: Utilisateur = Depends(exiger_droit("sites.gerer")),
                  db: Session = Depends(get_db)):
    _unique(db, Horaire, nom=donnees.nom)
    h = Horaire(**donnees.model_dump())
    db.add(h)
    auditer(db, acteur.identifiant, "CREATION_HORAIRE", h.nom, request)
    db.commit()
    return h


# --- Terminaux --------------------------------------------------------------
@router.get("/terminaux", response_model=list[TerminalSortie])
def lister_terminaux(_: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    return [terminal_sortie(t) for t in db.query(Terminal).options(joinedload(Terminal.site)).order_by(Terminal.code)]


@router.post("/terminaux", response_model=TerminalCle, status_code=201)
def creer_terminal(donnees: TerminalEntree, request: Request, acteur: Utilisateur = Depends(gestion_sites),
                   db: Session = Depends(get_db)):
    _unique(db, Terminal, code=donnees.code)
    _obtenir(db, Site, donnees.site_id, "Site")
    cle = generer_cle_terminal()
    t = Terminal(**donnees.model_dump(), empreinte_cle=empreinte_cle(cle))
    db.add(t)
    auditer(db, acteur.identifiant, "CREATION_TERMINAL", t.code, request)
    db.commit()
    db.refresh(t)
    return terminal_sortie(t, cle)


@router.put("/terminaux/{terminal_id}", response_model=TerminalSortie)
def modifier_terminal(terminal_id: int, donnees: TerminalModification, request: Request,
                      acteur: Utilisateur = Depends(gestion_sites), db: Session = Depends(get_db)):
    t = _obtenir(db, Terminal, terminal_id, "Terminal")
    valeurs = donnees.model_dump(exclude_unset=True)
    for k, v in valeurs.items():
        setattr(t, k, v)
    auditer(db, acteur.identifiant, "MODIFICATION_TERMINAL", f"{t.code} : {valeurs}", request)
    db.commit()
    db.refresh(t)
    return terminal_sortie(t)


@router.post("/terminaux/{terminal_id}/nouvelle-cle", response_model=TerminalCle)
def regenerer_cle(terminal_id: int, request: Request, acteur: Utilisateur = Depends(gestion_sites),
                  db: Session = Depends(get_db)):
    t = _obtenir(db, Terminal, terminal_id, "Terminal")
    cle = generer_cle_terminal()
    t.empreinte_cle = empreinte_cle(cle)
    auditer(db, acteur.identifiant, "NOUVELLE_CLE_TERMINAL", t.code, request)
    db.commit()
    return terminal_sortie(t, cle)


@router.post("/terminaux/{terminal_id}/synchroniser", response_model=TerminalSortie)
def forcer_synchronisation(terminal_id: int, request: Request, acteur: Utilisateur = Depends(gestion_agents),
                           db: Session = Depends(get_db)):
    """Le terminal reçoit la consigne à son prochain contact et envoie immédiatement sa file d'attente."""
    t = _obtenir(db, Terminal, terminal_id, "Terminal")
    t.synchro_demandee = True
    auditer(db, acteur.identifiant, "SYNCHRO_FORCEE", t.code, request)
    db.commit()
    return terminal_sortie(t)


@router.get("/synchronisation/lots")
def journal_synchronisation(terminal_id: int | None = None, limite: int = 50,
                            _: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    requete = db.query(LotSynchronisation).options(joinedload(LotSynchronisation.terminal))
    if terminal_id:
        requete = requete.filter(LotSynchronisation.terminal_id == terminal_id)
    lots = requete.order_by(LotSynchronisation.date.desc()).limit(min(limite, 500)).all()
    return [{"date": l.date, "terminal": l.terminal.code, "recus": l.recus, "doublons": l.doublons,
             "rejetes": l.rejetes} for l in lots]
