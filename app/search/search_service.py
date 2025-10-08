import asyncio
import time
import psutil
from typing import List, Dict, Any, Optional

from meilisearch_python_sdk import AsyncClient as MeiliClient
from app.models import QueryData, SearchOptions, SearchResponse
from app.search.search_utils import SearchUtils  # <-- Ton utilitaire complet


class SearchService:
    """Service de recherche principal combinant stratégies Meilisearch + scoring SearchUtils."""

    def __init__(self, meili_host: str = None, meili_key: str = None):
        self.meili_host = meili_host or "http://127.0.0.1:7700"
        self.meili_key = meili_key or "masterKey"
        self.client = MeiliClient(self.meili_host, self.meili_key)
        self.utils = SearchUtils()  # intègre le scoring textuel/phonétique complet

    async def _meili_search(
        self, index_name: str, query: str, attributes: List[str], limit: int, filters: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        index = await self.client.get_index(index_name)
        search_params = {"limit": limit, "attributesToRetrieve": attributes}
        if filters:
            search_params['filter'] = filters
        res = await index.search(query, search_params)
        return res.get('hits', []) if isinstance(res, dict) else []

    async def _parallel_strategies(
        self, index_name: str, qdata: QueryData, options: SearchOptions
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Exécute plusieurs stratégies de recherche Meilisearch en parallèle."""
        limit = options.limit
        filters = options.filters

        strategies = {
            'name_search': (qdata.cleaned or qdata.original, ['name_search']),
            'no_space': (qdata.no_space, ['name_no_space']),
            'standard': (qdata.original, ['name']),
        }
        if qdata.soundex:
            strategies['phonetic'] = (qdata.soundex, ['name_soundex'])

        tasks = [
            self._meili_search(index_name, q, attrs, limit, filters)
            for q, attrs in strategies.values()
        ]
        results = await asyncio.gather(*tasks)
        return dict(zip(strategies.keys(), results))

    async def search(self, index_name: str, qdata: QueryData, options: SearchOptions) -> SearchResponse:
        """Recherche complète : exécution parallèle, déduplication, scoring et tri."""
        t0 = time.time()

        # 1️⃣ Exécution parallèle Meilisearch
        all_results = await self._parallel_strategies(index_name, qdata, options)

        # 2️⃣ Traitement complet (déduplication + scoring + tri) via SearchUtils
        processed = self.utils.process_results(all_results, qdata, limit=options.limit)

        # 3️⃣ Construction de la réponse finale
        t1 = time.time()
        resp = SearchResponse(
            hits=processed['hits'],
            total=processed['total'],
            has_exact_results=processed['has_exact_results'],
            exact_count=processed['exact_count'],
            total_before_filter=processed['total_before_filter'],
            query_time_ms=processed['query_time_ms'],
            preprocessing=qdata,
            memory_used_mb=psutil.Process().memory_info().rss / 1024 / 1024,
        )
        return resp
