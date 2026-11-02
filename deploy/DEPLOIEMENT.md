# Déploiement sur le VPS (185.215.165.43)

| Élément | Valeur |
|---|---|
| Code | `/opt/edm-pointage` (clone de `https://github.com/trrvssctt/EDM-pointage.git`) |
| Base de données | conteneur Docker `edm-pointage-db` (postgres:16-alpine), `127.0.0.1:5442`, volume `edm_pointage_donnees` |
| API + interface web | PM2 `edm-pointage` → uvicorn sur `127.0.0.1:8200` (jamais exposé directement) |
| Accès public | Nginx : **https://185.215.165.43:8443** (administration, caméra) · **http://185.215.165.43:8095** (bornes et application mobile) |
| Secrets (à sauvegarder hors du serveur) | `server/.env` (clés de session et de chiffrement biométrique), `deploy/.db.env` (mot de passe PostgreSQL) |

Ces choix n'interfèrent avec aucune application existante (ports 3000-5678, 5440-5441, 8090 et sites Nginx déjà en place).

## 1. Première installation

```bash
cd /opt
git clone https://github.com/trrvssctt/EDM-pointage.git edm-pointage
cd edm-pointage
./deploy/installer_vps.sh --demo     # sans --demo : base vide (organisation, comptes et terminaux de départ)
```

Le script vérifie les prérequis (Python 3.10+, Node 18+, Docker, Nginx, PM2), crée la base, génère les clés,
installe les dépendances, compile l'interface, télécharge les modèles de reconnaissance faciale, charge les données,
démarre le service PM2 et active le site Nginx. Il peut être relancé sans risque : la base, les clés et les données
existantes sont conservées.

## 2. Après l'installation

1. Ouvrir `https://185.215.165.43:8443`, accepter une fois l'avertissement du certificat (Avancé › Continuer), se connecter avec `admin` / `Admin@2026`, puis **changer immédiatement** les mots
   de passe des comptes de départ (Mon compte, Utilisateurs et droits).
2. **Sauvegarder** `server/.env` et `deploy/.db.env` hors du serveur : sans `EDM_CLE_BIOMETRIE`, tous les agents devraient
   être ré-enrôlés.
3. **Bornes de pointage** : leurs fichiers de configuration (adresse du serveur déjà renseignée) sont dans
   `/opt/edm-pointage/terminal/config/` ; copier le fichier de la borne dans `terminal/config/` du poste de pointage.
4. **Application mobile** : Sites et terminaux › `MOB-BKO-07` › « Nouvelle clé » ; vérifier l'adresse
   `http://185.215.165.43:8095` et scanner le QR code depuis l'application.

## 3. Mises à jour

```bash
cd /opt/edm-pointage && ./deploy/mettre_a_jour.sh
```

## 4. Commandes utiles

```bash
pm2 logs edm-pointage                      # journaux de l'API
pm2 restart edm-pointage                   # redémarrage
docker exec -it edm-pointage-db psql -U edm -d edm_pointage    # console SQL
docker exec edm-pointage-db pg_dump -U edm edm_pointage | gzip > /root/edm_$(date +%F).sql.gz   # sauvegarde
```

## 5. HTTPS

Les navigateurs n'autorisent la **caméra** (enrôlement depuis l'application web) qu'en HTTPS. Sans nom de domaine,
l'installation crée un **certificat auto-signé** (`/etc/nginx/ssl/edm-pointage.crt`) pour `https://185.215.165.43:8443` :
le navigateur affiche un avertissement la première fois, puis la caméra fonctionne. Les bornes et l'application mobile
restent sur `http://…:8095` (elles refuseraient un certificat auto-signé).

Pour un certificat reconnu (sans avertissement), avec un nom de domaine pointant vers le VPS (par exemple
`pointage.mon-domaine.ml`) :

```bash
cat > /etc/nginx/sites-available/edm-pointage-https <<'CONF'
server {
    listen 80;
    server_name pointage.mon-domaine.ml;
    client_max_body_size 25m;
    location / {
        proxy_pass http://127.0.0.1:8200;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
CONF
ln -sf /etc/nginx/sites-available/edm-pointage-https /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d pointage.mon-domaine.ml      # certificat Let's Encrypt et redirection HTTPS
```
