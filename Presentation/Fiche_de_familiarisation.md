# Fiche de familiarisation : présentation du 09/11/2026

Système de pointage biométrique multisite par reconnaissance faciale, pour Énergie du Mali (EDM S.A.).
À relire la veille ; à garder sous la main pendant la démonstration.

---

## 1. Le projet en 30 secondes

> Les agents d'EDM travaillent sur de nombreux sites : siège, directions régionales, agences, centrales.
> Nous avons réalisé un système où l'agent est **enrôlé une seule fois** (son visage), puis **pointe sur
> n'importe quel site autorisé** devant une borne. Chaque pointage enregistre l'agent, l'heure, le site
> et le terminal. Les bornes **continuent de fonctionner sans réseau** et se synchronisent ensuite
> **sans doublon**. La DRH suit tout depuis une application web : tableau de bord, historique, rapports
> PDF et Excel. Une application mobile sert à enrôler sur le terrain et à pointer quand une borne est en panne.

## 2. Chiffres à retenir

| Sujet | Chiffre |
|---|---|
| Base de données | 14 tables, 3 vues de reporting (PostgreSQL 16) |
| API centrale | 63 points d'accès, documentés en français |
| Tests automatisés | 74 sur 74 réussis (relancés le 09/11/2026) |
| Fiche de tests manuels | 195 cas, dont 116 de priorité haute |
| Données de démonstration | 6 sites, 77 agents fictifs, 3 semaines d'historique |
| Écrans | 10 pages d'administration, écran de borne, 9 écrans mobiles |
| Reconnaissance (PC de développement) | ≈ 22 ms de détection + 23 ms de calcul du gabarit par image |
| Gabarit d'un visage | vecteur de 128 nombres, chiffré ; aucune photo conservée |
| Profils | Administrateur, DRH, Responsable (limité à son service ou à son site) |

## 3. Architecture : les 4 parties

```
 Administration web (navigateur)  ──┐
 Bornes de pointage (sur chaque site)──┼──► API centrale (FastAPI) ──► PostgreSQL
 Application mobile (téléphone)   ──┘        seul point d'accès
```

- **Règle d'or** : aucun écran ne touche directement la base. Tout passe par l'API, donc les droits,
  le chiffrement et le journal d'audit s'appliquent toujours.
- **La borne reconnaît sur place** (galerie de visages chiffrée en local). C'est ce qui permet de
  pointer pendant une coupure réseau.
- **Déploiement actuel** : un VPS (185.215.165.43) avec PostgreSQL dans Docker, l'API gérée par PM2 et
  Nginx en frontal. L'administration est servie en HTTPS sur le port 8443, les bornes et le mobile en
  HTTP sur le port 8095.

**Technologies, et pourquoi en une phrase :**

| Technologie | Pourquoi |
|---|---|
| Python + FastAPI | Même langage que la vision par ordinateur ; documentation de l'API générée automatiquement |
| PostgreSQL | Fiable, contraintes d'unicité (zéro doublon), vues pour les rapports |
| OpenCV YuNet + SFace | Modèles libres, légers, sur processeur seul, **sans cloud** : les visages ne sortent pas de l'entreprise |
| React + TypeScript | Interfaces fidèles aux maquettes ; même base pour l'administration et l'écran de borne |
| Expo (React Native) | Une seule application pour iPhone et Android |

## 4. Les écrans, et qui fait quoi

