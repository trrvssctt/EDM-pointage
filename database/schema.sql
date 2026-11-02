-- =============================================================================
--  Système de pointage biométrique multisite — base de données centrale
--  Script de création (PostgreSQL 14+)
--
--  Usage :
--    createdb -U postgres edm_pointage
--    psql -U postgres -d edm_pointage -f database/schema.sql
--  Puis dans server/.env :
--    EDM_DATABASE_URL=postgresql+psycopg://edm:motdepasse@localhost:5432/edm_pointage
--
--  Le serveur crée aussi ces tables automatiquement (SQLAlchemy) ; ce script en est
--  la version de référence, commentée, avec contraintes et vues de reporting.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Organisation cliente (marque blanche) et politique de sécurité
-- ---------------------------------------------------------------------------
CREATE TABLE organisation (
    id                             SERIAL PRIMARY KEY,
    nom                            VARCHAR(120) NOT NULL DEFAULT 'Énergie du Mali',
    sigle                          VARCHAR(30)  NOT NULL DEFAULT 'EDM S.A.',
    slogan                         VARCHAR(200) NOT NULL DEFAULT 'Gestion des présences',
    couleur_primaire               VARCHAR(7)   NOT NULL DEFAULT '#1A3A8F' CHECK (couleur_primaire ~ '^#[0-9A-Fa-f]{6}$'),
    couleur_menu                   VARCHAR(7)   NOT NULL DEFAULT '#12286B' CHECK (couleur_menu ~ '^#[0-9A-Fa-f]{6}$'),
    logo                           BYTEA,
    logo_type                      VARCHAR(40)  NOT NULL DEFAULT 'image/png',
    prefixe_matricule              VARCHAR(10)  NOT NULL DEFAULT 'EDM-',
    deux_etapes_obligatoire_admin  BOOLEAN      NOT NULL DEFAULT FALSE,
    duree_conservation_jours       INTEGER      NOT NULL DEFAULT 1825 CHECK (duree_conservation_jours BETWEEN 30 AND 3650),
    modifie_le                     TIMESTAMP    NOT NULL DEFAULT now()
);
COMMENT ON TABLE organisation IS 'Identité de l''entreprise cliente : nom, logo et couleurs affichés sur l''administration, les terminaux et les rapports';
COMMENT ON COLUMN organisation.duree_conservation_jours IS 'Au-delà, pointages, tentatives et journaux sont purgés automatiquement';

-- ---------------------------------------------------------------------------
-- Référentiels
-- ---------------------------------------------------------------------------
CREATE TABLE services (
    id      SERIAL PRIMARY KEY,
    code    VARCHAR(20)  NOT NULL UNIQUE,
    nom     VARCHAR(120) NOT NULL
);

CREATE TABLE sites (
    id         SERIAL PRIMARY KEY,
    code       VARCHAR(20)  NOT NULL UNIQUE,
    nom        VARCHAR(120) NOT NULL,
    nom_court  VARCHAR(60)  NOT NULL DEFAULT '',
    type       VARCHAR(30)  NOT NULL
               CHECK (type IN ('SIEGE', 'DIRECTION_REGIONALE', 'AGENCE', 'CENTRALE', 'SERVICE_TECHNIQUE')),
    ville      VARCHAR(80)  NOT NULL DEFAULT '',
    actif      BOOLEAN      NOT NULL DEFAULT TRUE
);
COMMENT ON COLUMN sites.actif IS 'Interrupteur « Pointage autorisé » : un site non autorisé voit ses terminaux refusés';
COMMENT ON COLUMN sites.nom_court IS 'Libellé affiché sur les terminaux et dans les tableaux (ex. « Siège · Bamako »)';

CREATE TABLE horaires (
    id                 SERIAL PRIMARY KEY,
    nom                VARCHAR(80) NOT NULL UNIQUE,
    heure_debut        TIME        NOT NULL,
    heure_fin          TIME        NOT NULL,
    tolerance_minutes  INTEGER     NOT NULL DEFAULT 10 CHECK (tolerance_minutes BETWEEN 0 AND 240),
    jours_travailles   VARCHAR(20) NOT NULL DEFAULT '0,1,2,3,4'
);
COMMENT ON COLUMN horaires.jours_travailles IS 'Jours travaillés : 0 = lundi ... 6 = dimanche';
COMMENT ON COLUMN horaires.tolerance_minutes IS 'Au-delà, l''arrivée est comptée comme un retard';

