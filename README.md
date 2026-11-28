# SmartCampus AI

## Développement local (SA-9)

### Avec Docker Compose (recommandé)

Prérequis : Docker Desktop avec Docker Compose v2.

1. Copier `.env.example` vers `.env` (`Copy-Item .env.example .env` dans PowerShell).
2. Remplacer les mots de passe d’exemple dans `.env`. Ne jamais versionner ce fichier.
3. Démarrer PostgreSQL/pgvector, le backend et le frontend :

   ```powershell
   docker compose --profile apps up --build -d
   ```

4. Appliquer les migrations :

   ```powershell
   docker compose exec backend alembic upgrade head
   ```

5. Ouvrir le frontend sur http://localhost:3000 et Swagger sur
   http://localhost:8000/docs.

`docker compose up -d db` ou `make db` démarre uniquement la base. Les
applications sont dans le profil `apps`; `make up`, `make down` et `make logs`
facilitent leur gestion. `make migrate` applique les migrations et `make test`
lance les tests backend dans le conteneur.

Sondes de santé : `GET /health` (le processus API répond, utilisé par le
healthcheck Compose) et `GET /health/db` (la base PostgreSQL est joignable).

> **Attention :** `make reset-db` supprime le volume PostgreSQL et toutes les
> données locales. Le script d’initialisation de la base ne s’exécute qu’au
> premier démarrage d’un volume vide.

### Lancement sans conteneurs applicatifs

Prérequis : Python 3.12+, Node.js 22+ et PostgreSQL/pgvector démarré.

Dans PowerShell, depuis la racine :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
python -m uvicorn app.main:app --app-dir backend --reload
```

Dans un second terminal :

```powershell
Set-Location frontend
npm ci
npm run dev
```

Le backend lit la connexion PostgreSQL dans `.env`. Pour le lancement natif,
`DB_HOST=localhost`; dans Compose, le service backend utilise le nom DNS `db`.
Les valeurs `VISITOR_SESSION_TTL_HOURS`, `VISITOR_SESSION_MAX_MESSAGES`,
`VISITOR_MEMORY_MAX_MESSAGES` et `VISITOR_MESSAGE_MAX_LENGTH` règlent les
limites des sessions anonymes.

## Catalogue public de l’IIT

Définir `SCRAPER_CONTACT_EMAIL` dans `.env` avec l’adresse de contact du projet.
Depuis la racine, installer les dépendances puis lancer le scraper depuis
`backend/` :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Set-Location backend
..\.venv\Scripts\python.exe -m scraper.run
```

Le scraper vérifie `robots.txt` avant les requêtes, n’utilise que les URL IIT
autorisées, attend au moins deux secondes entre les requêtes et limite la
collecte à 40 pages. Il retire les coordonnées, les panneaux de résultats
étudiants/actualités et les coordonnées bancaires avant d’écrire son cache local
ignoré par Git. Il n’écrit pas dans PostgreSQL.

Le catalogue est généré dans `backend/seed/iit_scraped_catalog.json` et la
couverture dans `backend/scraper/output/coverage.md`. Chaque valeur contient
l’URL source, la date de consultation et un hash de contenu. Les informations
collectées doivent être vérifiées par un humain avant chargement en base.

## Données de démonstration

Les fichiers de `data/demo/` sont fictifs et ne décrivent pas l’offre officielle
de l’IIT ou de l’ISB. Le mot de passe des comptes de démonstration n’est pas
stocké dans ces fichiers; `DEMO_PASSWORD` reste vide dans `.env.example` et
doit être défini localement si le chargement de comptes de démonstration le
requiert. Ne réutiliser aucun mot de passe réel.

## Sessions visiteurs (SA-25/SA-26)

`POST /api/visitor-sessions` crée une session anonyme et retourne son jeton
d’accès une seule fois. Utiliser `Authorization: Bearer <jeton>` pour consulter
ou ajouter des messages et supprimer la session. La mémoire conserve les
20 derniers messages; le plafond est de 100 messages utilisateur par session,
avec expiration après 24 heures par défaut. Les paramètres sont configurables
dans `.env`.

Les jetons ne sont stockés qu’en empreinte côté serveur. Les sessions expirées
sont inaccessibles dès leur expiration et supprimées périodiquement; chaque
création de session purge aussi les entrées expirées. Le frontend conserve le
jeton dans `sessionStorage` (onglet courant) et permet la suppression explicite
de la session. La génération de réponses du chatbot relève d’un ticket séparé.

## Migrations

Les migrations versionnées sont appliquées avec `alembic upgrade head` depuis
`backend/` ou avec `docker compose exec backend alembic upgrade head`. Les
modèles catalogue et comptes responsables restent une base à réconcilier avec
les spécifications finales de SA-12/13/14; les migrations doivent être relues
avant application sur une base partagée.

## Intégration continue (GitHub Actions)

Le workflow [.github/workflows/ci.yml](.github/workflows/ci.yml) s’exécute à
chaque push sur `master`, sur chaque pull request, et peut être lancé à la main
(onglet Actions → CI → Run workflow). Il contient cinq jobs indépendants :

| Job | Vérifie |
|---|---|
| Backend · tests unitaires | `pytest backend/tests` (SQLite en mémoire) |
| Backend · migrations | PostgreSQL 16 + pgvector : `alembic upgrade head`, `alembic check` (modèles ↔ migrations), puis downgrade/upgrade |
| Évaluation LLM · tests | `pytest eval/llm_comparison/tests` (Ollama simulé, aucun modèle téléchargé) |
| Frontend · build + audit | `npm ci`, `npm run build`, `npm audit --omit=dev` |
| Docker · compose + images | validation de `docker-compose.yml` et build des images |

Aucun secret n’est nécessaire : la CI utilise des identifiants factices et
`.env.example`. Le benchmark LLM réel (avec Ollama) reste à lancer en local.
