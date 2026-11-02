"""Stockage local du terminal : file d'attente des pointages (mode déconnecté) et cache chiffré de la galerie."""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

SCHEMA = """
CREATE TABLE IF NOT EXISTS pointages (
    uuid TEXT PRIMARY KEY,
    matricule TEXT NOT NULL,
    horodatage TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('ENTREE', 'SORTIE')),
    score REAL NOT NULL,
    hors_ligne INTEGER NOT NULL,
    synchronise INTEGER NOT NULL DEFAULT 0,  -- 0 en attente, 1 transmis, 2 refusé, 3 annulé avant envoi
    annule INTEGER NOT NULL DEFAULT 0,
    erreur TEXT
);
CREATE INDEX IF NOT EXISTS idx_pointages_attente ON pointages (synchronise);
CREATE TABLE IF NOT EXISTS tentatives (
    uuid TEXT PRIMARY KEY,
    horodatage TEXT NOT NULL,
    motif TEXT NOT NULL,
    matricule_suppose TEXT,
    score REAL NOT NULL,
    hors_ligne INTEGER NOT NULL DEFAULT 0,
    synchronise INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS annulations (
    uuid TEXT PRIMARY KEY,
    synchronise INTEGER NOT NULL DEFAULT 0
);
"""


def horodatage_local() -> str:
    """Heure locale avec fuseau (ISO 8601), ex. 2026-10-31T08:02:11+00:00."""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


class StockageLocal:
    def __init__(self, dossier: Path, cle_terminal: str):
        dossier.mkdir(parents=True, exist_ok=True)
        self.base = dossier / "pointages.db"
        self.fichier_galerie = dossier / "galerie.chiffree"
        self.fichier_site = dossier / "site.json"
        self.fichier_logo = dossier / "logo"
        # Clé de chiffrement locale dérivée de la clé d'API du terminal.
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(cle_terminal.encode()).digest()))
        self._verrou = threading.Lock()
        with self._connexion() as cx:
            cx.executescript(SCHEMA)

    def _connexion(self) -> sqlite3.Connection:
        cx = sqlite3.connect(self.base, timeout=10)
        cx.row_factory = sqlite3.Row
        return cx

    # --- Pointages ---------------------------------------------------------
    def ajouter_pointage(self, matricule: str, type_: str, score: float, hors_ligne: bool) -> dict:
        p = {"uuid": str(uuid.uuid4()), "matricule": matricule, "horodatage": horodatage_local(), "type": type_,
             "score": round(float(score), 4), "hors_ligne": hors_ligne}
        with self._verrou, self._connexion() as cx:
            cx.execute("INSERT INTO pointages (uuid, matricule, horodatage, type, score, hors_ligne) "
                       "VALUES (:uuid, :matricule, :horodatage, :type, :score, :hors_ligne)", p)
        return p

    def ajouter_tentative(self, motif: str, matricule: str | None, score: float, hors_ligne: bool = False) -> None:
        with self._verrou, self._connexion() as cx:
            cx.execute("INSERT INTO tentatives (uuid, horodatage, motif, matricule_suppose, score, hors_ligne) "
                       "VALUES (?,?,?,?,?,?)", (str(uuid.uuid4()), horodatage_local(), motif, matricule,
                                                round(float(score), 4), int(hors_ligne)))

    def annuler(self, uuid_pointage: str) -> None:
        """« Ce n'est pas moi » : retire le pointage de la file, ou programme son annulation côté serveur."""
        with self._verrou, self._connexion() as cx:
            ligne = cx.execute("SELECT synchronise FROM pointages WHERE uuid = ?", (uuid_pointage,)).fetchone()
            if ligne is None:
                return
            cx.execute("UPDATE pointages SET annule = 1 WHERE uuid = ?", (uuid_pointage,))
            if ligne["synchronise"] == 0:
                cx.execute("UPDATE pointages SET synchronise = 3 WHERE uuid = ?", (uuid_pointage,))
            else:
                cx.execute("INSERT OR IGNORE INTO annulations (uuid) VALUES (?)", (uuid_pointage,))

    def en_attente(self, table: str, limite: int = 200) -> list[dict]:
        assert table in ("pointages", "tentatives", "annulations")
        colonnes = {"pointages": "uuid, matricule, horodatage, type, score, hors_ligne",
                    "tentatives": "uuid, horodatage, motif, matricule_suppose, score, hors_ligne",
                    "annulations": "uuid"}[table]
        ordre = "uuid" if table == "annulations" else "horodatage"
        with self._connexion() as cx:
            lignes = cx.execute(f"SELECT {colonnes} FROM {table} WHERE synchronise = 0 ORDER BY {ordre} LIMIT ?",
                                (limite,)).fetchall()
        resultat = [dict(l) for l in lignes]
        for r in resultat:
            if "hors_ligne" in r:
                r["hors_ligne"] = bool(r["hors_ligne"])
        return resultat

    def marquer_synchronises(self, table: str, uuids: list[str], erreurs: dict[str, str] | None = None) -> None:
        assert table in ("pointages", "tentatives", "annulations")
        with self._verrou, self._connexion() as cx:
            cx.executemany(f"UPDATE {table} SET synchronise = 1 WHERE uuid = ?", [(u,) for u in uuids])
            if erreurs and table == "pointages":
                # Pointage refusé par le serveur : conservé localement pour analyse, plus renvoyé.
                cx.executemany("UPDATE pointages SET synchronise = 2, erreur = ? WHERE uuid = ?",
                               [(e, u) for u, e in erreurs.items()])

    def nb_en_attente(self) -> int:
        with self._connexion() as cx:
            return cx.execute("SELECT COUNT(*) FROM pointages WHERE synchronise = 0").fetchone()[0]

    def dernier_pointage_du_jour(self, matricule: str) -> dict | None:
        debut = datetime.now().astimezone().date().isoformat()
        with self._connexion() as cx:
            l = cx.execute("SELECT type, horodatage FROM pointages WHERE matricule = ? AND horodatage >= ? "
                           "AND annule = 0 ORDER BY horodatage DESC LIMIT 1", (matricule, debut)).fetchone()
        return dict(l) if l else None

    # --- Identité du site et logo (pour s'afficher correctement même hors ligne)
    def sauver_site(self, config_serveur: dict) -> None:
        self.fichier_site.write_text(json.dumps(config_serveur, default=str), encoding="utf-8")

    def charger_site(self) -> dict:
        try:
            return json.loads(self.fichier_site.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def sauver_logo(self, contenu: bytes, type_mime: str) -> None:
        self.fichier_logo.write_bytes(contenu)
        self.fichier_logo.with_suffix(".type").write_text(type_mime)

    def charger_logo(self) -> tuple[bytes, str] | None:
        try:
            return self.fichier_logo.read_bytes(), self.fichier_logo.with_suffix(".type").read_text()
        except OSError:
            return None

    # --- Galerie biométrique (cache chiffré pour fonctionner hors ligne) ----
    def sauver_galerie(self, version: str, agents: list[dict]) -> None:
        donnees = self._fernet.encrypt(json.dumps({"version": version, "agents": agents}).encode())
        temporaire = self.fichier_galerie.with_suffix(".tmp")
        temporaire.write_bytes(donnees)
        temporaire.chmod(0o600)
        temporaire.replace(self.fichier_galerie)

    def charger_galerie(self) -> tuple[str, list[dict]]:
        if not self.fichier_galerie.exists():
            return "", []
        try:
            contenu = json.loads(self._fernet.decrypt(self.fichier_galerie.read_bytes()))
            return contenu["version"], contenu["agents"]
        except (InvalidToken, ValueError, KeyError):
            return "", []
