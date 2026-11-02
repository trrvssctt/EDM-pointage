---
title: "Livrable n° 2 — Base de données PostgreSQL et API centrale"
subtitle: "Système de pointage biométrique multisite par reconnaissance faciale"
author: "Énergie du Mali (EDM S.A.) — Projet de fin d'études"
date: "Semaine 2 sur 3 — 31 octobre 2026 — version 1.0"
lang: fr
---

# Fiche du livrable

| | |
|---|---|
| **Projet** | Conception et réalisation d'un système de pointage biométrique par reconnaissance faciale pour EDM S.A. |
| **Livrable** | n° 2 — Base de données PostgreSQL et API centrale |
| **Calendrier** | Semaine 1 : analyse et conception · **Semaine 2 : base de données et API centrale** · Semaine 3 : interfaces (administration web, bornes, application mobile), tests sur site et mémoire |
| **Version** | 1.0 du 31/10/2026 |
| **Contenu remis** | Le présent document, le script `schema.sql`, le schéma `openapi.json`, le code source de l'API (`server/`), les tests automatisés (`tests/`) et les rapports d'exécution |

## Résumé

La base de données centrale et l'API qui l'expose sont **réalisées, documentées et validées sur PostgreSQL 16** :

| Indicateur | Résultat |
|---|---|
| Tables / vues de reporting | **14 tables**, **3 vues** |
| Contraintes d'intégrité | 18 clés étrangères, 11 contrôles `CHECK`, unicités (matricule, identifiants d'événements, clés d'appareils), 9 index |
| Points d'accès de l'API | **63**, documentés en français (`/docs`, annexe B, fichier `openapi.json`) |
| Tests automatisés | **66 / 66 réussis sur PostgreSQL 16**, 66 / 66 sur SQLite |
| Cohérence script SQL / code de l'API | **0 écart** sur 14 tables (contrôle automatique colonne par colonne) |
| Temps de réponse (2 016 pointages, 77 agents) | 50 à 420 ms selon la requête (§ 5.4) |

Les exigences du cahier des charges qui relèvent de la base et de l'API (identifiant unique, pointage multisite, unicité des
événements, traçabilité, sécurité biométrique, continuité de service, confidentialité) sont **toutes couvertes et testées**
(§ 2). Les interfaces utilisateur font l'objet du livrable n° 3.

\newpage

# 1. Objet et périmètre

Ce livrable fournit le **socle central** du système : la base de données qui conserve les agents, leurs gabarits
biométriques, les sites, les terminaux et les pointages, et l'**API REST** par laquelle passent **tous** les échanges.
Aucun client (administration web, borne de pointage, application mobile) n'accède directement à la base : cette règle
garantit que les droits, le chiffrement, les contrôles et la traçabilité s'appliquent toujours.

![Architecture générale : l'API centrale est le seul point d'accès à la base](images/02_architecture.png){width=95%}

**Inclus dans ce livrable :** modèle de données, script de création PostgreSQL, API centrale complète (authentification,
habilitations, agents, enrôlement, pointages, synchronisation, rapports, exports, audit), tests automatisés.

**Hors livrable (semaine 3) :** interfaces d'administration, écran des bornes, application mobile, essais sur site avec
du matériel réel, mémoire. Ces composants consomment l'API décrite ici sans la modifier.

# 2. Couverture des exigences

