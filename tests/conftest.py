# tests/conftest.py
import pytest
from unittest.mock import MagicMock, AsyncMock

# --- Mocks des clients de bas niveau ---

@pytest.fixture
def mock_db_connector():
    """Fixture pour un mock du connecteur PostgreSQL."""
    db_conn = MagicMock()
    db_conn.execute_query = AsyncMock(return_value=[])
    return db_conn

@pytest.fixture
def mock_meili_client():
    """Fixture pour un mock du client Meilisearch."""
    meili_client = MagicMock()
    # Comportement par défaut : simule une recherche qui ne renvoie aucun résultat
    meili_client.get_index.return_value.search = AsyncMock(return_value={'hits': [], 'estimatedTotalHits': 0})
    return meili_client

@pytest.fixture
def mock_cache_manager():
    """Fixture pour un mock du gestionnaire de cache Redis."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)  # Par défaut, le cache est toujours vide (miss)
    cache.set = AsyncMock()
    return cache

# --- Mocks des services de l'application ---

@pytest.fixture
def mock_resto_pastille_service(mock_db_connector):
    """
    Fixture pour un mock du RestoPastilleService.
    Initialisé avec un connecteur de base de données mocké.
    """
    from app.search.resto_pastille import RestoPastilleService

    # On utilise un vrai service, mais on lui injecte un faux connecteur DB
    service = RestoPastilleService(db_connector=mock_db_connector)
    # On peut aussi espionner ses méthodes si nécessaire
    service.append_resto_pastille = AsyncMock(side_effect=lambda datas, user_id: datas)

    return service

@pytest.fixture
def search_service_mock(mock_resto_pastille_service, mock_meili_client, mock_cache_manager):
    """
    Fixture qui fournit une instance de SearchService entièrement mockée
    pour des tests unitaires isolés.
    """
    from app.search.search_service import SearchService

    # Initialise le vrai service avec le service pastille mocké
    service = SearchService(resto_pastille_service=mock_resto_pastille_service)

    # Remplace les clients externes par des mocks
    service.client = mock_meili_client
    service.cache = mock_cache_manager

    # Mock des utilitaires internes pour un contrôle total
    service.utils = MagicMock()
    service.utils.process_results.return_value = {
        'hits': [], 'total': 0, 'has_exact_results': False,
        'exact_count': 0, 'total_before_filter': 0, 'query_time_ms': 10
    }
    service.utils.calculate_count_per_dep.return_value = {}

    return service
