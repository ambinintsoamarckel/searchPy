"""
SearchUtils - Version Python complète
Intègre le scoring textuel, phonétique et la logique de classement.
"""

import time
from typing import List, Dict, Any, Optional
from functools import cmp_to_key
from app.config import settings
from app.scoring.evaluator import FieldEvaluator
from app.scoring.phonetic import PhoneticScorer
from app.models import QueryData


class SearchUtils:
    """Utilitaire de recherche avec scoring hybride textuel/phonétique."""

    def __init__(
            self,
            max_distance: int = None,
            synonyms: Optional[Dict] = None):
        """Initialise SearchUtils avec les évaluateurs."""
        self.max_distance = (
            max_distance or settings.MAX_LEVENSHTEIN_DISTANCE
        )
        self.evaluator = FieldEvaluator(
            max_distance=self.max_distance,
            synonyms=synonyms
        )
        self.phonetic_scorer = PhoneticScorer()

    # -----------------------------------------------------------------
    # Évaluation complète d'un résultat
    # -----------------------------------------------------------------
    def classify_result(
            self,
            hit: Dict[str, Any],
            query_data: QueryData) -> Dict[str, Any]:
        """
        Classifie un résultat en combinant score textuel et phonétique.

        Args:
            hit: Le hit Meilisearch
            query_data: Les données de la query préprocessée

        Returns:
            Hit enrichi avec _score, _match_type, _match_priority
        """

        # --- Score textuel principal
        main_score = self.evaluator.calculate_main_score(hit, query_data)

        # --- Score phonétique
        phon_score = self.phonetic_scorer.calculate_phonetic_score(
            hit, query_data
        )

        # --- Score final hybride
        final_score = self.evaluator.calculate_final_score(
            main_score, phon_score
        )

        # Enrichissement du hit
        enriched = hit.copy()
        enriched['_score'] = final_score['score']
        enriched['_match_type'] = final_score['type']
        enriched['_match_method'] = final_score['method']

        # Cap strict : seul exact_full peut atteindre 10.0
        is_not_exact = enriched['_match_type'] != 'exact_full'
        is_high_score = enriched['_score'] >= settings.EXACT_THRESHOLD
        if is_not_exact and is_high_score:
            enriched['_score'] = settings.EXACT_FULL_CAP
            enriched['_capped'] = True

        # Ajout de la priorité
        enriched['_match_priority'] = settings.TYPE_PRIORITY.get(
            enriched['_match_type'],
            settings.TYPE_PRIORITY['partial']
        )

        return enriched

    # -----------------------------------------------------------------
    # Comparaison et tri
    # -----------------------------------------------------------------
    def compare_penalty_indices(
            self,
            a: Dict[str, Any],
            b: Dict[str, Any]) -> int:
        """Compare les pénalités pour le tri fin."""

        # 1) Extras par longueur
        extra_a = a.get('extra_length_ratio', 0.0)
        extra_b = b.get('extra_length_ratio', 0.0)
        if abs(extra_a - extra_b) > 0.01:
            return -1 if extra_a < extra_b else 1

        # 2) Ratio de longueur
        ratio_a = a.get('longueur_ratio', 1.0)
        ratio_b = b.get('longueur_ratio', 1.0)
        if abs(ratio_a - ratio_b) > 0.001:
            return -1 if ratio_a > ratio_b else 1

        # 3) Distance moyenne
        dist_a = a.get('distance_moyenne', 0.0)
        dist_b = b.get('distance_moyenne', 0.0)
        if dist_a < dist_b:
            return -1
        if dist_a > dist_b:
            return 1
        return 0

    def compare_results(
            self,
            a: Dict[str, Any],
            b: Dict[str, Any]) -> int:
        """Compare deux résultats pour le tri."""

        # 1) Score (descendant)
        score_a = a.get('_score', 0)
        score_b = b.get('_score', 0)
        if score_a != score_b:
            return -1 if score_a > score_b else 1

        # 2) Priorité du type (ascendant)
        priority_a = a.get('_match_priority', 999)
        priority_b = b.get('_match_priority', 999)
        if priority_a != priority_b:
            return -1 if priority_a < priority_b else 1

        # 3) Pénalités fines
        has_penalties = (
            '_penalty_indices' in a and '_penalty_indices' in b
        )
        if has_penalties:
            pen_cmp = self.compare_penalty_indices(
                a['_penalty_indices'],
                b['_penalty_indices']
            )
            if pen_cmp != 0:
                return pen_cmp

        # 4) Dénouage stable par ID
        id_a = a.get('id') or a.get('id_etab', '')
        id_b = b.get('id') or b.get('id_etab', '')
        if id_a < id_b:
            return -1
        if id_a > id_b:
            return 1

        return 0

    def sort_results(
            self,
            results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Trie les résultats selon la logique de comparaison."""
        return sorted(results, key=cmp_to_key(self.compare_results))

    # -----------------------------------------------------------------
    # Déduplication et pipeline de traitement
    # -----------------------------------------------------------------
    def deduplicate_results(
            self,
            all_results: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Déduplique les résultats par ID.

        Préserve la priorité des stratégies.

        Args:
            all_results: Dict avec clés 'name_search', 'no_space',
                         'standard', 'phonetic'. Chaque valeur est le
                         dictionnaire de résultat complet de Meilisearch.

        Returns:
            Liste unique de hits avec _discovery_strategy
        """
        unique = []
        seen = set()
        priority_order = [
            'name_search', 'no_space', 'standard', 'phonetic'
        ]

        for strategy in priority_order:
            if strategy not in all_results:
                continue

            # all_results[strategy] est le dict complet Meilisearch
            # On utilise .get('hits', []) pour obtenir les documents
            strategy_results = all_results[strategy].get('hits', [])

            for hit in strategy_results:
                hit_id = hit.get('id') or hit.get('id_etab')

                # Fallback : fingerprint sur le nom
                if hit_id is None:
                    hit_id = (
                        hit.get('name') or hit.get('nom') or ''
                    )[:200]

                if hit_id not in seen:
                    hit['_discovery_strategy'] = strategy
                    unique.append(hit)
                    seen.add(hit_id)

        return unique

    def process_results(
        self,
        all_results: Dict[str, List[Dict[str, Any]]],
        query_data: QueryData,
    ) -> Dict[str, Any]:
        """
        Traite les résultats : déduplique, score et trie. La pagination est gérée par l'appelant.

        Args:
            all_results: Résultats bruts des stratégies
            query_data: Données de la query

        Returns:
            Dict avec hits, total, has_exact_results, etc.
        """
        start_time = time.time()

        # 1) Déduplication
        dedup = self.deduplicate_results(all_results)
        total_before_filter = len(dedup)

        # 2) Scoring et filtrage immédiat
        enriched = []
        for hit in dedup:
            scored = self.classify_result(hit, query_data)
            if scored.get('_score', 0) >= settings.MIN_SCORE:
                enriched.append(scored)

        # 3) Tri des résultats
        sorted_results = self.sort_results(enriched)

        # 4) Détection des résultats exacts
        exact_results = [
            h for h in sorted_results
            if h.get('_score', 0) >= settings.EXACT_THRESHOLD
        ]
        has_exact_results = len(exact_results) > 0

        # Si exacts trouvés → ne garder qu'eux
        final_hits = (
            exact_results if has_exact_results else sorted_results
        )

        end_time = time.time()

        return {
            'hits': final_hits, # Retourne la liste complète triée
            'total': len(final_hits),
            'has_exact_results': has_exact_results,
            'exact_count': len(exact_results),
            'total_before_filter': total_before_filter,
            'query_time_ms': round((end_time - start_time) * 1000, 2),
        }

    # -----------------------------------------------------------------
    # Synonymes
    # -----------------------------------------------------------------
    def set_synonyms(self, synonyms: Dict[str, List[str]]) -> None:
        """Met à jour les synonymes de l'évaluateur."""
        self.evaluator.synonyms = synonyms or {}
