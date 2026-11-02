"""Purge des données au-delà de la durée de conservation fixée par l'organisation.

Exécutée au démarrage du serveur puis chaque nuit ; utilisable aussi en ligne de commande :
    python -m server.app.services.maintenance
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from server.app.database import SessionLocale
from server.app.models import JournalAudit, LotSynchronisation, Organisation, Pointage, TentativeRejetee

journal = logging.getLogger("maintenance")


def purger(db: Session) -> dict[str, int]:
    organisation = db.query(Organisation).first()
    if organisation is None:
        return {}
    limite = datetime.now() - timedelta(days=organisation.duree_conservation_jours)
    resultat = {
        "pointages": db.query(Pointage).filter(Pointage.horodatage < limite).delete(),
        "tentatives": db.query(TentativeRejetee).filter(TentativeRejetee.horodatage < limite).delete(),
        "lots": db.query(LotSynchronisation).filter(LotSynchronisation.date < limite).delete(),
        "audit": db.query(JournalAudit).filter(JournalAudit.date < limite).delete(),
    }
    if any(resultat.values()):
        db.add(JournalAudit(acteur="systeme", action="PURGE_CONSERVATION",
                            details=f"avant le {limite:%d/%m/%Y} : {resultat}"))
    db.commit()
    return resultat


def planifier() -> None:
    """Purge immédiate, puis toutes les 24 heures (fil d'exécution en arrière-plan)."""
    def boucle():
        while True:
            try:
                with SessionLocale() as db:
                    r = purger(db)
                if any(r.values()):
                    journal.info("Purge de conservation : %s", r)
            except Exception:  # la purge ne doit jamais arrêter le serveur
                journal.exception("Échec de la purge de conservation")
            threading.Event().wait(24 * 3600)
    threading.Thread(target=boucle, daemon=True, name="purge-conservation").start()


if __name__ == "__main__":
    with SessionLocale() as session:
        print(purger(session))
