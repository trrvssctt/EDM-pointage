"""Logique métier du terminal, indépendante de la caméra et de l'écran (réutilisée par le simulateur)."""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from common.moteur_facial import Galerie
from terminal.stockage_local import StockageLocal
from terminal.synchronisation import Synchroniseur

DOSSIER_DONNEES = Path(__file__).resolve().parent / "donnees"
ENTREE, SORTIE = "ENTREE", "SORTIE"


@dataclass
class Configuration:
    url_serveur: str
    code_terminal: str
    cle_api: str
    camera: int | str = 0
    camera_miroir: bool = False
    intervalle_synchro_s: float = 10
    anti_rebond_s: float = 60
    port_local: int = 8100
    defis: list[str] = field(default_factory=lambda: ["tourner", "cligner"])

    @classmethod
    def charger(cls, chemin: str | Path) -> "Configuration":
        donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
        return cls(**{k: v for k, v in donnees.items() if k in cls.__dataclass_fields__})


@dataclass
class ResultatPointage:
    enregistre: bool
    message: str                 # ENTREE | SORTIE | DEJA_POINTE | SITE_NON_AUTORISE
    pointage: dict | None = None
    hors_rattachement: bool = False


class NoyauTerminal:
    def __init__(self, config: Configuration):
        self.config = config
        self.galerie = Galerie()
        self._verrou_galerie = threading.Lock()
        self.stockage = StockageLocal(DOSSIER_DONNEES / config.code_terminal, config.cle_api)
        self.synchro = Synchroniseur(config.url_serveur, config.cle_api, self.stockage,
                                     config.intervalle_synchro_s, self._nouvelle_galerie)
        self._derniers: dict[str, float] = {}

    def demarrer(self) -> None:
        self.synchro.start()

    def arreter(self) -> None:
        self.synchro.arreter()

    def _nouvelle_galerie(self, agents: list[dict]) -> None:
        with self._verrou_galerie:
            self.galerie.charger(agents)

    def identifier(self, vecteur):
        with self._verrou_galerie:
            return self.galerie.identifier(vecteur)

    def score_agent(self, matricule, vecteur) -> float:
        with self._verrou_galerie:
            return self.galerie.score_agent(matricule, vecteur)

    def agent(self, matricule: str) -> dict:
        return self.galerie.agents.get(matricule, {"matricule": matricule, "prenom": "", "nom": matricule})

    @property
    def site_id(self) -> int | None:
        return self.synchro.config_serveur.get("site_id")

    def autorise_ici(self, matricule: str) -> bool:
        a = self.agent(matricule)
        if a.get("tous_sites", True) or self.site_id is None:
            return True
        return self.site_id == a.get("site_rattachement_id") or self.site_id in a.get("sites_autorises", [])

    def deja_pointe(self, matricule: str) -> bool:
        return time.monotonic() - self._derniers.get(matricule, -1e9) < self.config.anti_rebond_s

    def type_suivant(self, matricule: str) -> str:
        """ENTREE ou SORTIE selon le dernier pointage du jour, quel que soit le site."""
        candidats = []
        local = self.stockage.dernier_pointage_du_jour(matricule)
        if local:
            candidats.append((datetime.fromisoformat(local["horodatage"]).replace(tzinfo=None), local["type"]))
        distant = self.synchro.etat_agent(matricule)
        if distant and distant.get("dernier_type"):
            candidats.append((datetime.fromisoformat(distant["horodatage"]), distant["dernier_type"]))
        if not candidats:
            return ENTREE
        return SORTIE if max(candidats)[1] == ENTREE else ENTREE

    def enregistrer(self, matricule: str, score: float, type_force: str | None = None) -> ResultatPointage:
        if self.deja_pointe(matricule):
            return ResultatPointage(False, "DEJA_POINTE")
        if not self.autorise_ici(matricule):
            self.rejeter("SITE_NON_AUTORISE", matricule, score)
            return ResultatPointage(False, "SITE_NON_AUTORISE")
        type_ = type_force or self.type_suivant(matricule)
        p = self.stockage.ajouter_pointage(matricule, type_, score, hors_ligne=not self.synchro.en_ligne)
        self._derniers[matricule] = time.monotonic()
        self.synchro.declencher()  # transmission immédiate si le réseau est disponible
        logging.getLogger("terminal").info("Pointage %s %s (score %.2f)", matricule, type_, score)
        hors = self.site_id is not None and self.agent(matricule).get("site_rattachement_id") not in (None, self.site_id)
        return ResultatPointage(True, type_, p, hors)

    def annuler(self, pointage: dict) -> None:
        """« Ce n'est pas moi » : le pointage est annulé et la contestation tracée."""
        self.stockage.annuler(pointage["uuid"])
        self._derniers.pop(pointage["matricule"], None)
        self.rejeter("IDENTITE_CONTESTEE", pointage["matricule"], pointage.get("score", 0))

    def rejeter(self, motif: str, matricule: str | None = None, score: float = 0.0) -> None:
        self.stockage.ajouter_tentative(motif, matricule, score, hors_ligne=not self.synchro.en_ligne)
        self.synchro.declencher()