| Exigence (cahier des charges) | Réponse de la base et de l'API | Vérification |
|---|---|---|
| Agents dans une base centralisée | Table `agents`, API `/api/agents` (création, modification, désactivation, recherche) | tests « agents » |
| **Identifiant unique** (matricule) | Index unique `ix_agents_matricule` ; refus 409 en cas de doublon ; un même visage ne peut appartenir à deux agents | `test_creation_et_unicite_du_matricule`, `test_un_visage_ne_peut_appartenir_qu_a_un_agent` |
| Enrôlement à partir du visage | Gabarits SFace (128 valeurs) par pose, chiffrés ; contrôles de qualité, de vivacité, de cohérence et d'unicité | tests « enrôlement » (8) |
| **Pointage multisite** sans nouvel enrôlement | Galerie centrale distribuée à tous les terminaux ; sites autorisés par agent (`tous_sites`, `agent_sites_autorises`) | `test_pointage_sur_un_site_different_du_rattachement`, `test_entree_sur_un_site_sortie_sur_un_autre` |
| Date, heure, matricule, site, terminal | Colonnes `horodatage`, `matricule`, `site_id` (lieu réel), `terminal_id`, `type` de chaque pointage | `test_pointage_differe_conserve_son_heure_reelle` |
| Entrées, sorties, horaires | Type ENTRÉE / SORTIE ; table `horaires` (début, fin, tolérance, jours travaillés) | `test_rapport_presence_retard_absence` |
| Historique, rapports présence / retard / absence | `/api/pointages`, `/api/rapports` (+ exports PDF et Excel) par agent, service, site, période | tests « rapports et exports » |
| Utilisateurs et droits | 3 profils, matrice des droits appliquée côté serveur, périmètre service et/ou site | tests « habilitations » (9) |
| **Fiabilité** : un événement enregistré une seule fois | UUID créé par le terminal + contrainte `UNIQUE` ; renvois reconnus comme doublons et journalisés | `test_un_evenement_n_est_enregistre_qu_une_fois` |
| **Traçabilité** du site et du terminal | Site et terminal sur chaque pointage ; heure de réception ; journal d'audit ; lots de synchronisation | `test_actions_sensibles_tracees_dans_l_audit` |
| **Sécurité** des données biométriques | Gabarits chiffrés (Fernet : AES-128 + HMAC-SHA256), aucune photo conservée, consentement obligatoire, droit à l'effacement | `test_enrolement_chiffre_les_gabarits`, `test_suppression_des_donnees_biometriques` |
| **Disponibilité** en cas de coupure | Protocole de synchronisation idempotent ; heure réelle conservée ; consigne « forcer la synchronisation » | `test_pointages_conserves_hors_ligne_puis_synchronises` |
| **Confidentialité** selon les habilitations | Jeton signé, verrouillage après 5 échecs, double authentification, périmètres | `test_responsable_limite_a_son_service`, `test_verification_en_deux_etapes` |

\newpage

# 3. Base de données PostgreSQL

## 3.1 Choix de PostgreSQL

PostgreSQL est retenu pour sa **fiabilité transactionnelle** (aucun pointage partiellement enregistré), ses **contraintes
d'intégrité** (unicité, clés étrangères, contrôles `CHECK`) qui protègent les données même en cas d'erreur applicative,
ses **vues** utiles au reporting, ses outils de sauvegarde (`pg_dump`) et sa gratuité. L'API utilise l'ORM SQLAlchemy :
le même code fonctionne sur SQLite, utilisé pour le développement et les démonstrations sans installation.

## 3.2 Modèle de données

![Modèle conceptuel des données](images/04_modele_donnees.png){width=100%}

Les 14 tables se répartissent en cinq domaines :

| Domaine | Tables | Rôle |
|---|---|---|
| Organisation et référentiels | `organisation`, `services`, `sites`, `horaires` | Identité de l'entreprise (marque blanche), structure, horaires de travail |
| Agents et biométrie | `agents`, `agent_sites_autorises`, `gabarits_faciaux`, `demandes_enrolement` | Dossiers, sites autorisés, gabarits chiffrés, enrôlements à valider |
| Terminaux et pointages | `terminaux`, `pointages`, `tentatives_rejetees`, `lots_synchronisation` | Bornes et téléphones, événements, refus et fraudes, preuves de synchronisation |
| Accès | `utilisateurs` | Comptes, profils, périmètres, double authentification |
| Traçabilité | `journal_audit` | Toutes les actions sensibles |

Le dictionnaire de données complet (colonnes, types, contraintes, descriptions) figure en **annexe A**.

## 3.3 Règles d'intégrité garanties par la base

