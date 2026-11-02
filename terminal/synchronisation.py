"""Communication avec le serveur central et synchronisation différée des pointages."""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable

import requests

from terminal.stockage_local import StockageLocal

journal = logging.getLogger("terminal.synchro")
TAILLE_LOT = 200
VERSION_TERMINAL = "1.0.0"


class TerminalNonAutorise(Exception):
    pass


class Synchroniseur(threading.Thread):
    def __init__(self, url: str, cle_api: str, stockage: StockageLocal, intervalle_s: float,
                 sur_nouvelle_galerie: Callable[[list[dict]], None]):
        super().__init__(daemon=True, name="synchronisation")
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"X-Terminal-Key": cle_api, "X-Terminal-Version": VERSION_TERMINAL})
        self.stockage = stockage
        self.intervalle = intervalle_s
        self.sur_nouvelle_galerie = sur_nouvelle_galerie
        self.en_ligne = False
        self.etat = "CONNEXION"  # CONNEXION | EN_LIGNE | SYNCHRO | HORS_LIGNE | REFUSE
        self.message = "Connexion au serveur..."
        self.derniere_synchro: datetime | None = None
        # Identité du site : conservée localement pour s'afficher même sans réseau au démarrage.
        self.config_serveur: dict = stockage.charger_site()
        self._version_logo = None
        self._reveil = threading.Event()
        self._arret = threading.Event()
        self.version_galerie, agents = stockage.charger_galerie()
        if agents:
            sur_nouvelle_galerie(agents)

    # --- Appels HTTP ------------------------------------------------------
    def _requete(self, methode: str, chemin: str, timeout: float = 5, brut: bool = False, **kw):
        entetes = {"X-Terminal-En-Attente": str(self.stockage.nb_en_attente())}
        r = self.session.request(methode, self.url + chemin, timeout=timeout, headers=entetes, **kw)
        if r.status_code in (401, 403):
            raise TerminalNonAutorise(r.json().get("detail", "Terminal non autorisé"))
        r.raise_for_status()
        return r if brut else r.json()

    def etat_agent(self, matricule: str) -> dict | None:
        """Dernier pointage du jour connu du serveur (tous sites). None si injoignable."""
        if not self.en_ligne:
            return None
        try:
            return self._requete("GET", f"/api/terminal/etat-agent/{matricule}", timeout=1.5)
        except (requests.RequestException, TerminalNonAutorise):
            return None

    # --- Cycle de synchronisation ------------------------------------------
    def declencher(self) -> None:
        self._reveil.set()

    def arreter(self) -> None:
        self._arret.set()
        self._reveil.set()

    def _identite(self) -> None:
        config = self._requete("GET", "/api/terminal/configuration")
        if config.get("synchro_demandee"):
            journal.info("Synchronisation forcée demandée par l'administration")
        self.config_serveur = config
        self.stockage.sauver_site(config)
        version_logo = config.get("organisation", {}).get("version_logo")
        if version_logo != self._version_logo:
            r = self._requete("GET", "/api/terminal/logo", brut=True)
            if r.status_code == 200:
                self.stockage.sauver_logo(r.content, r.headers.get("content-type", "image/png"))
            self._version_logo = version_logo

    def cycle(self) -> None:
        self._identite()
        galerie = self._requete("GET", "/api/terminal/galerie", params={"version": self.version_galerie}, timeout=30)
        if not galerie["inchangee"]:
            self.stockage.sauver_galerie(galerie["version"], galerie["agents"])
            self.version_galerie = galerie["version"]
            self.sur_nouvelle_galerie(galerie["agents"])
            journal.info("Galerie mise à jour : %d agents", len(galerie["agents"]))
        if self.stockage.nb_en_attente():
            self.etat = "SYNCHRO"
        for table, cle in (("pointages", "pointages"), ("tentatives", "tentatives"), ("annulations", "uuids")):
            while lot := self.stockage.en_attente(table, TAILLE_LOT):
                contenu = [l["uuid"] for l in lot] if table == "annulations" else lot
                r = self._requete("POST", f"/api/terminal/{table}", json={cle: contenu}, timeout=30)
                self.stockage.marquer_synchronises(table, r["acceptes"] + r["doublons"] + (
                    list(r["rejetes"]) if table == "annulations" else []), r["rejetes"])
                if r["rejetes"]:
                    journal.warning("%s refusés par le serveur : %s", table, r["rejetes"])
                if len(lot) < TAILLE_LOT:
                    break
        self.derniere_synchro = datetime.now()

    def run(self) -> None:
        while not self._arret.is_set():
            try:
                self.cycle()
                if not self.en_ligne:
                    journal.info("Connexion au serveur établie")
                self.en_ligne = True
                self.etat, self.message = "EN_LIGNE", "En ligne"
            except TerminalNonAutorise as e:
                self.en_ligne = False
                self.etat, self.message = "REFUSE", str(e)
            except (requests.RequestException, ValueError) as e:
                if self.en_ligne:
                    journal.warning("Serveur injoignable, passage en mode hors ligne (%s)", type(e).__name__)
                self.en_ligne = False
                self.etat, self.message = "HORS_LIGNE", "Hors ligne · enregistrement local"
            self._reveil.wait(self.intervalle)
            self._reveil.clear()
