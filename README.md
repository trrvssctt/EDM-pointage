# Pointage biométrique multisite — Énergie du Mali (EDM S.A.)

Application de gestion des présences par **reconnaissance faciale**, conçue pour une organisation
multisite : un agent enrôlé une seule fois pointe sur **n'importe quel site équipé et autorisé**,
les terminaux continuent de fonctionner **pendant les coupures réseau** et se synchronisent
ensuite **sans jamais créer de doublon**.

La solution est en **marque blanche** : nom, logo, couleurs et préfixe de matricule se règlent
dans *Paramètres*, ce qui permet de la déployer pour n'importe quelle entreprise.

| Composant | Rôle | Technologies |
|---|---|---|
| Serveur central | API, base de données, calculs de présence, exports | Python 3.10+, FastAPI, SQLAlchemy, PostgreSQL (SQLite en démonstration) |
| Interface d'administration | Tableau de bord, agents, enrôlement, pointages, rapports, sites, utilisateurs | React 18, TypeScript, Vite, Tailwind CSS, TanStack Query |
| Terminal de pointage | Caméra, reconnaissance, anti-fraude, file hors ligne, écran tactile kiosque | Service Python (FastAPI + OpenCV) et écran React en mode kiosque |
| Reconnaissance faciale | Détection, gabarit 128 dimensions, vivacité | OpenCV 4 : YuNet (détection), SFace (reconnaissance), Haar (yeux) |

Documentation complémentaire :
[architecture et sécurité](docs/architecture.md) · [application mobile iPhone](docs/application-mobile.md) ·
[fiche de test](docs/Fiche_de_test_pointage_biometrique.xlsx) ·
[script de base de données](database/schema.sql).

---

## 1. Installation

### Prérequis

- Linux (Ubuntu 22.04+ conseillé), macOS ou Windows avec WSL2
- **Python 3.10 ou plus**, **Node.js 18 ou plus** (avec npm), `curl`
- Une webcam (USB ou intégrée) pour l'enrôlement et pour chaque terminal
- Accès Internet lors de l'installation (téléchargement des dépendances et des modèles, ~40 Mo)

### Installation automatique

```bash
./setup.sh            # installation + base de démonstration (sites, agents fictifs, 3 semaines d'historique)
./setup.sh --vierge   # installation + base vide (organisation, comptes et terminaux uniquement)
```

Le script :
1. crée l'environnement Python `.venv` et installe les dépendances (`requirements.txt`) ;
2. compile les interfaces web (`frontend/` → `frontend/dist/`) ;
3. télécharge les modèles OpenCV Zoo dans `models/` ;
4. génère les clés secrètes dans `server/.env` (signature des sessions, chiffrement biométrique) ;
5. initialise la base et écrit la configuration de chaque terminal dans `terminal/config/`.

> **Sauvegardez `server/.env`.** La clé `EDM_CLE_BIOMETRIE` chiffre les gabarits : sans elle,
> tous les agents devraient être ré-enrôlés.

### Lancement

```bash
./run_server.sh                    # serveur central : http://127.0.0.1:8000  (API documentée sur /docs)
./run_terminal.sh TRM-BKO-03       # terminal du siège : écran kiosque http://127.0.0.1:8100
```

Pour rendre le serveur accessible aux terminaux du réseau : `HOTE=0.0.0.0 ./run_server.sh`,
puis renseigner `url_serveur` dans le fichier `terminal/config/<CODE>.json` de chaque terminal.

### Comptes de démonstration

| Identifiant | Mot de passe | Profil | Périmètre |
|---|---|---|---|
| `admin` | `Admin@2026` | Administrateur | Tous les sites |
| `drh` (ou `f.maiga@edm.example`) | `Drh@2026` | Direction des RH | Tous les sites |
| `resp.sikasso` | `Resp@2026` | Responsable habilité | DR Sikasso |
| `resp.sotuba` | `Resp@2026` | Responsable habilité | Maintenance · Centre technique Sotuba |

**Changez ces mots de passe avant toute mise en service** (*Mon compte* ou *Utilisateurs et droits*).

### Base PostgreSQL (production)

```bash
createdb -U postgres edm_pointage
psql -U postgres -d edm_pointage -f database/schema.sql
.venv/bin/pip install "psycopg[binary]"
echo 'EDM_DATABASE_URL=postgresql+psycopg://edm:motdepasse@localhost:5432/edm_pointage' >> server/.env
.venv/bin/python -m server.seed            # organisation, comptes et terminaux initiaux
```

---

## 2. Utilisation

### Administration (navigateur : PC, tablette ou smartphone)