| Règle | Mise en œuvre |
|---|---|
| Un matricule par agent | `CREATE UNIQUE INDEX ix_agents_matricule` |
| Un événement enregistré une seule fois | `CONSTRAINT uq_pointage_uuid UNIQUE (uuid)` (de même pour les tentatives et les demandes d'enrôlement) |
| Clé d'appareil jamais stockée en clair, unique | `terminaux.empreinte_cle` (SHA-256) `UNIQUE` |
| Valeurs autorisées | `CHECK` sur type de pointage, type de site, type d'appareil, profil, statut de demande, pose, couleurs, durée de conservation |
| Un responsable a toujours un périmètre | `CHECK (role <> 'RESPONSABLE' OR service_id IS NOT NULL OR site_id IS NOT NULL)` |
| Suppression d'un agent | gabarits, sites autorisés et demandes supprimés en cascade (`ON DELETE CASCADE`) ; ses pointages, eux, bloquent la suppression : un agent se **désactive** |
| Recherche rapide | 9 index (matricule, horodatage, site, agent, dates de journal) |

## 3.4 Vues de reporting

| Vue | Contenu |
|---|---|
| `v_presences_journalieres` | Par agent et par jour : première entrée, dernière sortie, nombre de pointages, pointage hors rattachement, synchronisation différée (hors pointages annulés) |
| `v_pointages_multisites` | Pointages effectués sur un site différent du site de rattachement (mobilité) |
| `v_etat_terminaux` | État de chaque terminal : en ligne, hors ligne, synchronisation en cours, désactivé, jamais connecté |

Ces vues permettent à la DSI d'EDM S.A. d'interroger la base directement (outils de BI, requêtes ponctuelles) sans
passer par l'API.

## 3.5 Protection des données personnelles

- **Gabarits biométriques chiffrés** avant écriture (Fernet, AES-128-CBC + HMAC-SHA256) avec une clé conservée **hors de la
  base** (`server/.env`) : une copie volée de la base ne permet pas d'exploiter les données biométriques.
- **Aucune photo conservée** : seuls les gabarits sont stockés. Les photos d'un enrôlement proposé depuis le terrain sont
  chiffrées puis **effacées dès la décision** de la DRH.
- **Mots de passe** hachés (PBKDF2-HMAC-SHA256, 240 000 itérations, sel aléatoire) ; **secrets de double authentification**
  chiffrés.
- **Consentement** horodaté (`agents.consentement_le`) obligatoire pour enrôler ; **effacement** sur demande.
- **Durée de conservation** paramétrable (5 ans par défaut) : purge automatique quotidienne des pointages, tentatives et
  journaux plus anciens, elle-même tracée.

## 3.6 Installation

```bash
createdb -U postgres edm_pointage
psql -U postgres -d edm_pointage -f database/schema.sql
pip install "psycopg[binary]"
# server/.env : EDM_DATABASE_URL=postgresql+psycopg://edm:motdepasse@serveur:5432/edm_pointage
python -m server.seed        # organisation, comptes et terminaux initiaux (--demo : données fictives)
```

Le script `schema.sql` (annexe jointe) est commenté : chaque table et chaque colonne sensible porte une description
lisible dans les outils PostgreSQL (`\d+ pointages` dans `psql`). Il prévoit en commentaire la création d'un rôle
applicatif à privilèges minimaux.

\newpage

# 4. API centrale

## 4.1 Technologies

| Élément | Choix | Justification |
|---|---|---|
| Langage | Python 3.12+ | Langage de référence de la vision par ordinateur : la même base de code sert l'API et la reconnaissance faciale |
| Cadre web | FastAPI | API REST typée, validation automatique des données, documentation OpenAPI générée (`/docs`) |
| Accès aux données | SQLAlchemy 2 | Requêtes paramétrées (protection contre l'injection SQL), indépendance vis-à-vis du moteur |
| Reconnaissance faciale | OpenCV 4 : YuNet (détection) et SFace (gabarits) | Modèles légers et libres, fonctionnant sans GPU ni service externe : les données biométriques restent chez EDM |
| Exports | openpyxl (Excel), ReportLab (PDF) | Rapports aux couleurs de l'organisation |

## 4.2 Organisation du code

| Module (`server/app/`) | Responsabilité |
|---|---|
| `routers/auth.py` | Connexion, double authentification, comptes, matrice des droits, audit |
| `routers/agents.py`, `routers/enrolements.py` | Dossiers agents, enrôlement, validation des enrôlements proposés |
| `routers/pointages.py` | Historique, tableau de bord, rapports, exports |
| `routers/referentiels.py` | Services, sites, horaires, terminaux, journal de synchronisation |
| `routers/terminal_api.py`, `routers/mobile.py` | Échanges avec les bornes et les téléphones (galerie, pointages, synchronisation) |
| `routers/organisation.py` | Identité de l'organisation (nom, logo, couleurs) |
| `services/` | Calcul des présences, biométrie, exports, purge de conservation |
| `securite.py` | Jetons, droits, périmètres, chiffrement, audit |

## 4.3 Conventions

- **Format** : JSON en UTF-8 ; dates au format ISO 8601 (`2026-10-31T08:02:14`), heure locale du Mali (GMT).
- **Pagination** : paramètres `page` et `taille` ; réponse `{ "total": …, "elements": [ … ] }`.
- **Erreurs** : code HTTP explicite et message en français dans `detail` :

| Code | Signification | Exemple de réponse |
|---|---|---|
| 400 | Donnée invalide | `{"detail": "Le consentement de l'agent est requis"}` |
| 401 | Non authentifié | `{"detail": "Authentification requise"}` |
| 403 | Profil ou appareil non autorisé | `{"detail": "Votre profil ne permet pas cette action"}` |
| 404 | Introuvable ou hors périmètre | `{"detail": "Agent introuvable ou hors de votre périmètre"}` |
| 409 | Doublon | `{"detail": "Le matricule EDM-004217 existe déjà"}` |
| 422 | Contrôle métier refusé | `{"detail": {"message": "Enrôlement refusé : …", "images_rejetees": […]}}` |
| 423 | Compte verrouillé | `{"detail": "Compte temporairement bloqué après plusieurs échecs…"}` |

## 4.4 Authentification

Deux types de clients, deux mécanismes :

| Client | Mécanisme | En-tête |
|---|---|---|
| Personne (administrateur, DRH, responsable) | Identifiant, matricule ou e-mail + mot de passe (+ code à 6 chiffres si la double authentification est active) → **jeton de session signé** (JWT HS256, 8 h, ou 30 jours avec « Rester connecté ») | `Authorization: Bearer <jeton>` |
| Appareil (borne, téléphone) | **Clé d'accès individuelle** générée à l'enregistrement de l'appareil ; seule son empreinte SHA-256 est conservée ; révocable à tout moment | `X-Terminal-Key: <clé>` |
| Téléphone utilisé par une personne | Les deux à la fois : l'appareil doit être enregistré **et** l'utilisateur connecté | les deux en-têtes |

Exemple réel de connexion :

```http
POST /api/auth/connexion
{"identifiant": "drh", "mot_de_passe": "••••••••", "rester_connecte": false}
```
```json
{"jeton": "eyJhbGciOiJIUzI1NiIsInR5…", "deux_etapes_requise": false,
 "session": {"utilisateur": {"identifiant": "drh", "nom_complet": "Fanta Maïga", "role": "DRH",
   "perimetre": "Tous les sites", "derniere_connexion": "2026-10-31T23:24:44"},
  "droits": {"agents.gerer": "oui", "biometrie.enroler": "oui", "sites.gerer": "non", …}}}
```

## 4.5 Habilitations

La matrice des droits est appliquée par le serveur à **chaque requête**, et le périmètre d'un responsable filtre
automatiquement toutes les listes, rapports et exports.

| Droit | Administrateur | DRH | Responsable habilité |
|---|---|---|---|
| Gérer les dossiers agents | Oui | Oui | Son périmètre |
| Enrôler et valider les visages | Oui | Oui | Non |
| Proposer un enrôlement (application mobile) | Oui | Oui | Son périmètre |
| Supprimer un gabarit biométrique | Oui | Oui | Non |
| Pointage de secours (application mobile) | Oui | Oui | Son périmètre |
| Consulter les pointages | Oui | Oui | Son périmètre |
| Générer les rapports | Oui | Oui | Son périmètre |
| Gérer sites et terminaux | Oui | Non | Non |
| Gérer utilisateurs et droits | Oui | Non | Non |
| Consulter le journal d'audit | Oui | Oui | Non |

## 4.6 Points d'accès

Les 63 points d'accès sont regroupés par domaine (référence complète en **annexe B**, schéma `openapi.json` joint) :

| Domaine | Préfixe | Nombre | Principales opérations |
|---|---|---|---|
| Authentification et utilisateurs | `/api/auth`, `/api/utilisateurs`, `/api/droits`, `/api/audit` | 12 | Connexion, double authentification, mot de passe oublié, comptes, audit |
| Organisation | `/api/organisation` | 4 | Identité, logo |
| Référentiels | `/api/services`, `/api/sites`, `/api/horaires`, `/api/terminaux`, `/api/synchronisation` | 14 | Sites (autoriser le pointage), terminaux (clé, forcer la synchronisation), lots reçus |
| Agents et enrôlement | `/api/agents`, `/api/enrolements` | 11 | Dossiers, enrôlement, analyse qualité, validation, effacement |
| Pointages et rapports | `/api/pointages`, `/api/tableau-de-bord`, `/api/rapports`, `/api/tentatives` | 8 | Historique, indicateurs, rapports, exports PDF / Excel |
| Bornes de pointage | `/api/terminal` | 7 | Configuration, galerie, état d'un agent, pointages, tentatives, annulations |
| Application mobile | `/api/mobile` | 6 | Connexion d'appareil, accueil, enrôlement proposé, pointage de secours |
| Supervision | `/api/sante` | 1 | Disponibilité |

## 4.7 Synchronisation des terminaux

C'est le mécanisme qui garantit à la fois la **continuité de service** et l'**unicité des événements**.

![Synchronisation après une coupure réseau](images/06_sequence_synchronisation.png){width=88%}

1. Le terminal crée l'identifiant unique (UUID) d'un pointage **au moment où il a lieu**, puis le conserve localement.
2. Il envoie ses pointages par lots (`POST /api/terminal/pointages`), dès que le réseau le permet.
3. Pour chaque pointage, le serveur répond **accepté**, **doublon** (UUID déjà reçu : ignoré sans erreur) ou **refusé**
   (motif : matricule inconnu, site non autorisé, horodatage dans le futur).
4. Le terminal ne retire un pointage de sa file qu'après cette réponse : **aucune perte, aucun doublon**.
5. Chaque lot est journalisé (`lots_synchronisation`) : reçus, doublons ignorés, refusés.

Exemple réel (pointage d'un matricule inexistant) :

```http
POST /api/terminal/pointages            X-Terminal-Key: edmt_…
{"pointages": [{"uuid": "406778ca-…", "matricule": "EDM-INCONNU",
  "horodatage": "2026-10-31T08:02:14+00:00", "type": "ENTREE", "score": 0.81}]}
```
```json
{"acceptes": [], "doublons": [], "rejetes": {"406778ca-…": "matricule inconnu"}}
```

## 4.8 Calcul des présences

Pour chaque agent et chaque jour travaillé de son horaire, l'API détermine : **présent**, **en retard** (première entrée
au-delà de l'heure de début plus la tolérance) ou **absent**, la durée de présence (somme des intervalles entrée → sortie)
et les anomalies (entrée sans sortie, sortie sans entrée, départ anticipé, pointage hors rattachement, pointage un jour
non travaillé). Les pointages annulés (« Ce n'est pas moi ») sont exclus. Exemple réel, semaine du 26 au 30 octobre :

```json
{"titre": "Rapport de présence", "periode": "Du 26/10/2026 au 30/10/2026",
 "indicateurs": {"taux_presence": 85.3, "retards": 31, "absences": 56, "minutes_retard": 960},
 "lignes": [{"service": "Commercial", "effectif": 18, "jours_ouvres": 90, "presences": 71,
             "retards": 7, "absences": 19, "heures_travaillees": 605.47, "taux_presence": 78.9}, …]}
```

\newpage

# 5. Tests et validation

## 5.1 Stratégie

| Niveau | Moyen | Portée |
|---|---|---|
| Tests automatisés de l'API | pytest + client HTTP de test, base recréée à chaque test | 66 scénarios : sécurité, droits, agents, enrôlement, multisite, synchronisation, rapports, exports, mobile |
| Test de bout en bout de la synchronisation | Vrai serveur HTTP démarré puis arrêté pendant le test | Coupure, enregistrement local, reprise, renvoi sans doublon |
| Validation du script SQL | Application de `schema.sql` sur PostgreSQL 16, puis comparaison automatique avec le modèle de l'API | 14 tables, toutes les colonnes et leur caractère obligatoire |
| Essai de charge réaliste | Jeu de démonstration (77 agents, 3 semaines, 2 016 pointages) chargé dans PostgreSQL | Vues, temps de réponse |

## 5.2 Résultats des tests automatisés

| Domaine | Fichier | Tests | PostgreSQL 16 | SQLite |
|---|---|---|---|---|
| Sécurité, habilitations, agents, enrôlement | `test_securite_et_agents.py` | 28 | 28 / 28 | 28 / 28 |
| Multisite, synchronisation, rapports, exports | `test_pointage_multisite.py` | 18 | 18 / 18 | 18 / 18 |
| Terminal : reconnaissance, vivacité, synchronisation réelle | `test_terminal.py` | 12 | 12 / 12 | 12 / 12 |
| Application mobile : appareil, enrôlement à valider, secours | `test_mobile.py` | 8 | 8 / 8 | 8 / 8 |
| **Total** | | **66** | **66 / 66** | **66 / 66** |

Le détail test par test figure en **annexe C**. Commande de rejeu :

```bash
.venv/bin/python -m pytest                                    # SQLite
EDM_TEST_DATABASE_URL=postgresql+psycopg://user:mdp@hôte/edm_tests .venv/bin/python -m pytest   # PostgreSQL
```

## 5.3 Conformité du script SQL

Le script `schema.sql` a été appliqué **sans erreur** sur PostgreSQL 16 (14 tables, 3 vues), puis comparé au modèle
de l'API par l'outil `outils/comparer_schema.py` : **0 écart** (tables, colonnes, caractère obligatoire). Le script et
le code décrivent donc exactement la même base.

## 5.4 Performances mesurées

Sur PostgreSQL 16 avec le jeu de démonstration (77 agents, 2 016 pointages, 3 semaines), PC de développement :

| Requête | Temps de réponse |
|---|---|
| Historique des pointages (page de 25) | 50 ms |
| Liste des agents (page de 20) | 55 ms |
| Tableau de bord du jour | 284 ms |
| Rapport mensuel, tous agents, regroupé par agent | 324 ms |
| Export PDF du rapport | 418 ms |

Pour l'effectif réel d'EDM S.A. (plusieurs milliers d'agents), un essai de montée en charge est prévu en semaine 3.

# 6. Mise en service de l'API

```bash
./setup.sh                      # dépendances, clés secrètes, base initiale
HOTE=0.0.0.0 ./run_server.sh    # API sur le port 8000, documentation interactive sur /docs
```

| Variable (`server/.env`) | Rôle |
|---|---|
| `EDM_DATABASE_URL` | Connexion PostgreSQL (SQLite par défaut) |
| `EDM_CLE_JWT` | Clé de signature des sessions (générée automatiquement) |
| `EDM_CLE_BIOMETRIE` | Clé de chiffrement des gabarits (générée automatiquement — **à sauvegarder** : sans elle, les agents doivent être ré-enrôlés) |
| `EDM_SEUIL_SIMILARITE` | Seuil de reconnaissance faciale (0,42 par défaut) |
| `EDM_DUREE_JETON_MINUTES` | Durée d'une session (480 min par défaut) |

**En production** : API derrière un serveur Nginx en **HTTPS**, rôle PostgreSQL à privilèges minimaux, sauvegarde
quotidienne chiffrée de la base (`pg_dump`) **et** de `server/.env`, mots de passe de démonstration remplacés.

# 7. Limites et suite

| Point | Situation | Suite prévue |
|---|---|---|
| Montée en charge | Mesurée sur 77 agents | Essai avec un effectif réaliste (semaine 3) |
| HTTPS | Configuration de production décrite, non déployée sur le poste de développement | Déploiement sur le serveur d'EDM |
| Purge de conservation | Testée automatiquement ; s'exécute au démarrage puis chaque nuit | Paramétrage de la durée par EDM (5 ans par défaut) |
| Interfaces | Prototypes fonctionnels consommant cette API | Livrable n° 3 : administration web, bornes, application mobile, essais sur site, mémoire |

\newpage

# Annexes

| Annexe | Contenu | Fichier |
|---|---|---|
| A | Dictionnaire de données | `annexes/A_dictionnaire_de_donnees.md` (inclus ci-après) |
| B | Référence des 63 points d'accès | `annexes/B_reference_api.md` (inclus ci-après) |
| C | Résultats détaillés des tests | `annexes/C_resultats_des_tests.md` (inclus ci-après) |
| D | Script de création de la base | `annexes/schema.sql` |
| E | Schéma OpenAPI de l'API | `annexes/openapi.json` |
| F | Rapports d'exécution bruts (JUnit) | `outils/resultats_tests_postgresql.xml`, `outils/resultats_tests_sqlite.xml` |

\newpage