CREATE TABLE terminaux (
    id                SERIAL PRIMARY KEY,
    code              VARCHAR(30)  NOT NULL UNIQUE,
    libelle           VARCHAR(120) NOT NULL DEFAULT '',
    site_id           INTEGER      NOT NULL REFERENCES sites (id),
    empreinte_cle     VARCHAR(64)  NOT NULL UNIQUE,
    actif             BOOLEAN      NOT NULL DEFAULT TRUE,
    dernier_contact   TIMESTAMP,
    adresse_ip        VARCHAR(45)  NOT NULL DEFAULT '',
    version           VARCHAR(20)  NOT NULL DEFAULT '',
    nb_en_attente     INTEGER      NOT NULL DEFAULT 0,
    synchro_demandee  BOOLEAN      NOT NULL DEFAULT FALSE,
    type              VARCHAR(10)  NOT NULL DEFAULT 'BORNE' CHECK (type IN ('BORNE', 'MOBILE'))
);
COMMENT ON COLUMN terminaux.type IS 'BORNE : terminal fixe de pointage ; MOBILE : téléphone de l''application terrain (enrôlement, secours)';
COMMENT ON COLUMN terminaux.empreinte_cle IS 'SHA-256 de la clé d''API du terminal (la clé elle-même n''est jamais stockée)';
COMMENT ON COLUMN terminaux.nb_en_attente IS 'Pointages stockés localement, déclarés par le terminal à chaque contact';
COMMENT ON COLUMN terminaux.synchro_demandee IS 'Consigne « Forcer la synchronisation » transmise au prochain contact';

