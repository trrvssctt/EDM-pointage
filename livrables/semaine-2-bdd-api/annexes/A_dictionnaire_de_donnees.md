# Annexe A — Dictionnaire de données

Généré automatiquement à partir du modèle de l'API (SQLAlchemy) et des commentaires du script `database/schema.sql`. Légende : **PK** clé primaire, **FK** clé étrangère, **U** valeur unique, **NN** valeur obligatoire.

### Table `agent_sites_autorises`

Sélection de sites de pointage autorisés pour un agent (si tous_sites = faux)

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `agent_id` | INTEGER | PK, FK → agents |  |
| `site_id` | INTEGER | PK, FK → sites |  |

### Table `agents`

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `matricule` | VARCHAR(20) | NN, U | Identifiant unique de l'agent |
| `nom` | VARCHAR(80) | NN |  |
| `prenom` | VARCHAR(80) | NN |  |
| `fonction` | VARCHAR(120) | NN |  |
| `email` | VARCHAR(120) | NN |  |
| `telephone` | VARCHAR(30) | NN |  |
| `service_id` | INTEGER | NN, FK → services |  |
| `site_rattachement_id` | INTEGER | NN, FK → sites |  |
| `horaire_id` | INTEGER | NN, FK → horaires |  |
| `tous_sites` | BOOLEAN | NN | Vrai : pointage autorisé sur tous les sites équipés ; faux : rattachement + sites_autorises |
| `consentement_le` | TIMESTAMP |  | Date du recueil du consentement au traitement biométrique (obligatoire pour enrôler) |
| `actif` | BOOLEAN | NN |  |
| `cree_le` | TIMESTAMP | NN |  |
| `modifie_le` | TIMESTAMP | NN |  |

### Table `demandes_enrolement`

Enrôlements proposés depuis l'application mobile, en attente de validation par la DRH

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `uuid` | VARCHAR(36) | NN, U | Identifiant créé par le téléphone : un renvoi depuis la file hors ligne ne crée pas de doublon |
| `agent_id` | INTEGER | NN, FK → agents |  |
| `appareil_id` | INTEGER | NN, FK → terminaux |  |
| `auteur_id` | INTEGER | NN, FK → utilisateurs |  |
| `photos_chiffrees` | BYTEA |  | Photos chiffrées, conservées uniquement jusqu'à la décision (validation ou rejet), puis effacées |
| `gabarits_chiffres` | BYTEA |  |  |
| `nb_photos` | INTEGER | NN |  |
| `vivacite` | BOOLEAN | NN |  |
| `controles` | TEXT | NN |  |
| `statut` | VARCHAR(20) | NN |  |
| `motif` | VARCHAR(300) | NN |  |
| `capture_le` | TIMESTAMP | NN |  |
| `cree_le` | TIMESTAMP | NN |  |
| `traite_par` | VARCHAR(60) | NN |  |
| `traite_le` | TIMESTAMP |  |  |

### Table `gabarits_faciaux`

Vecteurs biométriques (128 dimensions, SFace), un par pose, chiffrés par Fernet (AES-128 + HMAC). Aucune photo stockée.

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `agent_id` | INTEGER | NN, FK → agents |  |
| `pose` | VARCHAR(10) | NN |  |
| `donnees_chiffrees` | BYTEA | NN |  |
| `qualite` | DOUBLE PRECISION | NN |  |
| `cree_le` | TIMESTAMP | NN |  |

### Table `horaires`

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `nom` | VARCHAR(80) | NN, U |  |
| `heure_debut` | TIME | NN |  |
| `heure_fin` | TIME | NN |  |
| `tolerance_minutes` | INTEGER | NN | Au-delà, l'arrivée est comptée comme un retard |
| `jours_travailles` | VARCHAR(20) | NN | Jours travaillés : 0 = lundi ... 6 = dimanche |

### Table `journal_audit`

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `date` | TIMESTAMP | NN |  |
| `acteur` | VARCHAR(60) | NN |  |
| `action` | VARCHAR(60) | NN |  |
| `details` | TEXT | NN |  |
| `adresse_ip` | VARCHAR(45) | NN |  |

### Table `lots_synchronisation`

Journal des lots reçus : preuve que les renvois ne créent aucun doublon

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `date` | TIMESTAMP | NN |  |
| `terminal_id` | INTEGER | NN, FK → terminaux |  |
| `recus` | INTEGER | NN |  |
| `doublons` | INTEGER | NN |  |
| `rejetes` | INTEGER | NN |  |

### Table `organisation`

Identité de l'entreprise cliente : nom, logo et couleurs affichés sur l'administration, les terminaux et les rapports

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `nom` | VARCHAR(120) | NN |  |
| `sigle` | VARCHAR(30) | NN |  |
| `slogan` | VARCHAR(200) | NN |  |
| `couleur_primaire` | VARCHAR(7) | NN |  |
| `couleur_menu` | VARCHAR(7) | NN |  |
| `logo` | BYTEA |  |  |
| `logo_type` | VARCHAR(40) | NN |  |
| `prefixe_matricule` | VARCHAR(10) | NN |  |
| `deux_etapes_obligatoire_admin` | BOOLEAN | NN |  |
| `duree_conservation_jours` | INTEGER | NN | Au-delà, pointages, tentatives et journaux sont purgés automatiquement |
| `modifie_le` | TIMESTAMP | NN |  |

