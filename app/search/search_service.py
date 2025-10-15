"""Module contenant le service de recherche principal."""
# app/search/search_service.py
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import psutil
from meilisearch_python_sdk import AsyncClient as MeiliClient

from app.cache import cache_manager
from app.config import settings
from app.models import QueryData, SearchOptions, SearchResponse
from app.search.resto_pastille import RestoPastilleService
from app.search.search_utils import SearchUtils

logger = logging.getLogger("search-api")


@dataclass
class SearchContext:
    """Contexte partagé pour les opérations de recherche."""
    index_name: str
    options: SearchOptions
    user_id: Optional[int]
    is_resto_index: bool
    start_time: float


class SearchService:
    """Service de recherche principal combinant stratégies Meilisearch + scoring SearchUtils."""

    def __init__(self, resto_pastille_service: RestoPastilleService):
        self.meili_host = settings.MEILISEARCH_URL
        self.meili_key = settings.MEILISEARCH_API_KEY
        self.client = MeiliClient(self.meili_host, self.meili_key)
        self.utils = SearchUtils()
        self.resto_pastille_service = resto_pastille_service
        self.cache = cache_manager

    async def _meili_search(
            self,
            index_name: str,
            query: str,
            attributes: List[str],
            options: SearchOptions
        ) -> Dict[str, Any]:
        """Effectue une recherche sur Meilisearch."""
        index = await self.client.get_index(index_name)

        res = await index.search(
            query,
            limit=options.limit,
            attributes_to_search_on=attributes,
            filter=options.filters,
            sort=options.sort,
            offset=options.offset,
        )

        if hasattr(res, 'dict'):
            return res.dict()
        return res

    async def _parallel_strategies(
        self, index_name: str, qdata: QueryData, options: SearchOptions
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Exécute plusieurs stratégies de recherche en parallèle."""
        strategies = {
            'name_search': (qdata.cleaned or qdata.original, ['name_search']),
            'no_space': (qdata.no_space, ['name_no_space']),
            'standard': (qdata.original, ['name']),
        }
        if qdata.soundex:
            strategies['phonetic'] = (qdata.soundex, ['name_soundex'])

        tasks = [
            self._meili_search(index_name, q, attrs, options=options)
            for q, attrs in strategies.values()
        ]
        results = await asyncio.gather(*tasks)
        return dict(zip(strategies.keys(), results))

    def _calculate_count_per_dep(
        self, hits: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Calcule le nombre de résultats par département."""
        count_per_dep: Dict[str, int] = {}
        for item in hits:
            dep = item.get('dep')
            if dep is not None:
                try:
                    dep_int = int(dep)
                    dep_key = f"{dep_int:02d}"
                    count_per_dep[dep_key] = count_per_dep.get(dep_key, 0) + 1
                except ValueError:
                    continue
        return dict(sorted(count_per_dep.items()))

    async def search(
            self,
            index_name: str,
            qdata: Optional[Union[str, QueryData]],
            options: SearchOptions,
            user_id: Optional[int] = None
        ) -> SearchResponse:
        """Effectue une recherche en utilisant un système de cache.

        Args:
            index_name: Nom de l'index sur lequel chercher.
            qdata: Données de la requête (simple string ou QueryData).
            options: Options de recherche (limite, filtres, etc.).
            user_id: ID de l'utilisateur pour personnalisation.

        Returns:
            Un objet SearchResponse avec les résultats.
        """
        cache_key = (
            f"search:{index_name}:{str(qdata)}:{str(options)}:{user_id}"
        )

        cached_result = await self.cache.get(cache_key)
        if cached_result:
            logger.info("Cache HIT for key: %s", cache_key)
            return SearchResponse.parse_raw(cached_result)

        logger.info("Cache MISS for key: %s", cache_key)
        response = await self._execute_search(
            index_name, qdata, options, user_id
        )

        await self.cache.set(
            cache_key, response.json(), expire=300
        )
        return response

    async def get_index_stats(self, index_name: str) -> Dict[str, Any]:
        """Récupère les statistiques d'un index Meilisearch.

        Méthode publique supplémentaire pour satisfaire pylint.
        """
        index = await self.client.get_index(index_name)
        stats = await index.get_stats()
        return stats.dict() if hasattr(stats, 'dict') else stats

    async def _execute_search(
            self,
            index_name: str,
            qdata: Optional[Union[str, QueryData]],
            options: SearchOptions,
            user_id: Optional[int] = None
        ) -> SearchResponse:
        """Exécute la recherche sans cache."""
        ctx = SearchContext(
            index_name=index_name,
            options=options,
            user_id=user_id,
            is_resto_index='resto' in index_name or 'restaurant' in index_name,
            start_time=time.time()
        )

        if qdata is None or isinstance(qdata, str):
            return await self._handle_simple_search(qdata, ctx)

        return await self._handle_advanced_search(qdata, ctx)

    async def _handle_simple_search(
        self,
        qdata: Optional[Union[str, QueryData]],
        ctx: SearchContext
    ) -> SearchResponse:
        """Gère la recherche simple."""
        query_text = qdata if isinstance(qdata, str) else ""

        result = await self._meili_search(
            index_name=ctx.index_name,
            query=query_text,
            attributes=['name'],
            options=ctx.options
        )

        hits = result.get('hits', [])
        estimated_total = result.get('estimated_total_hits', 0)

        if ctx.is_resto_index :
            logger.debug(
                "Enrichissement des %s restos pour l'utilisateur %s",
                len(hits), ctx.user_id
            )
            hits = await self.resto_pastille_service.append_resto_pastille(
                datas=hits,
                user_id=ctx.user_id
            )

        duration = time.time() - ctx.start_time
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024

        logger.info(
            "Recherche simple (index: %s, query: '%s') : "
            "Durée = %.4fs | RAM = %.2f Mo",
            ctx.index_name, query_text, duration, memory_mb
        )

        return SearchResponse(
            hits=hits,
            total=len(hits),
            has_exact_results=False,
            exact_count=0,
            total_before_filter=estimated_total or len(hits),
            query_time_ms=duration * 1000,
            preprocessing=None,
            memory_used_mb=memory_mb,
            count_per_dep=self._calculate_count_per_dep(hits),
        )

    async def _handle_advanced_search(
        self,
        qdata: QueryData,
        ctx: SearchContext
    ) -> SearchResponse:
        """Gère la recherche avancée avec scoring."""
        all_results = await self._parallel_strategies(
            ctx.index_name, qdata, ctx.options
        )

        processed = self.utils.process_results(
            all_results, qdata, limit=ctx.options.limit
        )

        if ctx.is_resto_index :
            logger.debug(
                "Enrichissement des %s restos pour l'utilisateur %s",
                len(processed['hits']), ctx.user_id
            )
            processed['hits'] = (
                await self.resto_pastille_service.append_resto_pastille(
                    datas=processed['hits'],
                    user_id=ctx.user_id
                )
            )

        count_per_dep = self._calculate_count_per_dep(processed['hits'])

        duration = time.time() - ctx.start_time
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024

        logger.info(
            "Recherche avancée (index: %s, query: %s) : "
            "Durée = %.4fs | RAM = %.2f Mo",
            ctx.index_name, qdata.original, duration, memory_mb
        )

        return SearchResponse(
            hits=processed['hits'],
            total=processed['total'],
            has_exact_results=processed['has_exact_results'],
            exact_count=processed['exact_count'],
            total_before_filter=processed['total_before_filter'],
            query_time_ms=processed['query_time_ms'],
            preprocessing=qdata,
            memory_used_mb=memory_mb,
            count_per_dep=count_per_dep,
        )