### Administration web
| Page | Ce qu'on y fait |
|---|---|
| Tableau de bord | Présents, retards, absences du jour, présence par site, 7 derniers jours, état des terminaux, anomalies à traiter |
| Agents | Créer, modifier, désactiver ; matricule unique ; sites autorisés |
| Enrôlement | Capture des 5 poses à la webcam ; onglet **« À valider »** pour les enrôlements faits sur mobile |
| Pointages | Historique unifié : entrées, sorties, refus ; pastilles « Hors rattachement », « Différé », « Secours », « Annulé » |
| Rapports | Présence, retards, absences ; regroupement par service, site ou agent ; export PDF et Excel avec le logo |
| Sites et terminaux | Autoriser ou suspendre un site ; enregistrer une borne ou un téléphone (clé et QR code) ; forcer la synchronisation |
| Utilisateurs et droits | Comptes, profils, matrice des droits, journal d'audit |
| Paramètres | Nom, logo, couleurs (marque blanche), services, horaires, durée de conservation |
| Mon compte | Mot de passe, vérification en deux étapes |

### Droits par profil (appliqués par le serveur, pas seulement à l'écran)
| Droit | Admin | DRH | Responsable |
|---|---|---|---|
| Gérer les agents | Oui | Oui | Son périmètre |
| Enrôler et **valider** les visages | Oui | Oui | Non |
| **Proposer** un enrôlement (mobile) | Oui | Oui | Son périmètre |
| Pointage de secours (mobile) | Oui | Oui | Son périmètre |
| Pointages et rapports | Oui | Oui | Son périmètre |
| Sites, terminaux, utilisateurs | Oui | Non | Non |
| Journal d'audit | Oui | Oui | Non |

### Borne de pointage
Écrans : attente → analyse → **défi** (« Tournez la tête » ou « Clignez des yeux ») → succès,
avec le bouton « Ce n'est pas moi », ou refus. Un bandeau « Hors ligne · enregistrement local »
s'affiche pendant les coupures.

