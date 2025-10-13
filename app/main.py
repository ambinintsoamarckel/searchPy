from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import logging
from logging.handlers import RotatingFileHandler
from typing import List

# Importez vos configurations et services
# Assurez-vous d'avoir les imports corrects pour ces modules :
from .config import settings
from .models import SearchRequest, SearchResponse
from .search.search_service import SearchService
from .search.resto_pastille import RestoPastilleService
from .db.postgres_connector import PostgresConnector # 👈 Votre nouveau connecteur
from .cache import cache_manager # 👈 Votre nouveau manager de cache

# --- Initialisation des variables globales ---

# Connecteur de base de données (sera initialisé au démarrage)
db_connector: PostgresConnector = PostgresConnector(settings.DATABASE_URL)

# Service de pastilles (dépend de db_connector)
resto_pastille_service: RestoPastilleService = RestoPastilleService(db_connector)

# Service de recherche (dépend du service de pastilles)
# Assurez-vous d'inclure les autres dépendances de SearchService si nécessaire
# Instance principale de SearchService (injectée)
search_service: SearchService = SearchService(
    resto_pastille_service=resto_pastille_service
)
# Alias `service` pour compatibilité avec les tests qui patchent `main.service`
service = search_service

# --- Configuration et Loggers (inchangée) ---
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_file = 'logs/search-api.log'
file_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024 * 5, backupCount=5)
file_handler.setFormatter(log_formatter)
logger = logging.getLogger("search-api")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.propagate = False

# ---------------------------------------------------------------------------------------
## 2. Gestion des événements de cycle de vie (Startup/Shutdown)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🚀 DÉMARRAGE DE L'APPLICATION
    logger.info("Starting up SearchPy API...")

    # 1. Connexion au pool PostgreSQL (opération asynchrone)
    try:
        await db_connector.connect()
        logger.info("PostgreSQL connection pool established successfully.")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        # Vous pourriez choisir d'arrêter l'application ici

    # 2. Initialisation du cache
    try:
        await cache_manager.redis.ping()
        logger.info("Redis cache connected successfully.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")

    yield # L'application commence à traiter les requêtes

    # 🛑 ARRÊT DE L'APPLICATION
    logger.info("Shutting down SearchPy API...")

    # 1. Fermeture du pool PostgreSQL (opération asynchrone)
    await db_connector.close()
    logger.info("PostgreSQL connection pool closed.")

    # 2. Fermeture de la connexion Redis
    await cache_manager.close()
    logger.info("Redis connection closed.")

# Création de l'instance FastAPI en passant le lifespan
app = FastAPI(
    title="SearchPy - Python Search Service",
    lifespan=lifespan # 👈 Indique à FastAPI d'utiliser ce contexte
)
# L'instance search_service est déjà initialisée ci-dessus (dans la section 1)
# Remplacez l'ancienne ligne 'service = SearchService()' par 'search_service = SearchService(...)'

@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    """
    POST /search endpoint.
    Nous supposons ici que le user_id est extrait du contexte de la requête
    (ex: headers, token JWT) et n'est pas directement dans SearchRequest.
    """
    try:
        logger.info(f"Received request: {req.json()}")

        # 💡 Extraction de l'ID utilisateur (Exemple hypothétique)
        # user_id = get_user_id_from_auth_header(req) # Utilisez votre propre fonction
        # Pour l'exemple, nous allons le simuler pour éviter les erreurs d'imports
        user_id = 42 # Remplacez ceci par la logique d'extraction réelle

        resp = await service.search(
            index_name=req.index_name,
            qdata=req.query_data,
            options=req.options,
            user_id=req.user_id #  Passage du user_id au service
        )
        return resp
    except Exception as e:
        logger.exception("Error processing search request")
        # Log l'exception pour le débogage
        raise HTTPException(status_code=500, detail={"error": str(e)})

@app.get("/")
def root():
    return {"status": "ok", "message": "SearchPy API is running 🚀"}
