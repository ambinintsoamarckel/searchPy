# app/search/search_service.py
import asyncio
import time
import psutil
from typing import List, Dict, Any, Optional, Union
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
            self, index_name: str, query: str, attributes: List[str], options: SearchOptions
        ) -> Dict[str, Any]: # CHANGEMENT : Mettre le type de retour à Dict[str, Any] ou l'objet SearchResults
        index = await self.client.get_index(index_name)

        # res est l'objet SearchResults complet du client Meilisearch
        res = await index.search(
            query,
            limit=options.limit,
            attributes_to_search_on=attributes,
            filter=options.filters,
            sort=options.sort,
            offset=options.offset,
        )

        # --- CORRECTION ICI : Renvoyer le résultat brut ---
        # Si vous utilisez un client Meilisearch moderne (async/await),
        # l'objet 'res' est généralement soit un dictionnaire, soit un objet
        # avec des propriétés comme 'hits', 'estimatedTotalHits', etc.

        # Pour être sûr que la fonction appelante (search) reçoive un dictionnaire
        # (car elle tente d'utiliser .get()), nous allons le convertir si nécessaire :

        # Le client Python Meilisearch renvoie souvent une instance de SearchResults
        # qui est itérable comme un dictionnaire. Si vous avez besoin d'un dict pur :
        if hasattr(res, 'dict'):
            return res.dict()

        # Si c'est déjà un dictionnaire ou l'objet se comporte bien :
        return res

        # Supprimez les lignes suivantes qui renvoyaient seulement hits:
        # hits = res.hits if hasattr(res, "hits") else []
        # return hits


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
            self._meili_search(index_name, q, attrs, options=options)
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


    async def search(
        self,
        index_name: str,
        qdata: Optional[Union[str, QueryData]],
        options: SearchOptions
    ) -> SearchResponse:
        """
        Recherche flexible qui gère 3 cas :
        1. qdata est None → recherche simple avec query vide (liste tous les résultats)
        2. qdata est un str → recherche simple avec ce texte
        3. qdata est un QueryData → recherche avancée avec scoring
        """

        t0 = time.time()

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

            # --- CORRECTION ICI ---
            # Le résultat de Meilisearch est un dictionnaire.
            # Les hits sont dans la clé 'hits' et le total est dans 'estimatedTotalHits'.
            hits = result.get('hits', [])# Récupère la liste des résultats (hits)
            estimated_total_hits = result.get('estimated_total_hits',0) # Récupère le nombre total estimé
            print(f"Meili search raw result: {estimated_total_hits}")

            # Si vous avez besoin d'une liste (même d'un seul élément) pour 'estimated_hits'
            # comme dans votre code original, vous pouvez la créer ainsi :

            # ----------------------

            logger.info(f"Hits estimés par stratégie : {estimated_total_hits}")
            print(f"Estimated total hits: {estimated_total_hits}")

            t1 = time.time()
            total_duration_sec = t1 - t0
            memory_used_mb = psutil.Process().memory_info().rss / 1024 / 1024

            logger.info(
                f"Recherche simple (index: {index_name}, query: '{query_text}') : "
                f"Durée = {total_duration_sec:.4f}s | RAM = {memory_used_mb:.2f} Mo"
            )

            return SearchResponse(
                # total est maintenant basé sur estimated_total_hits si vous voulez le total réel,
                # ou vous pouvez utiliser len(hits) si vous voulez juste le nombre d'éléments retournés
                hits=hits, # Utilisez la variable 'hits' que nous venons d'extraire
                total=len(hits), # Total estimé
                has_exact_results=False,
                exact_count=0,
                total_before_filter=estimated_total_hits if estimated_total_hits is not None else len(hits), # Total estimé
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
