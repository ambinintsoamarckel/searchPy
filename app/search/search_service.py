# app/search/search_service.py
import asyncio
import time
import psutil
from typing import List, Dict, Any, Optional, Union
from meilisearch_python_sdk import AsyncClient as MeiliClient
from app.cache import cache_manager
import json

# 💡 Importez la classe correcte (RestoPastilleService est maintenant dans .resto_pastille_service)
from app.search.resto_pastille import RestoPastilleService

from app.config import settings
from app.models import QueryData, SearchOptions, SearchResponse
from app.search.search_utils import SearchUtils
import logging

logger = logging.getLogger("search-api")

class SearchService:
    """Service de recherche principal combinant stratégies Meilisearch + scoring SearchUtils."""

    # 💡 MODIFICATION : Injection de RestoPastilleService
    def __init__(self, resto_pastille_service: RestoPastilleService):
        self.meili_host = settings.MEILISEARCH_URL
        self.meili_key = settings.MEILISEARCH_API_KEY
        # Client Meilisearch asynchrone
        self.client = MeiliClient(self.meili_host, self.meili_key)
        self.utils = SearchUtils()
        # Stockage du service injecté
        self.resto_pastille_service = resto_pastille_service
        self.cache = cache_manager

    async def _meili_search(
            self, index_name: str, query: str, attributes: List[str], options: SearchOptions
        ) -> Dict[str, Any]:

        # ... (Logique inchangée pour _meili_search, qui est correcte) ...
        index = await self.client.get_index(index_name)

        res = await index.search(
            query,
            limit=options.limit,
            attributes_to_search_on=attributes,
            filter=options.filters,
            sort=options.sort,
            offset=options.offset,
        )

        # Conversion du résultat Meilisearch en dictionnaire standard
        if hasattr(res, 'dict'):
            return res.dict()
        return res


    async def _parallel_strategies(
        self, index_name: str, qdata: QueryData, options: SearchOptions
    ) -> Dict[str, List[Dict[str, Any]]]:
        # ... (Logique inchangée, elle est correcte) ...
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
            self._meili_search(index_name, q, attrs, options=options)
            for q, attrs in strategies.values()
        ]
        results = await asyncio.gather(*tasks)
        return dict(zip(strategies.keys(), results))


    def _calculate_count_per_dep(self, hits: List[Dict[str, Any]]) -> Dict[str, int]:
        # ... (Logique inchangée, elle est correcte) ...
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
            user_id: Optional[int] = None # Paramètre user_id ajouté
        ) -> SearchResponse:

        # Création d'une clé de cache unique
        cache_key = f"search:{index_name}:{str(qdata)}:{str(options)}:{user_id}"
        
        # 1. Essayer de récupérer depuis le cache
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            logger.info(f"Cache HIT for key: {cache_key}")
            # Désérialiser la réponse et la retourner
            return SearchResponse.parse_raw(cached_result)

        logger.info(f"Cache MISS for key: {cache_key}")
        # 2. Si pas dans le cache, exécuter la recherche
        response = await self._execute_search(index_name, qdata, options, user_id)

        # 3. Mettre le résultat dans le cache avant de le retourner
        await self.cache.set(cache_key, response.json(), expire=300) # Cache pour 5 minutes

        return response

    async def _execute_search(
            self,
            index_name: str,
            qdata: Optional[Union[str, QueryData]],
            options: SearchOptions,
            user_id: Optional[int] = None
        ) -> SearchResponse:

        t0 = time.time()
        is_resto_index = 'resto' in index_name or 'restaurant' in index_name


        # ========== CAS 1 & 2 : RECHERCHE SIMPLE ==========
        if qdata is None or isinstance(qdata, str):
            query_text = qdata if isinstance(qdata, str) else ""

            # Recherche simple avec _meili_search
            result = await self._meili_search(
                index_name=index_name,
                query=query_text,
                attributes=['name'],
                options=options
            )

            hits = result.get('hits', [])
            estimated_total_hits = result.get('estimated_total_hits',0)

            # 🚀 ENRICHISSEMENT DES RESTOS (CAS SIMPLE)
            if is_resto_index and user_id is not None:
                logger.debug(f"Enrichissement des {len(hits)} restos pour l'utilisateur {user_id}")
                # 💡 CORRECTION : Utilisation de l'instance injectée
                hits = await self.resto_pastille_service.append_resto_pastille(
                    datas=hits,
                    user_id=user_id
                )
            # ----------------------------------------------

            # ... (Logique de logging) ...
            t1 = time.time()
            total_duration_sec = t1 - t0
            memory_used_mb = psutil.Process().memory_info().rss / 1024 / 1024
            logger.info(
                f"Recherche simple (index: {index_name}, query: '{query_text}') : "
                f"Durée = {total_duration_sec:.4f}s | RAM = {memory_used_mb:.2f} Mo"
            )

            return SearchResponse(
                hits=hits,
                total=len(hits),
                has_exact_results=False,
                exact_count=0,
                total_before_filter=estimated_total_hits if estimated_total_hits is not None else len(hits),
                query_time_ms=(t1 - t0) * 1000,
                preprocessing=None,
                memory_used_mb=memory_used_mb,
                count_per_dep=self._calculate_count_per_dep(hits),
            )

        # --- Recherche avancée avec scoring ---
        t0 = time.time()

        # 1️⃣ Exécution parallèle des stratégies Meilisearch
        all_results = await self._parallel_strategies(index_name, qdata, options)

        # 2️⃣ Traitement complet (déduplication + scoring + tri)
        processed = self.utils.process_results(all_results, qdata, limit=options.limit)

        # 🚀 ENRICHISSEMENT DES RESTOS (CAS AVANCÉ)
        if is_resto_index:
            logger.debug(f"Enrichissement des {len(processed['hits'])} restos pour l'utilisateur {user_id}")
            # 💡 CORRECTION : Utilisation de l'instance injectée
            processed['hits'] = await self.resto_pastille_service.append_resto_pastille(
                datas=processed['hits'],
                user_id=user_id
            )
        # ----------------------------------------------

        # 3️⃣ Comptage par département
        count_per_dep = self._calculate_count_per_dep(processed['hits'])

        # 4️⃣ Construction de la réponse finale
        t1 = time.time()
        total_duration_sec = t1 - t0
        memory_used_mb = psutil.Process().memory_info().rss / 1024 / 1024
        logger.info(
            f"Recherche avancée (index: {index_name}, query: {qdata.original}) : "
            f"Durée = {total_duration_sec:.4f}s | RAM = {memory_used_mb:.2f} Mo"
        )

        return SearchResponse(
            hits=processed['hits'],
            total=processed['total'],
            has_exact_results=processed['has_exact_results'],
            exact_count=processed['exact_count'],
            total_before_filter=processed['total_before_filter'],
            query_time_ms=processed['query_time_ms'],
            preprocessing=qdata,
            memory_used_mb=memory_used_mb,
            count_per_dep=count_per_dep,
        )
