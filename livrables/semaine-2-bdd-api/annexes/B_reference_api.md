# Annexe B — Référence de l'API centrale

63 points d'accès, générés à partir du schéma OpenAPI de l'API (fichier `openapi.json` joint, importable dans Postman, Insomnia ou Swagger Editor). La documentation interactive est servie par l'API elle-même sur `/docs` (essais directs) et `/redoc`.

Authentification : **jeton** = `Authorization: Bearer <jeton de session>` ; **clé appareil** = `X-Terminal-Key: <clé du terminal ou du téléphone>` ; **public** = sans authentification.

### Agents et enrôlement

| Méthode | Chemin | Authentification | Description |
|---|---|---|---|
| `GET` | `/api/agents` | jeton | Liste paginée des agents du périmètre de l'utilisateur, avec recherche et filtres (service, site, statut, enrôlement). |
| `POST` | `/api/agents` | jeton | Création d'un dossier agent (matricule unique, service, site de rattachement, horaire, sites autorisés). |
| `GET` | `/api/agents/{agent_id}` | jeton | Dossier d'un agent. |
| `PUT` | `/api/agents/{agent_id}` | jeton | Modification ou désactivation d'un dossier agent. |
| `POST` | `/api/agents/enrolement/analyse` | jeton | Contrôle qualité en direct pendant la capture (aucune image n'est conservée). |
| `POST` | `/api/agents/{agent_id}/enrolement` | jeton | Enrôlement depuis le poste RH : 5 poses, consentement, contrôles (vivacité, photo de face, cohérence, unicité) puis gabarits chiffrés. |
| `DELETE` | `/api/agents/{agent_id}/gabarits` | jeton | Suppression des données biométriques d'un agent (droit à l'effacement). |
| `GET` | `/api/enrolements/demandes` | jeton | Enrôlements proposés depuis l'application mobile, à valider par la DRH. |
| `GET` | `/api/enrolements/demandes/{uuid}` | jeton | Détail avec les photos (déchiffrées pour l'affichage, jamais stockées en clair). |
| `POST` | `/api/enrolements/demandes/{uuid}/valider` | jeton | Validation d'une demande : enregistrement des gabarits chiffrés, effacement des photos. |
| `POST` | `/api/enrolements/demandes/{uuid}/rejeter` | jeton | Rejet motivé d'une demande ; les photos sont effacées. |

### Application mobile

| Méthode | Chemin | Authentification | Description |
|---|---|---|---|
| `POST` | `/api/mobile/connexion` | clé appareil | Connexion d'un utilisateur, uniquement depuis un téléphone enregistré. |
| `GET` | `/api/mobile/accueil` | clé appareil + jeton | Écran d'accueil : utilisateur, appareil, droits et activité récente de l'appareil. |
| `POST` | `/api/mobile/enrolements` | clé appareil + jeton | Envoi idempotent d'un enrôlement photographié sur le terrain ; contrôles immédiats, puis attente de validation DRH. |
| `GET` | `/api/mobile/enrolements/{uuid}` | clé appareil + jeton | Suivi d'une demande d'enrôlement (reçue, gabarit calculé, validée, rejetée). |
| `POST` | `/api/mobile/secours` | clé appareil + jeton | Pointage photographié par un responsable quand la borne du site est en panne. |
| `POST` | `/api/mobile/secours/{uuid}/annuler` | clé appareil + jeton | « Ce n'est pas moi » sur l'écran de résultat. |

### Authentification et utilisateurs

| Méthode | Chemin | Authentification | Description |
|---|---|---|---|
| `POST` | `/api/auth/connexion` | public | Connexion par identifiant, matricule ou e-mail ; renvoie un jeton de session, ou demande le code de vérification en deux étapes. |
| `POST` | `/api/auth/deux-etapes` | public | Seconde étape de connexion : vérifie le code à 6 chiffres (TOTP) et ouvre la session. |
| `POST` | `/api/auth/mot-de-passe-oublie` | public | Signale la demande à l'administrateur (réinitialisation manuelle, sans envoi d'e-mail). |
| `GET` | `/api/auth/session` | jeton | Utilisateur connecté et droits effectifs de son profil. |
| `POST` | `/api/auth/mot-de-passe` | jeton | Changement de son propre mot de passe (règle de robustesse appliquée). |
| `POST` | `/api/auth/deux-etapes/preparer` | jeton | Génère un secret et le QR code à scanner avec une application d'authentification. |
| `POST` | `/api/auth/deux-etapes/activer` | jeton | Active la vérification en deux étapes après saisie d'un premier code valide. |
| `GET` | `/api/utilisateurs` | jeton | Liste des comptes utilisateurs avec profil, périmètre et dernière connexion (administrateur, DRH). |
| `POST` | `/api/utilisateurs` | jeton | Création d'un compte utilisateur (administrateur). |
| `GET` | `/api/droits` | jeton | Matrice des droits par profil (Oui / Non / Son périmètre). |
| `PUT` | `/api/utilisateurs/{utilisateur_id}` | jeton | Modification d'un compte : profil, périmètre, activation, nouveau mot de passe, réinitialisation de la 2FA. |
| `GET` | `/api/audit` | jeton | Journal d'audit des actions sensibles, filtrable par utilisateur et par action. |

