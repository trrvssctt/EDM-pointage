"""Dossiers des agents et enrôlement biométrique."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from server.app import config
from server.app.database import get_db
from server.app.models import Agent, Horaire, Role, Service, Site, Utilisateur, maintenant
from server.app.schemas import (AgentEntree, AgentModification, AgentSortie, AnalyseImage, Enrolement,
                                EnrolementResultat, PageResultats)
from server.app.securite import auditer, exiger_droit, perimetre, utilisateur_courant
from server.app.services import biometrie
from server.app.services.vues import agent_sortie

router = APIRouter(prefix="/api/agents", tags=["Agents et enrôlement"])
gestion = exiger_droit("agents.gerer")
enrolement = exiger_droit("biometrie.enroler")


def _agent(db: Session, agent_id: int, utilisateur: Utilisateur) -> Agent:
    a = perimetre(db.query(Agent), utilisateur).filter(Agent.id == agent_id).first()
    if a is None:
        raise HTTPException(404, "Agent introuvable ou hors de votre périmètre")
    return a


def _references(db: Session, utilisateur: Utilisateur, service_id=None, site_rattachement_id=None, horaire_id=None,
                **_):
    for modele, ident, nom in ((Service, service_id, "Service"), (Site, site_rattachement_id, "Site"),
                               (Horaire, horaire_id, "Horaire")):
        if ident is not None and db.get(modele, ident) is None:
            raise HTTPException(404, f"{nom} introuvable")
    if utilisateur.role == Role.RESPONSABLE:  # un responsable reste dans son périmètre
        if service_id is not None and utilisateur.service_id and service_id != utilisateur.service_id:
            raise HTTPException(403, "Ce service est hors de votre périmètre")
        if (site_rattachement_id is not None and utilisateur.site_id
                and site_rattachement_id != utilisateur.site_id):
            raise HTTPException(403, "Ce site est hors de votre périmètre")


def _sites(db: Session, ids: list[int]) -> list[Site]:
    sites = db.query(Site).filter(Site.id.in_(ids)).all() if ids else []
    if len(sites) != len(set(ids)):
        raise HTTPException(404, "Site autorisé introuvable")
    return sites


@router.get("", response_model=PageResultats)
def lister(q: str = "", service_id: int | None = None, site_id: int | None = None, actif: bool | None = None,
           enrole: bool | None = None, page: int = Query(1, ge=1), taille: int = Query(20, ge=1, le=500),
           utilisateur: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    requete = perimetre(db.query(Agent), utilisateur)
    if q:
        motif = f"%{q.strip()}%"
        requete = requete.filter(or_(Agent.matricule.ilike(motif), Agent.nom.ilike(motif), Agent.prenom.ilike(motif),
                                     (Agent.prenom + " " + Agent.nom).ilike(motif)))
    if service_id:
        requete = requete.filter(Agent.service_id == service_id)
    if site_id:
        requete = requete.filter(Agent.site_rattachement_id == site_id)
    if actif is not None:
        requete = requete.filter(Agent.actif.is_(actif))
    if enrole is not None:
        condition = Agent.gabarits.any()
        requete = requete.filter(condition if enrole else ~condition)
    total = requete.count()
    agents = (requete.options(joinedload(Agent.service), joinedload(Agent.site_rattachement),
                              joinedload(Agent.horaire), joinedload(Agent.gabarits), joinedload(Agent.sites_autorises))
              .order_by(Agent.nom, Agent.prenom).offset((page - 1) * taille).limit(taille).all())
    return PageResultats(total=total, elements=[agent_sortie(a) for a in agents])


@router.get("/{agent_id}", response_model=AgentSortie)
def consulter(agent_id: int, utilisateur: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    return agent_sortie(_agent(db, agent_id, utilisateur))


@router.post("", response_model=AgentSortie, status_code=201)
def creer(donnees: AgentEntree, request: Request, acteur: Utilisateur = Depends(gestion),
          db: Session = Depends(get_db)):
    matricule = donnees.matricule.strip().upper()
    if db.query(Agent).filter_by(matricule=matricule).first():
        raise HTTPException(409, f"Le matricule {matricule} existe déjà")
    _references(db, acteur, **donnees.model_dump())
    valeurs = donnees.model_dump(exclude={"sites_autorises"})
    valeurs["matricule"] = matricule
    a = Agent(**valeurs, sites_autorises=_sites(db, donnees.sites_autorises))
    db.add(a)
    auditer(db, acteur.identifiant, "CREATION_AGENT", matricule, request)
    db.commit()
    db.refresh(a)
    return agent_sortie(a)


@router.put("/{agent_id}", response_model=AgentSortie)
def modifier(agent_id: int, donnees: AgentModification, request: Request, acteur: Utilisateur = Depends(gestion),
             db: Session = Depends(get_db)):
    a = _agent(db, agent_id, acteur)
    valeurs = donnees.model_dump(exclude_unset=True)
    _references(db, acteur, **valeurs)
    if "sites_autorises" in valeurs:
        a.sites_autorises = _sites(db, valeurs.pop("sites_autorises") or [])
    for k, v in valeurs.items():
        setattr(a, k, v)
    a.modifie_le = maintenant()
    action = "DESACTIVATION_AGENT" if valeurs.get("actif") is False else "MODIFICATION_AGENT"
    auditer(db, acteur.identifiant, action, f"{a.matricule} : {', '.join(sorted(valeurs))}", request)
    db.commit()
    db.refresh(a)
    return agent_sortie(a)


@router.post("/enrolement/analyse")
def analyser_image(donnees: AnalyseImage, u: Utilisateur = Depends(exiger_droit("biometrie.proposer")),
                   db: Session = Depends(get_db)):
    """Contrôle qualité en direct pendant la capture (aucune image n'est conservée).

    Avec agent_id : signale aussitôt un visage déjà enrôlé pour un autre agent ; avec reference (photo de
    face déjà prise) : vérifie que la même personne pose."""
    if donnees.agent_id is not None and not perimetre(db.query(Agent), u).filter(Agent.id == donnees.agent_id).first():
        raise HTTPException(404, "Agent introuvable ou hors de votre périmètre")
    try:
        if donnees.agent_id is not None:
            return biometrie.analyser(donnees.image, db, donnees.agent_id, donnees.reference)
        return biometrie.analyser(donnees.image)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{agent_id}/enrolement", response_model=EnrolementResultat)
def enroler(agent_id: int, donnees: Enrolement, request: Request, acteur: Utilisateur = Depends(enrolement),
            db: Session = Depends(get_db)):
    a = _agent(db, agent_id, acteur)
    if not a.actif:
        raise HTTPException(400, "Agent désactivé : réactivez son dossier avant l'enrôlement")
    if not donnees.consentement:
        raise HTTPException(400, "Le consentement de l'agent au traitement de ses données biométriques est requis")
    captures, rejets = biometrie.extraire_gabarits([(i.pose, i.image) for i in donnees.images])
    try:
        vivant = biometrie.enroler(db, a, captures, config.MIN_IMAGES_ENROLEMENT)
    except biometrie.ErreurEnrolement as e:
        db.rollback()
        auditer(db, acteur.identifiant, "ECHEC_ENROLEMENT", f"{a.matricule} : {e}", request)
        db.commit()
        raise HTTPException(422, {"message": f"Enrôlement refusé : {e}", "images_rejetees": rejets})
    a.consentement_le = maintenant()
    a.modifie_le = maintenant()
    auditer(db, acteur.identifiant, "ENROLEMENT", f"{a.matricule} : {len(captures)} gabarits, "
                                                  f"vivacité {'validée' if vivant else 'non vérifiée'}", request)
    db.commit()
    return EnrolementResultat(gabarits_enregistres=len(captures), images_rejetees=rejets, vivacite=vivant)


@router.delete("/{agent_id}/gabarits")
def supprimer_gabarits(agent_id: int, request: Request,
                       acteur: Utilisateur = Depends(exiger_droit("biometrie.supprimer")),
                       db: Session = Depends(get_db)):
    a = _agent(db, agent_id, acteur)
    a.gabarits.clear()
    a.consentement_le = None
    a.modifie_le = maintenant()
    auditer(db, acteur.identifiant, "SUPPRESSION_BIOMETRIE", a.matricule, request)
    db.commit()
    return {"message": "Données biométriques supprimées. L'agent devra être enrôlé à nouveau pour pointer."}
