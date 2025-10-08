# app/search/search_service.py
import asyncio
import time
import psutil
from typing import List, Dict, Any, Optional
from meilisearch_python_sdk import AsyncClient as MeiliClient

from app.config import settings  # <--- on importe la config ici
from app.models import QueryData, SearchOptions, SearchResponse
from app.search.search_utils import SearchUtils
import logging

logger = logging.getLogger("search-api")

class SearchService:
    """Service de recherche principal combinant stratégies Meilisearch + scoring SearchUtils."""

    def __init__(self):
        self.meili_host = settings.MEILISEARCH_URL
        self.meili_key = settings.MEILISEARCH_API_KEY
        self.client = MeiliClient(self.meili_host, self.meili_key)
        self.utils = SearchUtils()

    async def _meili_search(
        self, index_name: str, query: str, attributes: List[str], limit: int, filters: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        index = await self.client.get_index(index_name)

        res = await index.search(
            query,
            limit=limit,
            attributes_to_search_on=attributes,
            filter=filters
        )

        # Utilisation correcte de l'objet SearchResults
        hits = res.hits if hasattr(res, "hits") else []
        return hits


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

    def _calculate_count_per_dep(self, hits: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Calcule le nombre de hits par code départemental (formaté sur 2 chiffres).
        """
        count_per_dep: Dict[str, int] = {}

        for item in hits:
            # Assurez-vous que 'dep' est le nom du champ dans vos hits
            dep = item.get('dep')

            if dep is not None:
                try:
                    # Convertir en entier, puis formater sur deux chiffres (ex: 5 -> '05')
                    dep_int = int(dep)
                    dep_key = f"{dep_int:02d}"

                    # Incrémenter le compteur
                    count_per_dep[dep_key] = count_per_dep.get(dep_key, 0) + 1
                except ValueError:
                    # Ignorer si la valeur de 'dep' n'est pas un nombre valide
                    continue

        # Trier par clé de département (alphabétique)
        # Note : Le tri n'est pas strictement nécessaire pour Python,
        # mais assure la même sortie que votre exemple PHP
        return dict(sorted(count_per_dep.items()))
    # Fichier : app/search/search_service.py
    async def search(self, index_name: str, qdata: QueryData, options: SearchOptions) -> SearchResponse:
        """Recherche complète : exécution parallèle, déduplication, scoring et tri."""
        t0 = time.time()

        # 1️⃣ Exécution parallèle Meilisearch
        all_results = await self._parallel_strategies(index_name, qdata, options)

        # 2️⃣ Traitement complet (déduplication + scoring + tri) via SearchUtils
        processed = self.utils.process_results(all_results, qdata, limit=options.limit)

        # 3️⃣ Comptage par département
        # Utilisez les hits finaux traités
        count_per_dep = self._calculate_count_per_dep(processed['hits'])

        # 4️⃣ Construction de la réponse finale
        t1 = time.time()

        # ... (logging de la durée et de la RAM) ...
        total_duration_sec = t1 - t0
        memory_used_mb = psutil.Process().memory_info().rss / 1024 / 1024

        logger.info(
            f"Requête complète (index: {index_name}, query: {qdata.original}) : "
            f"Durée = {total_duration_sec:.4f}s | "
            f"RAM utilisée = {memory_used_mb:.2f} Mo"
        )
        # -------------------------

        resp = SearchResponse(
            hits=processed['hits'],
            total=processed['total'],
            has_exact_results=processed['has_exact_results'],
            exact_count=processed['exact_count'],
            total_before_filter=processed['total_before_filter'],
            query_time_ms=processed['query_time_ms'],
            preprocessing=qdata,
            memory_used_mb=memory_used_mb,

            # --- AJOUT DU COMPTAGE ICI ---
            count_per_dep=count_per_dep,
            # -----------------------------
        )
        return resp
