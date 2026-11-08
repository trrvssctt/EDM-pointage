# Prompt pour générer la présentation PowerPoint

Mode d'emploi :
1. Ouvrez une nouvelle conversation avec Claude.
2. Joignez les fichiers listés à la fin de ce document.
3. Ajustez la durée et le public entre crochets, puis copiez-collez le bloc ci-dessous.

---

```text
Crée une présentation PowerPoint (.pptx) professionnelle, en français, pour la soutenance du projet
« Système de pointage biométrique multisite par reconnaissance faciale » réalisé pour Énergie du Mali (EDM S.A.).

PUBLIC ET DURÉE
- Public : [jury et représentants d'EDM S.A. (DSI, DRH) — à ajuster].
- Durée : [15 minutes de présentation + 10 minutes de démonstration en direct — à ajuster].
- Le message à faire retenir : un agent est enrôlé une seule fois, il pointe sur n'importe quel site
  autorisé, et rien n'est perdu même sans réseau.

RÈGLES DE CONTENU
- N'utilise que les faits donnés ci-dessous ou dans les fichiers joints. N'invente aucun chiffre :
  ni taux de reconnaissance, ni coût, ni résultat de test.
- Une idée par diapositive. Titres formulés comme des affirmations
  (ex. « Les bornes continuent de pointer sans réseau »).
- Au plus 5 puces par diapositive, au plus 12 mots par puce.
- Ajoute des notes de l'orateur sur chaque diapositive : 3 à 5 phrases à dire à l'oral.
- Utilise les captures et diagrammes joints. Ne dessine pas de fausses captures d'écran.

CHARTE GRAPHIQUE
- Couleurs : bleu EDM #1A3A8F (principal), bleu foncé #12286B (titres, bandeaux), blanc,
  gris très clair #F6F8FC pour les fonds de blocs ; orange #B5530A seulement pour les alertes et les limites
  (ce sont les couleurs de l'application elle-même).
- Police sans empattement (Arial ou Calibri). Logo EDM (fichier logo-edm.png) en couverture
  et discrètement en bas des diapositives.
- Format 16:9, style sobre et institutionnel, beaucoup d'espace blanc.

PLAN (16 diapositives)
1. Couverture : titre, sous-titre « Pointage biométrique multisite par reconnaissance faciale »,
   EDM S.A., [nom de l'étudiant], [nom de l'encadrant], [date].
2. Le problème : EDM compte de nombreux sites (siège, directions régionales, agences, centrales,
   services techniques) ; les agents se déplacent ; un pointage limité à un site ou manuel ne suit pas.
3. L'objectif : identifier l'agent par son visage, enregistrer agent, date, heure, site et terminal,
   sur tous les sites, y compris pendant les coupures réseau.
4. La solution en un schéma : administration web, bornes et application mobile, reliées à une API
   centrale, seul accès à la base PostgreSQL (image 02_architecture.png).
5. Les choix techniques et leur raison : FastAPI (Python, vision), PostgreSQL (fiabilité, unicité),
   OpenCV YuNet + SFace (libres, sans cloud), React + TypeScript (fidèle aux maquettes),
   Expo (iPhone et Android). Présenter sous forme de tableau à 2 colonnes.
6. L'enrôlement : 5 poses guidées, contrôle de vivacité, consentement obligatoire, visage déjà enrôlé
   refusé. Variante mobile validée par la DRH (capture admin_04_enrolement.png, diagramme
   07_sequence_enrolement_mobile.png).
7. Le pointage à la borne : détection, identification 1 parmi N, défi aléatoire (tourner la tête,
   cligner des yeux), contrôle du site, anti-rebond de 60 s, entrée ou sortie déduite automatiquement
   (diagramme 05_sequence_pointage.png et captures borne_*).
8. Le multisite : un agent pointe sur tout site autorisé sans nouvel enrôlement ; le site réel est
   enregistré, avec la pastille « Hors rattachement » (capture admin_06_pointages.png).
9. Continuité sans réseau : stockage local sur la borne, renvoi automatique par lots, identifiant
   unique par pointage donc aucun doublon, heure réelle conservée (06_sequence_synchronisation.png,
   capture borne_hors_ligne.png).
10. L'application mobile : enrôlement terrain et pointage de secours quand la borne est en panne,
    avec file d'envoi hors ligne (montage de 3 ou 4 captures mobiles).
11. Le suivi par la DRH : tableau de bord, historique, rapports par agent, service, site et période,
    exports PDF et Excel au logo de l'entreprise (captures admin_02_tableau_de_bord.png,
    admin_07_rapports.png).
12. Sécurité et données personnelles : aucune photo conservée (gabarits de 128 nombres chiffrés,
    clé hors de la base) ; droits appliqués par le serveur (Administrateur, DRH, Responsable limité à
    son périmètre) ; double authentification ; journal d'audit ; consentement ; effacement ;
    conservation limitée (5 ans par défaut).
13. Anti-fraude et ses limites : tableau « tentative / parade » (photo, vidéo, substitution, pointage
    pour un collègue). Limites assumées : masque 3D ou vidéo répondant au bon défi ; pas de défi en
    pointage de secours. Évolution possible : caméra infrarouge ou de profondeur.
14. Validation : 66 tests automatisés sur 66 réussis ; base de 14 tables et 3 vues ; API de
    63 points d'accès ; fiche de 195 cas de test sur tous les équipements ; déploiement sur serveur
    réalisé ; essais du mobile réalisés sur téléphone Android (enrôlement validé par la DRH,
    pointage de secours, refus d'un visage inconnu).
    [Ajouter ici les résultats de la campagne manuelle s'ils sont disponibles.]
15. Limites et suite : passage en HTTPS pour le mobile et les bornes (nom de domaine à fournir par
    EDM) ; essais sur site avec de vrais agents et mesure du taux de reconnaissance ; montée en charge ;
    version installable de l'application mobile ; corrections relevées par la fiche de test.
16. Conclusion et démonstration : rappeler les 3 promesses (une seule inscription, tous les sites,
    rien de perdu sans réseau), puis annoncer la démonstration en direct. Terminer par « Merci,
    place aux questions ».

APRÈS LA DERNIÈRE DIAPOSITIVE, ajoute 2 diapositives d'annexe (à n'afficher que si on pose la question) :
- A1. Spécifications du matériel : borne = mini-PC Intel N100 8 Go ou Raspberry Pi 5,
  écran tactile 10,1″, webcam 1080p avec WDR, onduleur ; serveur = machine virtuelle de 4 processeurs,
  8 Go de RAM, 100 Go SSD, pour environ 2 000 agents et 5 ans d'historique.
- A2. Droits par profil : tableau Administrateur / DRH / Responsable (gérer les agents ; enrôler et
  valider ; proposer un enrôlement mobile ; pointage de secours ; pointages et rapports ;
  sites, terminaux, utilisateurs ; journal d'audit).

LIVRABLE
Un fichier .pptx prêt à projeter, avec les notes de l'orateur. Vérifie ensuite chaque diapositive :
texte qui ne déborde pas, images non déformées, contraste suffisant.
```