### Organisation

| Méthode | Chemin | Authentification | Description |
|---|---|---|---|
| `GET` | `/api/organisation` | public | Public : nécessaire à l'affichage de l'écran de connexion et des terminaux. |
| `PUT` | `/api/organisation` | jeton | Modification de l'identité de l'organisation (nom, couleurs, préfixe des matricules) et de la politique de sécurité. |
| `GET` | `/api/organisation/logo` | public | Logo de l'organisation (public). |
| `POST` | `/api/organisation/logo` | jeton | Corps : {"image": "data:image/png;base64,..."} (500 Ko maximum). |

### Pointages, tableau de bord et rapports

| Méthode | Chemin | Authentification | Description |
|---|---|---|---|
| `GET` | `/api/pointages` | jeton | Historique unifié des pointages et des refus, filtrable (période, site, terminal, type, alerte, agent), paginé. |
| `GET` | `/api/pointages/export.xlsx` | jeton | Export Excel de l'historique filtré. |
| `POST` | `/api/tentatives/{tentative_id}/traiter` | jeton | Marque une tentative refusée (fraude, appel superviseur) comme traitée. |
| `GET` | `/api/tableau-de-bord` | jeton | Indicateurs du jour : présents, retards, absences, pointages en attente, présence par site, 7 jours, anomalies, terminaux. |
| `GET` | `/api/tableau-de-bord/export.xlsx` | jeton | « Exporter la journée » : présences de chaque agent et liste des pointages. |
| `GET` | `/api/rapports` | jeton | Rapport de présence, de retards ou d'absences par service, site ou agent sur une période. |
| `GET` | `/api/rapports/export.xlsx` | jeton | Export Excel du rapport (synthèse + détail journalier). |
| `GET` | `/api/rapports/export.pdf` | jeton | Export PDF du rapport aux couleurs de l'organisation. |

### Sites, terminaux et référentiels

| Méthode | Chemin | Authentification | Description |
|---|---|---|---|
| `GET` | `/api/services` | jeton | Liste des services. |
| `POST` | `/api/services` | jeton | Création d'un service. |
| `GET` | `/api/sites` | jeton | Liste des sites avec nombre de bornes, état agrégé et effectif rattaché. |
| `POST` | `/api/sites` | jeton | Création d'un site. |
| `PUT` | `/api/sites/{site_id}` | jeton | Modification d'un site. |
| `PATCH` | `/api/sites/{site_id}/pointage` | jeton | Interrupteur « Pointage autorisé » de l'écran Sites et terminaux. |
| `GET` | `/api/horaires` | jeton | Liste des horaires de travail (début, fin, tolérance, jours travaillés). |
| `POST` | `/api/horaires` | jeton | Création d'un horaire de travail. |
| `GET` | `/api/terminaux` | jeton | Liste des terminaux et téléphones : état, dernier contact, version, pointages en attente. |
| `POST` | `/api/terminaux` | jeton | Enregistrement d'une borne ou d'un téléphone ; la clé d'accès n'est renvoyée qu'une seule fois. |
| `PUT` | `/api/terminaux/{terminal_id}` | jeton | Modification d'un terminal (emplacement, site, activation). |
| `POST` | `/api/terminaux/{terminal_id}/nouvelle-cle` | jeton | Génère une nouvelle clé d'accès ; l'ancienne est immédiatement invalidée. |
| `POST` | `/api/terminaux/{terminal_id}/synchroniser` | jeton | Le terminal reçoit la consigne à son prochain contact et envoie immédiatement sa file d'attente. |
| `GET` | `/api/synchronisation/lots` | jeton | Journal des lots reçus des terminaux (reçus, doublons ignorés, refusés). |

### Supervision

| Méthode | Chemin | Authentification | Description |
|---|---|---|---|
| `GET` | `/api/sante` | public | Disponibilité du serveur (supervision). |

### Terminaux de pointage

| Méthode | Chemin | Authentification | Description |
|---|---|---|---|
| `GET` | `/api/terminal/configuration` | clé appareil | Contacté à chaque cycle : identité du site, marque de l'organisation et consignes en attente. |
| `GET` | `/api/terminal/logo` | clé appareil | Logo de l'organisation pour l'écran du terminal. |
| `GET` | `/api/terminal/galerie` | clé appareil | Galerie des gabarits des agents actifs (versionnée : rien n'est renvoyé si elle est inchangée). |
| `GET` | `/api/terminal/etat-agent/{matricule}` | clé appareil | Dernier pointage du jour, tous sites confondus : permet de déduire ENTRÉE / SORTIE. |
| `POST` | `/api/terminal/pointages` | clé appareil | Réception idempotente : un événement (uuid) n'est enregistré qu'une seule fois. |
| `POST` | `/api/terminal/tentatives` | clé appareil | Réception idempotente des tentatives refusées (visage inconnu, fraude, contestation, appel superviseur). |
| `POST` | `/api/terminal/annulations` | clé appareil | « Ce n'est pas moi » : annule un pointage déjà transmis (seulement depuis le terminal émetteur). |
