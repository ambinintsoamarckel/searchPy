# tests/test_optimizations.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.search.resto_pastille import RestoPastilleService
from app.scoring.distance import StringDistance
from app.models import QueryData, SearchOptions, SearchResponse
from .test_utils import print_test_name, print_test_result

@pytest.mark.asyncio
class TestCacheLogic:
    """Tests pour la logique de cache (HIT/MISS)."""

    @patch('app.search.search_service.SearchService._execute_search', new_callable=AsyncMock)
    async def test_cache_miss_and_set(self, mock_execute_search, search_service_mock):
        test_name = "test_cache_miss_and_set"
        print_test_name(test_name)
        try:
            """
            Vérifie qu'une première requête résulte en un 'Cache MISS',
            exécute la recherche et met le résultat en cache.
            """
            # --- Arrange ---
            # Le mock de cache dans conftest.py simule déjà un 'miss'

            # Simuler une réponse de la recherche réelle
            mock_response = SearchResponse(
                hits=[],
                total=0,
                has_exact_results=False,
                exact_count=0,
                total_before_filter=0,
                query_time_ms=10
            )
            mock_execute_search.return_value = mock_response

            # --- Act ---
            response = await search_service_mock.search(index_name="test", qdata=MagicMock(), options=SearchOptions(limit=10))

            # --- Assert ---
            # 1. Le cache a été consulté (il a renvoyé None)
            search_service_mock.cache.get.assert_called_once()
            # 2. La recherche a été exécutée (car le cache était vide)
            mock_execute_search.assert_called_once()
            # 3. Le résultat a été mis en cache pour la prochaine fois
            search_service_mock.cache.set.assert_called_once()
            # 4. La réponse est correcte
            assert response.total == 0
            print_test_result(test_name, passed=True)
        except Exception as e:
            print_test_result(test_name, passed=False)
            raise e

    @patch('app.search.search_service.SearchService._execute_search', new_callable=AsyncMock)
    async def test_cache_hit(self, mock_execute_search, search_service_mock):
        test_name = "test_cache_hit"
        print_test_name(test_name)
        try:
            """
            Vérifie qu'une deuxième requête identique résulte en un 'Cache HIT'
            et ne ré-exécute pas la recherche.
            """
            # --- Arrange ---
            cached_response_model = SearchResponse(
                hits=[{"id": 123}],
                total=1,
                has_exact_results=True,
                exact_count=1,
                total_before_filter=1,
                query_time_ms=2
            )
            cached_response_json = cached_response_model.model_dump_json()
            search_service_mock.cache.get.return_value = cached_response_json

            # --- Act ---
            response = await search_service_mock.search(index_name="test", qdata=MagicMock(), options=SearchOptions(limit=10))

            # --- Assert ---
            # 1. Le cache a été consulté
            search_service_mock.cache.get.assert_called_once()
            # 2. La recherche N'A PAS été exécutée (car le cache a été trouvé)
            mock_execute_search.assert_not_called()
            # 3. Le cache a été rafraîchi (TTL mis à jour)
            search_service_mock.cache.set.assert_called_once()
            # 4. La réponse est correcte et vient du cache
            assert response.hits[0]["id"] == 123
            print_test_result(test_name, passed=True)
        except Exception as e:
            print_test_result(test_name, passed=False)
            raise e

@pytest.mark.asyncio
class TestParallelization:
    """Tests pour la parallélisation des appels DB."""

    @patch('app.search.resto_pastille.asyncio.gather', new_callable=AsyncMock)
    async def test_append_resto_pastille_uses_gather(self, mock_gather, mock_db_connector):
        test_name = "test_append_resto_pastille_uses_gather"
        print_test_name(test_name)
        try:
            """
            Vérifie que RestoPastilleService utilise bien asyncio.gather
            pour paralléliser les requêtes.
            """
            # --- Arrange ---
            # Le mock_db_connector est injecté par pytest depuis conftest.py
            service = RestoPastilleService(db_connector=mock_db_connector)
            sample_data = [{'id': 1}, {'id': 2}] # Clé corrigée: 'id' au lieu de 'id_etab'

            # --- Act ---
            await service.append_resto_pastille(datas=sample_data, user_id=123)

            # --- Assert ---
            assert mock_db_connector.execute_query.call_count == 3
            mock_gather.assert_called_once()
            print_test_result(test_name, passed=True)
        except Exception as e:
            print_test_result(test_name, passed=False)
            raise e

class TestLruCache:
    """Test pour la mise en cache LRU sur les fonctions coûteuses."""

    def test_string_distance_lru_cache(self):
        test_name = "test_string_distance_lru_cache"
        print_test_name(test_name)
        try:
            """
            Vérifie que la fonction de calcul de distance est appelée une seule fois
            pour les mêmes arguments.
            """
            # --- Arrange ---
            with patch('app.scoring.distance.lev.distance') as mock_lev_distance:
                mock_lev_distance.return_value = 5
                sd = StringDistance()

                # Appeler deux fois avec les mêmes arguments
                sd.distance("test", "text")
                sd.distance("test", "text")

                # La fonction sous-jacente ne doit être appelée qu'une fois
                mock_lev_distance.assert_called_once_with("test", "text")
                print_test_result(test_name, passed=True)
        except Exception as e:
            print_test_result(test_name, passed=False)
            raise e