### Table `pointages`

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `uuid` | VARCHAR(36) | NN, U | Identifiant généré par le terminal : un événement n'est consolidé qu'une seule fois |
| `agent_id` | INTEGER | NN, FK → agents |  |
| `matricule` | VARCHAR(20) | NN |  |
| `horodatage` | TIMESTAMP | NN | Heure réelle du pointage sur le terminal |
| `type` | VARCHAR(10) | NN |  |
| `site_id` | INTEGER | NN, FK → sites |  |
| `terminal_id` | INTEGER | NN, FK → terminaux |  |
| `score` | DOUBLE PRECISION | NN |  |
| `hors_ligne` | BOOLEAN | NN | Vrai si enregistré pendant une coupure réseau puis synchronisé |
| `annule` | BOOLEAN | NN | Contesté par l'agent (« Ce n'est pas moi ») : exclu des présences, conservé pour la traçabilité |
| `secours` | BOOLEAN | NN | Pointage de secours effectué avec un téléphone de l'application terrain (borne en panne) |
| `recu_le` | TIMESTAMP | NN | Heure de réception par le serveur central |

### Table `services`

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `code` | VARCHAR(20) | NN, U |  |
| `nom` | VARCHAR(120) | NN |  |

### Table `sites`

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `code` | VARCHAR(20) | NN, U |  |
| `nom` | VARCHAR(120) | NN |  |
| `nom_court` | VARCHAR(60) | NN | Libellé affiché sur les terminaux et dans les tableaux (ex. « Siège · Bamako ») |
| `type` | VARCHAR(30) | NN |  |
| `ville` | VARCHAR(80) | NN |  |
| `actif` | BOOLEAN | NN | Interrupteur « Pointage autorisé » : un site non autorisé voit ses terminaux refusés |

### Table `tentatives_rejetees`

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `uuid` | VARCHAR(36) | NN, U |  |
| `horodatage` | TIMESTAMP | NN |  |
| `motif` | VARCHAR(40) | NN | VISAGE_INCONNU, ECHEC_VIVACITE, CHANGEMENT_VISAGE, SITE_NON_AUTORISE, IDENTITE_CONTESTEE, APPEL_SUPERVISEUR |
| `matricule_suppose` | VARCHAR(20) |  |  |
| `score` | DOUBLE PRECISION | NN |  |
| `terminal_id` | INTEGER | NN, FK → terminaux |  |
| `site_id` | INTEGER | NN, FK → sites |  |
| `hors_ligne` | BOOLEAN | NN |  |
| `traitee` | BOOLEAN | NN | Anomalie examinée par un responsable (retirée du tableau de bord) |

### Table `terminaux`

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `code` | VARCHAR(30) | NN, U |  |
| `libelle` | VARCHAR(120) | NN |  |
| `site_id` | INTEGER | NN, FK → sites |  |
| `empreinte_cle` | VARCHAR(64) | NN, U | SHA-256 de la clé d'API du terminal (la clé elle-même n'est jamais stockée) |
| `actif` | BOOLEAN | NN |  |
| `dernier_contact` | TIMESTAMP |  |  |
| `adresse_ip` | VARCHAR(45) | NN |  |
| `version` | VARCHAR(20) | NN |  |
| `nb_en_attente` | INTEGER | NN | Pointages stockés localement, déclarés par le terminal à chaque contact |
| `synchro_demandee` | BOOLEAN | NN | Consigne « Forcer la synchronisation » transmise au prochain contact |
| `type` | VARCHAR(10) | NN | BORNE : terminal fixe de pointage ; MOBILE : téléphone de l'application terrain (enrôlement, secours) |

### Table `utilisateurs`

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | INTEGER | PK |  |
| `identifiant` | VARCHAR(50) | NN, U |  |
| `email` | VARCHAR(120) | U |  |
| `nom_complet` | VARCHAR(120) | NN |  |
| `fonction` | VARCHAR(120) | NN |  |
| `mot_de_passe_hash` | VARCHAR(200) | NN | PBKDF2-HMAC-SHA256, sel aléatoire, 240 000 itérations |
| `role` | VARCHAR(20) | NN |  |
| `service_id` | INTEGER | FK → services | Périmètre d'un responsable habilité : son service et/ou son site |
| `site_id` | INTEGER | FK → sites |  |
| `actif` | BOOLEAN | NN |  |
| `echecs_connexion` | INTEGER | NN |  |
| `bloque_jusqua` | TIMESTAMP |  | Verrouillage temporaire après 5 échecs de connexion |
| `derniere_connexion` | TIMESTAMP |  |  |
| `secret_totp` | VARCHAR(255) |  | Secret de la vérification en deux étapes (TOTP), chiffré |
| `deux_etapes` | BOOLEAN | NN |  |
| `reinitialisation_demandee` | BOOLEAN | NN |  |
| `cree_le` | TIMESTAMP | NN |  |