### Application mobile
Accueil · Enrôler (choisir l'agent, 5 photos, consentement, envoi) · Secours (pointer un agent par photo)
· File d'envoi (ce qui attend le réseau). Le téléphone doit d'abord être **enregistré** par
l'administrateur, à l'aide d'un QR code.

## 5. Les parcours à savoir raconter

**Enrôlement (une seule fois par agent)**
1. Le dossier de l'agent est créé dans l'application web.
2. Au poste RH, la webcam guide 5 poses : face, un côté, l'autre côté, haut, bas. La capture est
   automatique ; un bouton manuel apparaît après 8 s.
3. Un contrôle de vivacité vérifie que la tête a vraiment tourné, ce qu'une photo ne peut pas faire.
4. Le consentement est obligatoire et horodaté.
5. **Contrôle d'identité à chaque photo** :
   - un visage déjà enrôlé sous un autre matricule est signalé tout de suite, avec son nom, et la
     capture est bloquée ;
   - si une autre personne prend le relais pendant les poses, la capture est refusée.
6. **Variante mobile** : un responsable photographie l'agent sur le terrain, mais l'enrôlement n'est
   **actif qu'après validation de la DRH** sur le site. Les photos sont effacées dès la décision.

**Pointage à la borne**
1. L'agent se présente ; la borne détecte le visage sur 8 images stables.
2. Elle calcule son gabarit et le compare à tous les agents enrôlés : identification « 1 parmi N »,
   seuil de similarité de 0,42.
3. Elle lance un défi aléatoire, à réussir en 7 s, puis revérifie l'identité.
4. Elle contrôle que l'agent est autorisé sur ce site, et qu'il n'a pas pointé dans les 60 dernières
   secondes (anti-rebond).
5. Entrée ou sortie : la borne la déduit du **dernier pointage du jour, tous sites confondus**.
6. Le pointage est enregistré localement, puis envoyé au serveur.

**Multisite (le cœur du sujet)** : un agent de la DR Sikasso pointe au siège sans nouvel enrôlement.
Le site réel est enregistré, et l'historique affiche « Hors rattachement ». Le site de rattachement est
toujours autorisé ; les autres sites peuvent être restreints agent par agent.

**Coupure réseau**
- La borne garde tout en local, et retente l'envoi toutes les 10 s.
- Au retour du réseau, elle envoie par lots de 200, dans l'ordre chronologique.
- Chaque pointage a un identifiant unique, créé au moment du pointage : un renvoi est reconnu et
  compté en « doublon ignoré ».
- Une ligne ne quitte la borne qu'après accusé de réception.
- L'heure réelle et l'heure de réception sont conservées séparément.

**Pointage de secours (mobile)** : à utiliser quand la borne est en panne. Le responsable photographie
l'agent, et le serveur le reconnaît avec la même galerie que les bornes. Le pointage est marqué
« Secours ». Sans réseau, la photo attend dans la file d'envoi et l'heure réelle est conservée.

## 6. Sécurité et données personnelles

- **Pas de photo stockée** : seulement des vecteurs de 128 nombres, à partir desquels on ne peut pas
  reconstituer le visage.
- **Chiffrement** : gabarits chiffrés avec une clé gardée hors de la base. Une copie volée de la base
  est inexploitable. Le cache des bornes est chiffré lui aussi.
- **Comptes** :
  - mots de passe hachés (PBKDF2, 240 000 itérations) ;
  - compte bloqué 15 minutes après 5 échecs ;
  - vérification en deux étapes (code à 6 chiffres) ;
  - session de 8 h.
- **Bornes et téléphones** : chacun a sa propre clé, révocable à tout moment (« Nouvelle clé », « Désactiver »).
- **Traçabilité** : le journal d'audit enregistre connexions, modifications, enrôlements, exports et
  adresses IP. Les pointages annulés et les tentatives refusées sont conservés.
- **Droits de l'agent** : consentement obligatoire ; suppression du gabarit sur demande ; purge
  automatique au-delà de la durée de conservation (5 ans par défaut, réglable).

## 7. Anti-fraude

| Tentative | Parade |
|---|---|
| Photo imprimée ou sur écran | Défi de rotation : sur une image plate, la tête ne « tourne » jamais |
| Vidéo enregistrée | Défi tiré au hasard au dernier moment, délai de 7 s |
| Changer de personne pendant le défi | Revérification de l'identité à la fin du défi |
| Pointer pour un collègue | « Ce n'est pas moi », tentatives tracées, anomalies au tableau de bord |
| Enrôler une photo | Vivacité contrôlée à l'enrôlement, consentement en présence de l'agent |
| Deux personnes qui se relaient pendant l'enrôlement | Chaque pose est comparée à la photo de face et aux autres agents enrôlés : capture bloquée |

**Limites à assumer** : une caméra classique ne détecte pas un masque 3D réaliste ni une vidéo qui
répondrait au bon défi. Il faudrait alors une caméra infrarouge ou de profondeur, et l'architecture
le permet. Autre limite : le **pointage de secours n'a pas de défi**. Il repose sur la présence du
responsable et sur la traçabilité.

## 8. Démonstration

### Le matin : vérifications (sur le VPS, en root)

1. **Mettre le VPS à jour** :
   ```bash
   cd /opt/edm-pointage && git pull && ./deploy/mettre_a_jour.sh
   ```
2. **Remettre les données de démonstration à jour.** Sans cela, le tableau de bord affiche 0 présent
   sur 76, car l'historique fictif s'arrête au 02/11, jour de l'installation. La commande :
   - complète les pointages des agents fictifs jusqu'à maintenant ;
   - ajoute les anomalies du jour ;
   - corrige l'heure des pointages mobiles faits avant le réglage du fuseau.

   Elle ne touche ni aux comptes, ni aux clés, ni aux agents réellement enrôlés.
   ```bash
   .venv/bin/python -m server.actualiser_demo --corriger-fuseau
   ```
   **Relancez-la juste avant de présenter** (sans `--corriger-fuseau`), pour ajouter les pointages
   des dernières heures. Elle peut être relancée sans risque.
3. **Contrôler la galerie** : la commande liste les agents enrôlés avec des visages mélangés, comme
   Assitan Sow.
   ```bash
   .venv/bin/python -m server.controle_galerie
   ```
   Pour chaque agent signalé : Agents › sa fiche › « Supprimer le gabarit biométrique ». Ne le
   réenrôlez que si la personne est présente.
4. **Bornes « en ligne »** : aucune borne physique ne tourne. Cette commande les fait contacter le
   serveur toutes les 30 s pendant 4 h, comme des bornes allumées, sans rien pointer :
   ```bash
   nohup .venv/bin/python -m terminal.presence_bornes --serveur http://127.0.0.1:8200 > /tmp/bornes.log 2>&1 &
   ```
   - Pour montrer une panne : ajoutez `--sauf TRM-SEL-01`, et la borne de Sélingué reste
     « hors ligne ».
   - Pour l'arrêter : `pkill -f presence_bornes`.
5. Ouvrir `https://185.215.165.43:8443` dans le navigateur de la démonstration, accepter le
   certificat, se connecter avec un compte **admin** et un compte **drh** (onglet « Démarrer ici »
   de la fiche de test).
6. **Téléphone** : Expo lancé sur le PC, câble branché, `adb reverse tcp:8081 tcp:8081` exécuté,
   application ouverte et connectée. Le Samsung est déjà enregistré comme `MOB-BKO-07`.
7. **Lumière** : bien éclairer le visage de face. L'application a déjà signalé « Lumière
   insuffisante » en intérieur.
8. Préparer **un agent sans visage** pour l'enrôlement en direct, et **une personne non enrôlée**
   pour montrer un refus.
9. **Plan B** : garder les captures de `livrables/semaine-3-preparation/captures/` ouvertes, au cas
   où le réseau ferait défaut.

### Déroulé conseillé (≈ 10 minutes)
| # | Montrer | Message à faire passer |
|---|---|---|
| 1 | Tableau de bord (DRH) | « La DRH voit en un coup d'œil la présence de tous les sites » |
| 2 | Agents, puis une fiche | Matricule unique, rattachement, sites autorisés, état biométrique |
| 3 | Mobile : enrôler l'agent préparé (5 photos, consentement, envoi) | Enrôlement sur le terrain, sans PC |
| 4 | Site : Enrôlement › **À valider** › Valider ; le téléphone passe à « Validé » | La DRH garde le contrôle |
| 5 | Mobile : Secours › pointer cet agent | Reconnu en quelques secondes, marqué « Secours » |
| 6 | Site : Pointages | Heure, site, terminal, pastilles ; **multisite** si l'agent est rattaché ailleurs |
| 7 | Mobile : personne non enrôlée | Refus, et tentative tracée |
| 8 | Site : **Poste de pointage simulé**, deux personnes devant la webcam | Même moteur que les bornes : chacun est identifié en direct (démonstration, rien n'est pointé) |
| 9 | Mobile : mode avion → pointer → réseau rétabli | Rien n'est perdu, aucun doublon, heure réelle conservée |
| 10 | Rapports : changer la période, exporter le PDF | Rapport fiable, au logo de l'entreprise |
| 11 | Utilisateurs et droits, puis journal d'audit | Confidentialité et traçabilité |

Pour la borne, montrer les captures, sauf si elle a été préparée et testée avant. Pour la faire
tourner sur le PC, il faut une configuration téléchargée depuis le VPS avec l'adresse
`http://185.215.165.43:8095`, et un environnement Python réparé (`./setup.sh`).

## 9. Questions probables, et réponses

**« Ces chiffres sont-ils réels ? »**
Non : le tableau de bord repose sur 70 agents fictifs et leur historique de démonstration. Les
pointages faits en direct pendant la démonstration, eux, sont réels. Le dire d'emblée.

**« Quel est le taux de reconnaissance ? »**
Le moteur est validé sur nos jeux de test, mais le taux sur de vrais agents d'EDM reste à mesurer
lors des essais sur site. La fiche de test prévoit au moins 95 % sur 20 passages par condition
d'éclairage. Ne pas annoncer de chiffre non mesuré.

**« Et sans Internet ? »**
La borne reconnaît localement et stocke les pointages ; elle envoie tout au retour du réseau, sans
doublon. Le mobile fait de même avec sa file d'envoi.

**« Un agent peut-il pointer pour un autre avec une photo ? »**
À la borne, non : le défi de vivacité l'en empêche. Les limites sont celles du § 7 (masque 3D, vidéo
qui répondrait au bon défi). En secours mobile, le contrôle repose sur le responsable présent et
sur la traçabilité.

**« Où sont les visages ? Qui peut les voir ? »**
Nulle part en photo. Seuls des gabarits chiffrés sont gardés sur le serveur d'EDM, sans cloud
externe. Seuls l'administrateur et la DRH peuvent enrôler ou supprimer.

**« Pourquoi pas les empreintes digitales ? »**
Le visage est sans contact (hygiène, usure des capteurs) et permet l'enrôlement à distance par
téléphone. C'est aussi le sujet du cahier des charges.

**« Combien ça coûte en matériel ? »**
Par point de pointage : un mini-PC ou un Raspberry Pi 5, un écran tactile de 10″, une webcam 1080p,
un onduleur. Le serveur : une machine virtuelle de 4 processeurs et 8 Go, pour environ 2 000 agents
et 5 ans d'historique. Ne pas avancer de prix sans devis.

**« Et si l'agent change d'apparence (barbe, lunettes) ? »**
Les 5 poses rendent la reconnaissance robuste. En cas d'échecs répétés, on supprime le gabarit et
on réenrôle en 2 minutes.

**« Le système peut-il servir à une autre entreprise ? »**
Oui : nom, logo, couleurs, préfixe des matricules, services et horaires se paramètrent sans
toucher au code (marque blanche). Exception : l'écran de connexion mobile affiche encore
« Énergie du Mali » en dur, ce qui est à corriger.

**« Est-ce légal ? »**
Le consentement, la finalité limitée, la durée de conservation et le droit à l'effacement sont
prévus. La déclaration auprès de l'autorité de protection des données personnelles (APDP au Mali)
relève d'EDM avant la mise en production.

## 10. Limites et suite : à dire avant qu'on les découvre

- **Données en clair** : le mobile et les bornes passent encore en **HTTP**. Il faut un nom de domaine
  et un certificat reconnu, ce qui demande une décision d'EDM.
- **Essais sur site** avec de vrais agents, et mesure du taux de reconnaissance : pas encore faits.
- **Montée en charge** sur l'effectif réel : à faire.
- **Application mobile** : elle tourne dans Expo Go ; une version installable reste à produire.
- **Anomalies relevées dans la fiche de test**, à corriger :
  - effacement sans avertissement de la file d'envoi au changement d'appareil ;
  - un refus après coupure s'affiche « Envoyé » (visible sur nos captures) ;
  - libellé « Matricule » à l'écran de connexion mobile.
- **Reste à rédiger** : le guide d'utilisation et le mémoire.

## 11. Petit glossaire

| Terme | Sens |
|---|---|
| Enrôlement | Enregistrer le visage d'un agent, une seule fois |
| Gabarit | Représentation chiffrée du visage (128 nombres) ; pas une photo |
| Identification 1:N | Retrouver qui est la personne parmi tous les agents enrôlés |
| Vivacité | Vérifier qu'il s'agit d'une personne réelle, pas d'une photo |
| Site de rattachement | Le site habituel de l'agent ; les autres sites sont « hors rattachement » |
| Synchronisation | Envoi des pointages de la borne vers le serveur central |
| Anti-rebond | Ignorer un second pointage du même agent dans les 60 s |
| Pointage de secours | Pointage fait au téléphone quand la borne est en panne |
| Marque blanche | Produit personnalisable aux couleurs de n'importe quelle entreprise |
