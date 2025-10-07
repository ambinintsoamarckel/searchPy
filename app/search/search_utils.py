import asyncio
from typing import List, Dict, Any, Optional
import time
import psutil

from meilisearch_async import Client as MeiliClient
import numpy as np
from Levenshtein import distance as lev_distance

from app.models import QueryData, SearchOptions, ScoredHit, SearchResponse
from app.scoring.evaluator import FieldEvaluator
from app.scoring.ranking import Ranker


class SearchService:
    """Delegates Meilisearch queries, deduplication, vectorized scoring and ranking.

    This implementation focuses on being memory- and CPU-friendly by
    - requesting only required attributes
    - streaming/processing hits in batches when possible
    - vectorizing distance computations with numpy where applicable
    """

    def __init__(self, meili_host: str = None, meili_key: str = None):
        self.meili_host = meili_host or "http://127.0.0.1:7700"
        self.meili_key = meili_key or "masterKey"
        self.client = MeiliClient(self.meili_host, self.meili_key)
        self.evaluator = FieldEvaluator()
        self.ranker = Ranker()

    async def _meili_search(self, index_name: str, query: str, attributes: List[str], limit: int, filters: Optional[str] = None) -> List[Dict[str, Any]]:
        index = await self.client.get_index(index_name)
        search_params = {"limit": limit, "attributesToCrop": [], "attributesToRetrieve": attributes}
        if filters:
            search_params['filter'] = filters
        res = await index.search(query, search_params)
        # meilisearch-async returns a dict-like with 'hits'
        hits = res.get('hits', []) if isinstance(res, dict) else []
        # annotate discovery strategy is done by caller
        return hits

    async def _parallel_strategies(self, index_name: str, qdata: QueryData, options: SearchOptions) -> Dict[str, List[Dict[str, Any]]]:
        limit = options.limit
        filters = options.filters

        strategies = {
            'name_search': (qdata.cleaned or qdata.original, ['name_search']),
            'no_space': (qdata.no_space, ['name_no_space']),
            'standard': (qdata.original, ['name']),
        }
        if qdata.soundex:
            strategies['phonetic'] = (qdata.soundex, ['name_soundex'])

        tasks = []
        for strat, (q, attrs) in strategies.items():
            tasks.append(self._meili_search(index_name, q, attrs, limit, filters))

        results = await asyncio.gather(*tasks)
        return dict(zip(list(strategies.keys()), results))

    def _deduplicate(self, all_results: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        seen = set()
        order = ['name_search', 'no_space', 'standard', 'phonetic']
        unique = []
        for strat in order:
            for hit in all_results.get(strat, []):
                hid = hit.get('id') or hit.get('id_etab')
                if hid is None:
                    # fallback to name-based fingerprint
                    hid = (hit.get('name') or hit.get('nom') or '')[:200]
                if hid in seen:
                    continue
                seen.add(hid)
                hit['_discovery_strategy'] = strat
                unique.append(hit)
        return unique

    def _vectorized_score(self, hits: List[Dict[str, Any]], qdata: QueryData, options: SearchOptions) -> List[ScoredHit]:
        # For memory: process in chunks
        CHUNK = 200_000
        out: List[ScoredHit] = []
        n = len(hits)
        for i in range(0, n, CHUNK):
            chunk = hits[i:i+CHUNK]
            names = [ (h.get('name') or h.get('nom') or '') for h in chunk ]
            # Compute distances using C extension in a vectorized loop (numpy helps store floats)
            q = qdata.cleaned or qdata.original
            dist_arr = np.fromiter((lev_distance(q.lower(), nm.lower()) for nm in names), dtype=np.int32)
            max_len = np.maximum(np.fromiter((max(len(q), len(nm)) for nm in names), dtype=np.int32), 1)
            score_arr = (max_len - dist_arr) / max_len * 10.0
            # small prefix bonus
            prefix_bonus = np.fromiter((1.5 if nm.lower().startswith(q.lower()) and q else 0.0 for nm in names), dtype=np.float32)
            final_scores = np.clip(score_arr.astype(np.float32) + prefix_bonus, 0.0, 12.0)

            for idx, h in enumerate(chunk):
                s = float(final_scores[idx])
                scored = ScoredHit(**{**h, '_score': s, '_match_type': h.get('_discovery_strategy','text'), '_match_priority': 0})
                out.append(scored)
        return out

    def _sort_and_trim(self, scored: List[ScoredHit], limit: int) -> List[Dict[str, Any]]:
        # convert to dicts for compatibility
        arr = [s.dict() for s in scored]
        sorted_arr = self.ranker.rank(arr)
        return sorted_arr[:limit]

    async def search(self, index_name: str, qdata: QueryData, options: SearchOptions) -> SearchResponse:
        t0 = time.time()
        # 1) execute strategies in parallel
        all_results = await self._parallel_strategies(index_name, qdata, options)
        # 2) deduplicate by id (priority-preserving)
        unique = self._deduplicate(all_results)
        # 3) scoring (vectorized)
        scored = self._vectorized_score(unique, qdata, options)
        # 4) sort and trim
        final = self._sort_and_trim(scored, options.limit)

        t1 = time.time()
        resp = SearchResponse(
            hits=final,
            total=len(final),
            has_exact_results=any(h.get('_score',0) >= 10.0 for h in final),
            exact_count=sum(1 for h in final if h.get('_score',0) >= 10.0),
            total_before_filter=len(unique),
            query_time_ms=(t1-t0)*1000.0,
            preprocessing=qdata,
            memory_used_mb=psutil.Process().memory_info().rss/1024/1024,
        )
        return resp
