"""Configuration du serveur central (variables d'environnement ou server/.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

RACINE_SERVEUR = Path(__file__).resolve().parent.parent
load_dotenv(RACINE_SERVEUR / ".env")

DATABASE_URL = os.environ.get("EDM_DATABASE_URL", f"sqlite:///{RACINE_SERVEUR / 'edm_pointage.db'}")
CLE_JWT = os.environ.get("EDM_CLE_JWT", "")
# Clé Fernet (AES-128-CBC + HMAC-SHA256) pour chiffrer les gabarits biométriques.
CLE_BIOMETRIE = os.environ.get("EDM_CLE_BIOMETRIE", "")
DUREE_JETON_MINUTES = int(os.environ.get("EDM_DUREE_JETON_MINUTES", "480"))
# Un terminal est considéré en ligne s'il a contacté le serveur récemment.
DELAI_TERMINAL_EN_LIGNE_S = int(os.environ.get("EDM_DELAI_TERMINAL_EN_LIGNE_S", "120"))
MIN_IMAGES_ENROLEMENT = int(os.environ.get("EDM_MIN_IMAGES_ENROLEMENT", "3"))
# Adresse par laquelle les bornes et les téléphones joignent ce serveur (proposée avec chaque nouvelle clé).
URL_APPAREILS = os.environ.get("EDM_URL_PUBLIQUE", "").rstrip("/")

if not CLE_JWT or not CLE_BIOMETRIE:
    raise RuntimeError(
        "EDM_CLE_JWT et EDM_CLE_BIOMETRIE doivent être définies (server/.env). "
        "Lancez ./setup.sh pour les générer."
    )
