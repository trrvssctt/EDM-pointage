"""API utilisée par les terminaux de pointage (authentification par clé X-Terminal-Key)."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from server.app.database import get_db
from server.app.models import Agent, LotSynchronisation, Pointage, TentativeRejetee, Terminal, TypeAppareil, maintenant
from server.app.routers.organisation import organisation
from server.app.schemas import LotAnnulations, LotPointages, LotTentatives, ResultatSynchro
from server.app.securite import terminal_courant
from server.app.services.biometrie import galerie

router = APIRouter(prefix="/api/terminal", tags=["Terminaux de pointage"])

# Tolérance sur l'horloge d'un terminal : un pointage daté dans le futur est suspect.
DERIVE_MAX = timedelta(minutes=10)


def _naive(d: datetime) -> datetime:
    """Les horodatages sont conservés en heure locale du serveur, sans fuseau."""
    return d.astimezone().replace(tzinfo=None, microsecond=0) if d.tzinfo else d.replace(microsecond=0)


@router.get("/configuration")
def configuration(terminal: Terminal = Depends(terminal_courant), db: Session = Depends(get_db)):
    """Contacté à chaque cycle : identité du site, marque de l'organisation et consignes en attente."""
    org = organisation(db)
    consigne = terminal.synchro_demandee
    if consigne:
        terminal.synchro_demandee = False
        db.commit()
    return {"terminal": terminal.code, "libelle": terminal.libelle, "site_id": terminal.site_id,
            "site_code": terminal.site.code, "site_nom": terminal.site.libelle_court,
            "heure_serveur": maintenant(), "synchro_demandee": consigne,
            "organisation": {"nom": org.nom, "sigle": org.sigle, "couleur_primaire": org.couleur_primaire,
                             "couleur_menu": org.couleur_menu, "version_logo": str(org.modifie_le)}}


@router.get("/logo")
def logo(_: Terminal = Depends(terminal_courant), db: Session = Depends(get_db)):
    org = organisation(db)
    if org.logo is None:
        return Response(status_code=204)
    return Response(org.logo, media_type=org.logo_type)


@router.get("/galerie")
def telecharger_galerie(version: str = "", terminal: Terminal = Depends(terminal_courant),
                        db: Session = Depends(get_db)):
    signature, entrees = galerie(db)
    if version == signature:
        return {"version": signature, "inchangee": True}
    return {"version": signature, "inchangee": False, "agents": entrees}


@router.get("/etat-agent/{matricule}")
def etat_agent(matricule: str, terminal: Terminal = Depends(terminal_courant), db: Session = Depends(get_db)):
    """Dernier pointage du jour, tous sites confondus : permet de déduire ENTRÉE / SORTIE."""
    debut = datetime.combine(maintenant().date(), datetime.min.time())
    dernier = (db.query(Pointage).filter(Pointage.matricule == matricule, Pointage.horodatage >= debut,
                                         Pointage.annule.is_(False))
               .order_by(Pointage.horodatage.desc()).first())
    if dernier is None:
        return {"dernier_type": None, "horodatage": None, "site": None}
    return {"dernier_type": dernier.type, "horodatage": dernier.horodatage, "site": dernier.site.libelle_court}


def _journaliser_lot(db: Session, terminal: Terminal, recus: int, doublons: int, rejetes: int) -> None:
    if recus + doublons + rejetes:
        db.add(LotSynchronisation(terminal_id=terminal.id, recus=recus, doublons=doublons, rejetes=rejetes))
        db.commit()


@router.post("/pointages", response_model=ResultatSynchro)
def recevoir_pointages(lot: LotPointages, terminal: Terminal = Depends(terminal_courant),
                       db: Session = Depends(get_db)):
    """Réception idempotente : un événement (uuid) n'est enregistré qu'une seule fois."""
    acceptes, doublons, rejetes = [], [], {}
    limite_futur = maintenant() + DERIVE_MAX
    for p in lot.pointages:
        if db.query(Pointage.id).filter_by(uuid=p.uuid).first():
            doublons.append(p.uuid)
            continue
        agent = db.query(Agent).options(joinedload(Agent.sites_autorises)).filter_by(matricule=p.matricule).first()
        if agent is None:
            rejetes[p.uuid] = "matricule inconnu"
            continue
        if not agent.peut_pointer_sur(terminal.site_id):
            rejetes[p.uuid] = "site non autorisé pour cet agent"
            continue
        horodatage = _naive(p.horodatage)
        if horodatage > limite_futur:
            rejetes[p.uuid] = "horodatage dans le futur (horloge du terminal à vérifier)"
            continue
        db.add(Pointage(uuid=p.uuid, agent_id=agent.id, matricule=agent.matricule, horodatage=horodatage,
                        type=p.type, site_id=terminal.site_id, terminal_id=terminal.id, score=p.score,
                        hors_ligne=p.hors_ligne, secours=terminal.type == TypeAppareil.MOBILE))
        try:
            db.commit()
            acceptes.append(p.uuid)
        except IntegrityError:  # envoi concurrent du même événement
            db.rollback()
            doublons.append(p.uuid)
    # La file d'attente déclarée par le terminal se vide au fur et à mesure des lots reçus.
    terminal.nb_en_attente = max(0, terminal.nb_en_attente - len(lot.pointages))
    db.commit()
    _journaliser_lot(db, terminal, len(acceptes), len(doublons), len(rejetes))
    return ResultatSynchro(acceptes=acceptes, doublons=doublons, rejetes=rejetes)


@router.post("/tentatives", response_model=ResultatSynchro)
def recevoir_tentatives(lot: LotTentatives, terminal: Terminal = Depends(terminal_courant),
                        db: Session = Depends(get_db)):
    acceptes, doublons = [], []
    for t in lot.tentatives:
        if db.query(TentativeRejetee.id).filter_by(uuid=t.uuid).first():
            doublons.append(t.uuid)
            continue
        db.add(TentativeRejetee(uuid=t.uuid, horodatage=_naive(t.horodatage), motif=t.motif,
                                matricule_suppose=t.matricule_suppose, score=t.score, hors_ligne=t.hors_ligne,
                                terminal_id=terminal.id, site_id=terminal.site_id))
        try:
            db.commit()
            acceptes.append(t.uuid)
        except IntegrityError:
            db.rollback()
            doublons.append(t.uuid)
    return ResultatSynchro(acceptes=acceptes, doublons=doublons, rejetes={})


@router.post("/annulations", response_model=ResultatSynchro)
def recevoir_annulations(lot: LotAnnulations, terminal: Terminal = Depends(terminal_courant),
                         db: Session = Depends(get_db)):
    """« Ce n'est pas moi » : annule un pointage déjà transmis (seulement depuis le terminal émetteur)."""
    acceptes, rejetes = [], {}
    for uuid in lot.uuids:
        p = db.query(Pointage).filter_by(uuid=uuid).first()
        if p is None:
            rejetes[uuid] = "pointage inconnu"
        elif p.terminal_id != terminal.id:
            rejetes[uuid] = "pointage émis par un autre terminal"
        else:
            p.annule = True
            acceptes.append(uuid)
    db.commit()
    return ResultatSynchro(acceptes=acceptes, doublons=[], rejetes=rejetes)
