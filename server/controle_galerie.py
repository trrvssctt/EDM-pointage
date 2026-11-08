"""Contrôle des enrôlements existants : repère les agents dont les gabarits mélangent plusieurs personnes.

Lecture seule, rien n'est modifié. Sur le VPS :
    cd /opt/edm-pointage && .venv/bin/python -m server.controle_galerie
Pour chaque agent signalé : page Agents › fiche › « Supprimer le gabarit biométrique », puis réenrôler.
"""
from __future__ import annotations

from common.moteur_facial import SEUIL_SIMILARITE, similarite
from server.app.database import SessionLocale
from server.app.models import GabaritFacial
from server.app.services.biometrie import SEUIL_COHERENCE, _gabarits_des_autres


def controler() -> tuple[list[str], int, int]:
    """(alertes, agents contrôlés, agents fictifs ignorés)."""
    alertes = []
    with SessionLocale() as db:
        agents = _gabarits_des_autres(db, None)
        # Données de démonstration (server/seed.py) : gabarits aléatoires de qualité 0,9, sans visage réel.
        fictifs = {g.agent_id for g in db.query(GabaritFacial).filter(GabaritFacial.pose == "face")
                   if abs((g.qualite or 0) - 0.9) < 1e-6}
    agents = [(a, g) for a, g in agents if a.id not in fictifs]
    faces = [(a, g["face"]) for a, g in agents if "face" in g]
    for agent, gabarits in agents:
        face = gabarits.get("face")
        nom = f"{agent.matricule} ({agent.nom_complet})"
        if face is None:
            alertes.append(f"{nom} : enrôlement ancien sans photo de face, à refaire")
            continue
        for pose, v in gabarits.items():
            propre = similarite(v, face)
            if pose != "face" and propre < SEUIL_COHERENCE:
                alertes.append(f"{nom} : la pose « {pose} » ne ressemble pas à sa photo de face ({propre:.2f}), autre personne probable")
            for autre, face_autre in faces:
                if autre.id == agent.id:
                    continue
                s = similarite(v, face_autre)
                if s >= SEUIL_SIMILARITE or (pose != "face" and s >= SEUIL_COHERENCE and s > propre):
                    alertes.append(f"{nom} : la pose « {pose} » ressemble à {autre.matricule} ({autre.nom_complet}) ({s:.2f})")
    return alertes, len(agents), len(fictifs)


if __name__ == "__main__":
    resultats, controles, ignores = controler()
    print("\n".join(resultats) if resultats else "Aucun enrôlement suspect.")
    print(f"\n{len(resultats)} alerte(s) sur {controles} agent(s) enrôlé(s) ; {ignores} agent(s) de démonstration ignoré(s).")
    print(f"Seuils : même personne ≥ {SEUIL_COHERENCE}, identification ≥ {SEUIL_SIMILARITE}.")
