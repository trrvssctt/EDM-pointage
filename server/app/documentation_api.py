"""Descriptions en français des points d'accès sans docstring (documentation /docs et annexe du livrable)."""
from fastapi import FastAPI

DESCRIPTIONS: dict[tuple[str, str], str] = {
    ("POST", "/api/auth/connexion"): "Connexion par identifiant, matricule ou e-mail ; renvoie un jeton de session, ou demande le code de vérification en deux étapes.",
    ("POST", "/api/auth/deux-etapes"): "Seconde étape de connexion : vérifie le code à 6 chiffres (TOTP) et ouvre la session.",
    ("GET", "/api/auth/session"): "Utilisateur connecté et droits effectifs de son profil.",
    ("POST", "/api/auth/mot-de-passe"): "Changement de son propre mot de passe (règle de robustesse appliquée).",
    ("POST", "/api/auth/deux-etapes/activer"): "Active la vérification en deux étapes après saisie d'un premier code valide.",
    ("GET", "/api/utilisateurs"): "Liste des comptes utilisateurs avec profil, périmètre et dernière connexion (administrateur, DRH).",
    ("POST", "/api/utilisateurs"): "Création d'un compte utilisateur (administrateur).",
    ("GET", "/api/droits"): "Matrice des droits par profil (Oui / Non / Son périmètre).",
    ("PUT", "/api/utilisateurs/{utilisateur_id}"): "Modification d'un compte : profil, périmètre, activation, nouveau mot de passe, réinitialisation de la 2FA.",
    ("GET", "/api/audit"): "Journal d'audit des actions sensibles, filtrable par utilisateur et par action.",
    ("PUT", "/api/organisation"): "Modification de l'identité de l'organisation (nom, couleurs, préfixe des matricules) et de la politique de sécurité.",
    ("GET", "/api/organisation/logo"): "Logo de l'organisation (public).",
    ("GET", "/api/services"): "Liste des services.",
    ("POST", "/api/services"): "Création d'un service.",
    ("GET", "/api/sites"): "Liste des sites avec nombre de bornes, état agrégé et effectif rattaché.",
    ("POST", "/api/sites"): "Création d'un site.",
    ("PUT", "/api/sites/{site_id}"): "Modification d'un site.",
    ("GET", "/api/horaires"): "Liste des horaires de travail (début, fin, tolérance, jours travaillés).",
    ("POST", "/api/horaires"): "Création d'un horaire de travail.",
    ("GET", "/api/terminaux"): "Liste des terminaux et téléphones : état, dernier contact, version, pointages en attente.",
    ("POST", "/api/terminaux"): "Enregistrement d'une borne ou d'un téléphone ; la clé d'accès n'est renvoyée qu'une seule fois.",
    ("PUT", "/api/terminaux/{terminal_id}"): "Modification d'un terminal (emplacement, site, activation).",
    ("POST", "/api/terminaux/{terminal_id}/nouvelle-cle"): "Génère une nouvelle clé d'accès ; l'ancienne est immédiatement invalidée.",
    ("GET", "/api/synchronisation/lots"): "Journal des lots reçus des terminaux (reçus, doublons ignorés, refusés).",
    ("GET", "/api/agents"): "Liste paginée des agents du périmètre de l'utilisateur, avec recherche et filtres (service, site, statut, enrôlement).",
    ("POST", "/api/agents"): "Création d'un dossier agent (matricule unique, service, site de rattachement, horaire, sites autorisés).",
    ("GET", "/api/agents/{agent_id}"): "Dossier d'un agent.",
    ("PUT", "/api/agents/{agent_id}"): "Modification ou désactivation d'un dossier agent.",
    ("POST", "/api/agents/{agent_id}/enrolement"): "Enrôlement depuis le poste RH : 5 poses, consentement, contrôles (vivacité, photo de face, cohérence, unicité) puis gabarits chiffrés.",
    ("DELETE", "/api/agents/{agent_id}/gabarits"): "Suppression des données biométriques d'un agent (droit à l'effacement).",
    ("GET", "/api/enrolements/demandes"): "Enrôlements proposés depuis l'application mobile, à valider par la DRH.",
    ("POST", "/api/enrolements/demandes/{uuid}/valider"): "Validation d'une demande : enregistrement des gabarits chiffrés, effacement des photos.",
    ("POST", "/api/enrolements/demandes/{uuid}/rejeter"): "Rejet motivé d'une demande ; les photos sont effacées.",
    ("GET", "/api/pointages"): "Historique unifié des pointages et des refus, filtrable (période, site, terminal, type, alerte, agent), paginé.",
    ("GET", "/api/pointages/export.xlsx"): "Export Excel de l'historique filtré.",
    ("POST", "/api/tentatives/{tentative_id}/traiter"): "Marque une tentative refusée (fraude, appel superviseur) comme traitée.",
    ("GET", "/api/tableau-de-bord"): "Indicateurs du jour : présents, retards, absences, pointages en attente, présence par site, 7 jours, anomalies, terminaux.",
    ("GET", "/api/rapports"): "Rapport de présence, de retards ou d'absences par service, site ou agent sur une période.",
    ("GET", "/api/rapports/export.xlsx"): "Export Excel du rapport (synthèse + détail journalier).",
    ("GET", "/api/rapports/export.pdf"): "Export PDF du rapport aux couleurs de l'organisation.",
    ("GET", "/api/terminal/logo"): "Logo de l'organisation pour l'écran du terminal.",
    ("GET", "/api/terminal/galerie"): "Galerie des gabarits des agents actifs (versionnée : rien n'est renvoyé si elle est inchangée).",
    ("POST", "/api/terminal/tentatives"): "Réception idempotente des tentatives refusées (visage inconnu, fraude, contestation, appel superviseur).",
    ("POST", "/api/mobile/enrolements"): "Envoi idempotent d'un enrôlement photographié sur le terrain ; contrôles immédiats, puis attente de validation DRH.",
    ("GET", "/api/mobile/enrolements/{uuid}"): "Suivi d'une demande d'enrôlement (reçue, gabarit calculé, validée, rejetée).",
    ("GET", "/api/sante"): "Disponibilité du serveur (supervision).",
}


def documenter(app: FastAPI) -> None:
    """Complète le schéma OpenAPI (servi sur /docs) avec les descriptions ci-dessus."""
    generer = app.openapi

    def openapi_documente():
        if app.openapi_schema:
            return app.openapi_schema
        schema = generer()
        for chemin, operations in schema.get("paths", {}).items():
            for methode, operation in operations.items():
                texte = DESCRIPTIONS.get((methode.upper(), chemin))
                if texte and not operation.get("description"):
                    operation["description"] = texte
        app.openapi_schema = schema
        return schema

    app.openapi = openapi_documente