---

## Fichiers à joindre à la conversation

Tous les chemins partent du dossier du projet (`~/Documents/EDM`).

| Fichier | Diapositive |
|---|---|
| `livrables/semaine-2-bdd-api/images/logo-edm.png` | Couverture, pied de page |
| `livrables/semaine-2-bdd-api/images/02_architecture.png` | 4 |
| `livrables/semaine-2-bdd-api/images/06_sequence_synchronisation.png` | 9 |
| `livrables/semaine-3-preparation/images/05_sequence_pointage.png` | 7 |
| `livrables/semaine-3-preparation/images/07_sequence_enrolement_mobile.png` | 6 |
| `livrables/semaine-3-preparation/captures/admin_02_tableau_de_bord.png` | 11 |
| `livrables/semaine-3-preparation/captures/admin_04_enrolement.png` | 6 |
| `livrables/semaine-3-preparation/captures/admin_06_pointages.png` | 8 |
| `livrables/semaine-3-preparation/captures/admin_07_rapports.png` | 11 |
| `livrables/semaine-3-preparation/captures/borne_defi_tourner.png`, `borne_succes.png`, `borne_hors_ligne.png` | 7, 9 |
| `livrables/semaine-3-preparation/captures/Mobile/` : 3 ou 4 captures, par exemple l'accueil, la prise de photo et la file d'envoi | 10 |

Choisissez des captures mobiles **sans** l'écran de connexion rempli, et sans données personnelles
réelles. Vos captures montrent un visage réel : utilisez-les seulement si la personne est d'accord.

## Avant de projeter

- **Chiffres :** vérifiez ceux de la diapositive 14 et remplacez le passage entre crochets.
- **Démonstration :** répétez-la au moins une fois, avec le plan B des captures (voir
  `Fiche_de_familiarisation.md`, § 8).
- **Fichier de secours :** apportez la présentation en PDF en plus du .pptx.
