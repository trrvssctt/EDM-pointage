"""Actualisation des données de démonstration avant une présentation."""
from datetime import datetime, timedelta

import numpy as np

from server.actualiser_demo import actualiser
from server.app.database import SessionLocale
from server.app.models import GabaritFacial, Pointage, Terminal
from server.app.securite import chiffrer_gabarit


def _gabarit(agent_id, qualite):
    v = np.random.default_rng(1).normal(size=128).astype(np.float32)
    return GabaritFacial(agent_id=agent_id, pose="face", donnees_chiffrees=chiffrer_gabarit(v / np.linalg.norm(v)), qualite=qualite)


def test_complete_l_historique_des_seuls_agents_fictifs_sans_doublon_ni_futur(client, creer_agent):
    fictif, reel = creer_agent("EDM0001"), creer_agent("EDM0002")
    with SessionLocale() as db:
        db.add_all([_gabarit(fictif["id"], 0.9),   # agent de démonstration (server/seed.py)
                    _gabarit(reel["id"], 1.0)])    # agent réellement enrôlé
        db.commit()
        fin = datetime(2026, 11, 9, 10, 30)
        bilan = actualiser(db, fin=fin)
        assert bilan["agents_fictifs"] == 1 and bilan["pointages"] > 20
        assert db.query(Pointage).filter(Pointage.agent_id == reel["id"]).count() == 0
        assert db.query(Pointage).filter(Pointage.horodatage > fin).count() == 0
        assert db.query(Pointage).filter(Pointage.horodatage >= fin - timedelta(days=1)).count() >= 1  # jusqu'à aujourd'hui
        assert db.query(Terminal).filter(Terminal.dernier_contact.isnot(None)).count() >= 1
        total = db.query(Pointage).count()
        assert actualiser(db, fin=fin)["pointages"] == 0 and db.query(Pointage).count() == total  # relançable
        assert actualiser(db, fin=fin + timedelta(hours=8))["pointages"] >= 1  # sorties du soir ajoutées ensuite
