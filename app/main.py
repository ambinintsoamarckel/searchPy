"""Main module for the FastAPI application."""
import os
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from redis.exceptions import ConnectionError as RedisConnectionError

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

# Créer le répertoire de logs s'il n'existe pas
LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, 'search-api.log')

file_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024 * 5, backupCount=5)
file_handler.setFormatter(log_formatter)
logger = logging.getLogger("search-api")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.propagate = False

# ---------------------------------------------------------------------------------------
## 2. Gestion des événements de cycle de vie (Startup/Shutdown)
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Handle FastAPI startup and shutdown events."""
    # 🚀 DÉMARRAGE DE L'APPLICATION
    logger.info("Starting up SearchPy API...")

    # 1. Connexion au pool PostgreSQL (opération asynchrone)
    try:
        await db_connector.connect()
        logger.info("PostgreSQL connection pool established successfully.")
    except ConnectionError as e:
        logger.error("Failed to connect to PostgreSQL: %s", e)
        # Vous pourriez choisir d'arrêter l'application ici

    # 2. Initialisation du cache
    try:
        await cache_manager.redis.ping()
        logger.info("Redis cache connected successfully.")
    except RedisConnectionError as e:
        logger.error("Failed to connect to Redis: %s", e)

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

def get_service() -> SearchService:
    """Dépendance FastAPI pour obtenir l'instance du service de recherche."""
    return service


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, svc: SearchService = Depends(get_service)):
    """
    POST /search endpoint.
    Nous supposons ici que le user_id est extrait du contexte de la requête
    (ex: headers, token JWT) et n'est pas directement dans SearchRequest.
    """
    try:
        logger.info("Received request: %s", req.model_dump_json())

        resp = await svc.search(
            index_name=req.index_name,
            qdata=req.query_data,
            options=req.options,
            user_id=req.user_id #  Passage du user_id au service
        )
        return resp
    except Exception as e:
        logger.exception("Error processing search request")
        # Log l'exception pour le débogage
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e

@app.get("/")
def root():
    """Root endpoint to check API status."""
    return {"status": "ok", "message": "SearchPy API is running 🚀"}
@app.get("/health", status_code=status.HTTP_200_OK, tags=["Monitoring"])
async def health_check():
    """
    Health check endpoint.

    Checks connectivity to essential services like Database and Redis.
    Returns 200 OK if all services are reachable, otherwise 503 Service Unavailable.
    """
    services_status = {"database": "ok", "redis": "ok"}
    try:
        # 1. Check Redis connection
        await cache_manager.redis.ping()
    except RedisConnectionError:
        services_status["redis"] = "error"
        logger.error("Health check failed: Redis connection error.")

    try:
        # 2. Check Database connection by executing a simple query
        await db_connector.execute_query("SELECT 1")
    except ConnectionError:
        services_status["database"] = "error"
        logger.error("Health check failed: Database connection error.")

    if "error" in services_status.values():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=services_status)

    return services_status