| Écran | Profils | Fonctions |
|---|---|---|
| **Tableau de bord** | Tous (selon périmètre) | Présents, retards, absences, pointages en attente de synchronisation, présence par site, 7 derniers jours, anomalies à traiter, état des terminaux, export Excel de la journée |
| **Agents** | Tous (responsable : son périmètre) | Recherche, filtres, création, modification, désactivation, sites de pointage autorisés, suppression du gabarit |
| **Enrôlement** | Administrateur, DRH | Capture guidée de 5 poses (face, gauche, droite, haut, bas) avec contrôle qualité en direct, test de vivacité et consentement |
| **Pointages** | Tous (selon périmètre) | Historique des entrées, sorties et refus ; filtres par période, site, terminal, type, alerte ; export Excel |
| **Rapports** | Tous (selon périmètre) | Présence, retards, absences par service, site ou agent ; export **PDF** et **Excel** |
| **Sites et terminaux** | Administrateur (DRH en lecture) | Autoriser ou suspendre le pointage d'un site, enregistrer un terminal (clé + fichier de configuration), forcer la synchronisation, journal des lots |
| **Utilisateurs et droits** | Administrateur (DRH en lecture) | Comptes, profils, périmètres, matrice des droits, journal d'audit |
| **Paramètres** | Administrateur | Nom, logo, couleurs, préfixe des matricules, vérification en deux étapes obligatoire, durée de conservation |
| **Mon compte** | Tous | Mot de passe, vérification en deux étapes (application d'authentification) |

**Enrôler un agent** : *Agents › Nouvel agent* (ou *Enrôler* sur un agent existant), placer l'agent
face à la caméra du poste RH, suivre les consignes : chaque pose est capturée automatiquement
quand elle est correcte. Cocher le consentement puis *Valider l'enrôlement*. Les terminaux
reçoivent le nouvel agent à leur prochaine synchronisation (10 secondes par défaut).

**Ajouter un terminal** : *Sites et terminaux › Enregistrer un terminal* → télécharger le fichier
de configuration proposé (la clé n'est affichée qu'une fois), le copier dans
`terminal/config/` du poste de pointage, puis `./run_terminal.sh <CODE>`.

### Terminal de pointage (écran tactile)

1. L'agent se place face à la caméra, dans l'ovale.
2. Après une seconde d'immobilité, le terminal l'identifie puis lance un **contrôle anti-fraude**
   tiré au hasard : *tourner la tête* vers la droite ou la gauche, ou *cligner des yeux*.
3. Le pointage est enregistré (entrée ou sortie, déduite du dernier pointage de la journée, tous
   sites confondus). Le type peut être forcé avec les boutons *Entrée* / *Sortie*.
4. *Ce n'est pas moi* annule le pointage et trace la contestation.
5. Sans réseau, le bandeau passe à *Hors ligne · enregistrement local* : les pointages sont
   conservés sur le terminal et transmis automatiquement au retour du réseau.

### Démonstration du pointage multisite sans caméra

Le simulateur utilise la même file locale et la même synchronisation que le vrai terminal :

```bash
./run_server.sh &                                    # serveur démarré
.venv/bin/python -m terminal.simulateur --config terminal/config/TRM-SEL-01.json EDM-001864   # entrée à Sélingué
.venv/bin/python -m terminal.simulateur --config terminal/config/TRM-BKO-03.json EDM-001864   # sortie au siège
# Coupure réseau : arrêter le serveur, pointer, redémarrer le serveur, relancer avec --etat
```

---

## 3. Application mobile terrain (iPhone, Expo Go)

Application React Native (Expo SDK 58, TypeScript) dans `mobile/` : enrôlement photographié sur le
terrain puis **validé par la DRH** (web › Enrôlement › À valider), pointage de secours, file d'envoi
hors ligne. Détails : [docs/application-mobile.md](docs/application-mobile.md).

```bash
HOTE=0.0.0.0 ./run_server.sh                         # serveur joignable depuis le Wi-Fi
cd mobile && nvm use 22 && npm install --legacy-peer-deps
npx expo start --lan                                  # QR code à scanner avec l'iPhone (Expo Go)
```

Enregistrer le téléphone : *Sites et terminaux › Enregistrer un terminal › Téléphone* (ou *Nouvelle
clé* sur `MOB-BKO-07`), puis scanner le QR code affiché depuis l'application. L'iPhone et le PC
doivent être sur le même réseau Wi-Fi.

## 4. Déploiement sur serveur

Voir [deploy/DEPLOIEMENT.md](deploy/DEPLOIEMENT.md) : base PostgreSQL en conteneur, API gérée par PM2, accès public par
Nginx (`./deploy/installer_vps.sh`, puis `./deploy/mettre_a_jour.sh` à chaque mise à jour).

## 5. Tests

```bash
.venv/bin/python -m pytest              # 64 tests automatisés (API, sécurité, multisite, hors ligne, terminal, mobile)
cd frontend && npm run typecheck        # vérification TypeScript des interfaces
```

La campagne complète, y compris les essais manuels sur chaque équipement (PC, tablette,
smartphone, terminal kiosque, caméras), figure dans la
[fiche de test](docs/Fiche_de_test_pointage_biometrique.xlsx).

---

## 6. Organisation du code

```
server/            serveur central (FastAPI)
  app/routers/     API : authentification, organisation, référentiels, agents, pointages, terminaux
  app/services/    présences, biométrie, exports PDF/Excel, purge de conservation
  seed.py          initialisation (et données de démonstration)
terminal/          terminal de pointage
  service.py       service local : caméra, automate de pointage, écran kiosque
  noyau.py         règles métier (entrée/sortie, sites autorisés, anti-rebond, annulation)
  stockage_local.py  file hors ligne SQLite + cache chiffré de la galerie
  synchronisation.py échanges avec le serveur central
  simulateur.py    pointages simulés (démonstration, tests)
common/            moteur facial (YuNet + SFace) et contrôle de vivacité
frontend/          interfaces React + TypeScript (administration et écran du terminal)
mobile/            application iPhone React Native + Expo (enrôlement terrain, secours, file d'envoi)
database/          script de création PostgreSQL
tests/             tests automatisés (pytest)
docs/              architecture, sécurité, fiche de test
deploy/            installation et mise à jour sur le VPS (PM2, Nginx, PostgreSQL)
livrables/         livrables par semaine (document, annexes, génération PDF)
```