-- ---------------------------------------------------------------------------
-- Agents et données biométriques
-- ---------------------------------------------------------------------------
CREATE TABLE agents (
    id                    SERIAL PRIMARY KEY,
    matricule             VARCHAR(20)  NOT NULL,
    nom                   VARCHAR(80)  NOT NULL,
    prenom                VARCHAR(80)  NOT NULL,
    fonction              VARCHAR(120) NOT NULL DEFAULT '',
    email                 VARCHAR(120) NOT NULL DEFAULT '',
    telephone             VARCHAR(30)  NOT NULL DEFAULT '',
    service_id            INTEGER      NOT NULL REFERENCES services (id),
    site_rattachement_id  INTEGER      NOT NULL REFERENCES sites (id),
    horaire_id            INTEGER      NOT NULL REFERENCES horaires (id),
    tous_sites            BOOLEAN      NOT NULL DEFAULT TRUE,
    consentement_le       TIMESTAMP,
    actif                 BOOLEAN      NOT NULL DEFAULT TRUE,
    cree_le               TIMESTAMP    NOT NULL DEFAULT now(),
    modifie_le            TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ix_agents_matricule ON agents (matricule);
COMMENT ON COLUMN agents.matricule IS 'Identifiant unique de l''agent';
COMMENT ON COLUMN agents.tous_sites IS 'Vrai : pointage autorisé sur tous les sites équipés ; faux : rattachement + sites_autorises';
COMMENT ON COLUMN agents.consentement_le IS 'Date du recueil du consentement au traitement biométrique (obligatoire pour enrôler)';

CREATE TABLE agent_sites_autorises (
    agent_id  INTEGER NOT NULL REFERENCES agents (id) ON DELETE CASCADE,
    site_id   INTEGER NOT NULL REFERENCES sites (id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, site_id)
);
COMMENT ON TABLE agent_sites_autorises IS 'Sélection de sites de pointage autorisés pour un agent (si tous_sites = faux)';

CREATE TABLE gabarits_faciaux (
    id                 SERIAL PRIMARY KEY,
    agent_id           INTEGER     NOT NULL REFERENCES agents (id) ON DELETE CASCADE,
    pose               VARCHAR(10) NOT NULL DEFAULT '' CHECK (pose IN ('', 'face', 'gauche', 'droite', 'haut', 'bas')),
    donnees_chiffrees  BYTEA       NOT NULL,
    qualite            DOUBLE PRECISION NOT NULL DEFAULT 0,
    cree_le            TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX ix_gabarits_faciaux_agent_id ON gabarits_faciaux (agent_id);
COMMENT ON TABLE gabarits_faciaux IS 'Vecteurs biométriques (128 dimensions, SFace), un par pose, chiffrés par Fernet (AES-128 + HMAC). Aucune photo stockée.';

-- ---------------------------------------------------------------------------
-- Pointages, refus et synchronisation
-- ---------------------------------------------------------------------------
CREATE TABLE pointages (
    id           SERIAL PRIMARY KEY,
    uuid         VARCHAR(36) NOT NULL,
    agent_id     INTEGER     NOT NULL REFERENCES agents (id),
    matricule    VARCHAR(20) NOT NULL,
    horodatage   TIMESTAMP   NOT NULL,
    type         VARCHAR(10) NOT NULL CHECK (type IN ('ENTREE', 'SORTIE')),
    site_id      INTEGER     NOT NULL REFERENCES sites (id),
    terminal_id  INTEGER     NOT NULL REFERENCES terminaux (id),
    score        DOUBLE PRECISION NOT NULL DEFAULT 0,
    hors_ligne   BOOLEAN     NOT NULL DEFAULT FALSE,
    annule       BOOLEAN     NOT NULL DEFAULT FALSE,
    secours      BOOLEAN     NOT NULL DEFAULT FALSE,
    recu_le      TIMESTAMP   NOT NULL DEFAULT now(),
    CONSTRAINT uq_pointage_uuid UNIQUE (uuid)
);
CREATE INDEX ix_pointages_agent_id   ON pointages (agent_id);
CREATE INDEX ix_pointages_matricule  ON pointages (matricule);
CREATE INDEX ix_pointages_horodatage ON pointages (horodatage);
CREATE INDEX ix_pointages_site_id    ON pointages (site_id);
COMMENT ON COLUMN pointages.uuid IS 'Identifiant généré par le terminal : un événement n''est consolidé qu''une seule fois';
COMMENT ON COLUMN pointages.horodatage IS 'Heure réelle du pointage sur le terminal';
COMMENT ON COLUMN pointages.recu_le IS 'Heure de réception par le serveur central';
COMMENT ON COLUMN pointages.hors_ligne IS 'Vrai si enregistré pendant une coupure réseau puis synchronisé';
COMMENT ON COLUMN pointages.secours IS 'Pointage de secours effectué avec un téléphone de l''application terrain (borne en panne)';
COMMENT ON COLUMN pointages.annule IS 'Contesté par l''agent (« Ce n''est pas moi ») : exclu des présences, conservé pour la traçabilité';

CREATE TABLE tentatives_rejetees (
    id                 SERIAL PRIMARY KEY,
    uuid               VARCHAR(36) NOT NULL,
    horodatage         TIMESTAMP   NOT NULL,
    motif              VARCHAR(40) NOT NULL,
    matricule_suppose  VARCHAR(20),
    score              DOUBLE PRECISION NOT NULL DEFAULT 0,
    terminal_id        INTEGER     NOT NULL REFERENCES terminaux (id),
    site_id            INTEGER     NOT NULL REFERENCES sites (id),
    hors_ligne         BOOLEAN     NOT NULL DEFAULT FALSE,
    traitee            BOOLEAN     NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_tentative_uuid UNIQUE (uuid)
);
CREATE INDEX ix_tentatives_rejetees_horodatage ON tentatives_rejetees (horodatage);
COMMENT ON COLUMN tentatives_rejetees.motif IS 'VISAGE_INCONNU, ECHEC_VIVACITE, CHANGEMENT_VISAGE, SITE_NON_AUTORISE, IDENTITE_CONTESTEE, APPEL_SUPERVISEUR';
COMMENT ON COLUMN tentatives_rejetees.traitee IS 'Anomalie examinée par un responsable (retirée du tableau de bord)';

CREATE TABLE lots_synchronisation (
    id           SERIAL PRIMARY KEY,
    date         TIMESTAMP NOT NULL DEFAULT now(),
    terminal_id  INTEGER   NOT NULL REFERENCES terminaux (id),
    recus        INTEGER   NOT NULL DEFAULT 0,
    doublons     INTEGER   NOT NULL DEFAULT 0,
    rejetes      INTEGER   NOT NULL DEFAULT 0
);
CREATE INDEX ix_lots_synchronisation_date ON lots_synchronisation (date);
COMMENT ON TABLE lots_synchronisation IS 'Journal des lots reçus : preuve que les renvois ne créent aucun doublon';

-- ---------------------------------------------------------------------------
-- Utilisateurs, habilitations et audit
-- ---------------------------------------------------------------------------
CREATE TABLE utilisateurs (
    id                         SERIAL PRIMARY KEY,
    identifiant                VARCHAR(50)  NOT NULL UNIQUE,
    email                      VARCHAR(120) UNIQUE,
    nom_complet                VARCHAR(120) NOT NULL DEFAULT '',
    fonction                   VARCHAR(120) NOT NULL DEFAULT '',
    mot_de_passe_hash          VARCHAR(200) NOT NULL,
    role                       VARCHAR(20)  NOT NULL CHECK (role IN ('ADMIN', 'DRH', 'RESPONSABLE')),
    service_id                 INTEGER      REFERENCES services (id),
    site_id                    INTEGER      REFERENCES sites (id),
    actif                      BOOLEAN      NOT NULL DEFAULT TRUE,
    echecs_connexion           INTEGER      NOT NULL DEFAULT 0,
    bloque_jusqua              TIMESTAMP,
    derniere_connexion         TIMESTAMP,
    secret_totp                VARCHAR(255),
    deux_etapes                BOOLEAN      NOT NULL DEFAULT FALSE,
    reinitialisation_demandee  BOOLEAN      NOT NULL DEFAULT FALSE,
    cree_le                    TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT ck_responsable_perimetre CHECK (role <> 'RESPONSABLE' OR service_id IS NOT NULL OR site_id IS NOT NULL)
);
COMMENT ON COLUMN utilisateurs.mot_de_passe_hash IS 'PBKDF2-HMAC-SHA256, sel aléatoire, 240 000 itérations';
COMMENT ON COLUMN utilisateurs.service_id IS 'Périmètre d''un responsable habilité : son service et/ou son site';
COMMENT ON COLUMN utilisateurs.secret_totp IS 'Secret de la vérification en deux étapes (TOTP), chiffré';
COMMENT ON COLUMN utilisateurs.bloque_jusqua IS 'Verrouillage temporaire après 5 échecs de connexion';

CREATE TABLE demandes_enrolement (
    id                 SERIAL PRIMARY KEY,
    uuid               VARCHAR(36)  NOT NULL,
    agent_id           INTEGER      NOT NULL REFERENCES agents (id) ON DELETE CASCADE,
    appareil_id        INTEGER      NOT NULL REFERENCES terminaux (id),
    auteur_id          INTEGER      NOT NULL REFERENCES utilisateurs (id),
    photos_chiffrees   BYTEA,
    gabarits_chiffres  BYTEA,
    nb_photos          INTEGER      NOT NULL DEFAULT 0,
    vivacite           BOOLEAN      NOT NULL DEFAULT FALSE,
    controles          TEXT         NOT NULL DEFAULT '',
    statut             VARCHAR(20)  NOT NULL DEFAULT 'RECUE'
                       CHECK (statut IN ('RECUE', 'GABARIT_CALCULE', 'VALIDEE', 'REJETEE')),
    motif              VARCHAR(300) NOT NULL DEFAULT '',
    capture_le         TIMESTAMP    NOT NULL,
    cree_le            TIMESTAMP    NOT NULL DEFAULT now(),
    traite_par         VARCHAR(60)  NOT NULL DEFAULT '',
    traite_le          TIMESTAMP,
    CONSTRAINT uq_demande_uuid UNIQUE (uuid)
);
CREATE INDEX ix_demandes_enrolement_agent_id ON demandes_enrolement (agent_id);
COMMENT ON TABLE demandes_enrolement IS 'Enrôlements proposés depuis l''application mobile, en attente de validation par la DRH';
COMMENT ON COLUMN demandes_enrolement.photos_chiffrees IS 'Photos chiffrées, conservées uniquement jusqu''à la décision (validation ou rejet), puis effacées';
COMMENT ON COLUMN demandes_enrolement.uuid IS 'Identifiant créé par le téléphone : un renvoi depuis la file hors ligne ne crée pas de doublon';

CREATE TABLE journal_audit (
    id          SERIAL PRIMARY KEY,
    date        TIMESTAMP   NOT NULL DEFAULT now(),
    acteur      VARCHAR(60) NOT NULL,
    action      VARCHAR(60) NOT NULL,
    details     TEXT        NOT NULL DEFAULT '',
    adresse_ip  VARCHAR(45) NOT NULL DEFAULT ''
);
CREATE INDEX ix_journal_audit_date ON journal_audit (date);

-- ---------------------------------------------------------------------------
-- Vues de reporting
-- ---------------------------------------------------------------------------
-- Premier et dernier pointage de chaque agent par jour, tous sites confondus.
CREATE VIEW v_presences_journalieres AS
SELECT a.matricule,
       a.prenom || ' ' || a.nom                           AS agent,
       s.nom                                              AS service,
       sr.nom                                             AS site_rattachement,
       p.horodatage::date                                 AS jour,
       MIN(p.horodatage) FILTER (WHERE p.type = 'ENTREE') AS premiere_entree,
       MAX(p.horodatage) FILTER (WHERE p.type = 'SORTIE') AS derniere_sortie,
       COUNT(*)                                           AS nb_pointages,
       BOOL_OR(p.site_id <> a.site_rattachement_id)       AS hors_site_rattachement,
       BOOL_OR(p.hors_ligne)                              AS synchronisation_differee
FROM pointages p
JOIN agents a    ON a.id = p.agent_id
JOIN services s  ON s.id = a.service_id
JOIN sites sr    ON sr.id = a.site_rattachement_id
WHERE NOT p.annule
GROUP BY a.matricule, a.nom, a.prenom, s.nom, sr.nom, p.horodatage::date;

-- Pointages effectués hors du site de rattachement (mobilité des agents).
CREATE VIEW v_pointages_multisites AS
SELECT p.horodatage, p.type, a.matricule, a.prenom || ' ' || a.nom AS agent,
       sr.nom AS site_rattachement, sp.nom AS site_pointage, t.code AS terminal
FROM pointages p
JOIN agents a     ON a.id = p.agent_id
JOIN sites sr     ON sr.id = a.site_rattachement_id
JOIN sites sp     ON sp.id = p.site_id
JOIN terminaux t  ON t.id = p.terminal_id
WHERE p.site_id <> a.site_rattachement_id AND NOT p.annule;

-- État de la synchronisation par terminal.
CREATE VIEW v_etat_terminaux AS
SELECT t.code, s.nom AS site, t.actif, t.version, t.dernier_contact, t.nb_en_attente,
       CASE WHEN NOT t.actif THEN 'DESACTIVE'
            WHEN t.dernier_contact IS NULL THEN 'JAMAIS_CONNECTE'
            WHEN t.dernier_contact < now() - INTERVAL '2 minutes' THEN 'HORS_LIGNE'
            WHEN t.nb_en_attente > 0 THEN 'SYNCHRO'
            ELSE 'EN_LIGNE' END AS etat
FROM terminaux t JOIN sites s ON s.id = t.site_id;

-- ---------------------------------------------------------------------------
-- Rôle applicatif à privilèges minimaux (adapter le mot de passe)
-- ---------------------------------------------------------------------------
-- CREATE ROLE edm LOGIN PASSWORD 'changer-moi';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO edm;
-- GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO edm;

COMMIT;
