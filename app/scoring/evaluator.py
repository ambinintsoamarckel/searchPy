"""Évaluation et scoring des champs."""
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models import QueryData
from app.scoring.distance import string_distance


class FieldEvaluator:
    """Évaluateur de champs pour le scoring."""

    def __init__(
        self,
        max_distance: int = settings.MAX_LEVENSHTEIN_DISTANCE,
        synonyms: Optional[Dict] = None,
    ):
        self.max_distance = max_distance
        original_synonyms = synonyms or settings.SYNONYMS_FR
        self._synonym_lookup: Dict[str, str] = self._build_synonym_lookup(
            original_synonyms
        )

    def _build_synonym_lookup(
        self, synonyms: Dict[str, List[str]]
    ) -> Dict[str, str]:
        """Construit une map pour un lookup rapide : mot_quelconque -> mot_base."""
        lookup = {}
        for base, syns in synonyms.items():
            lookup[base.lower()] = base.lower()
            for syn in syns:
                lookup[syn.lower()] = base.lower()
        return lookup

    def apply_synonyms(self, word1: str, word2: str) -> Optional[str]:
        """Vérifie si deux mots sont synonymes en utilisant le lookup map."""
        w1 = word1.lower()
        w2 = word2.lower()
        base1 = self._synonym_lookup.get(w1, w1)
        base2 = self._synonym_lookup.get(w2, w2)
        if base1 == base2 and base1 in self._synonym_lookup:
            return word2
        return None

    def calculate_word_match(
        self, query_word: str, candidate_word: str
    ) -> Dict[str, Any]:
        """Calcule le match entre deux mots."""
        q = query_word.lower()
        c = candidate_word.lower()

        if q == c:
            return {"distance": 0, "type": "exact", "matched_word": candidate_word}

        if self.apply_synonyms(q, c) is not None:
            return {"distance": 0, "type": "synonym", "matched_word": candidate_word}

        max_dist = min(self.max_distance, string_distance.dynamic_max(q))
        distance = string_distance.distance(q, c, max_dist)
        return {"distance": distance, "type": "levenshtein", "matched_word": candidate_word}

    def find_best_word_match(
        self, query_word: str, candidate_words: List[str], used_positions: Dict[int, bool]
    ) -> Optional[Dict[str, Any]]:
        """Trouve le meilleur match pour un mot de la query."""
        best_match = None
        best_distance = self.max_distance + 1

        for position, candidate_word in enumerate(candidate_words):
            if used_positions.get(position, False):
                continue

            match = self.calculate_word_match(query_word, candidate_word)
            if match["distance"] < best_distance:
                best_match = match
                best_match["position"] = position
                best_distance = match["distance"]
                if best_distance == 0:
                    break

        if best_match:
            used_positions[best_match["position"]] = True
        return best_match

    def _calculate_evaluation_metrics(
        self,
        found: List[Dict],
        not_found: List[str],
        total_distance: int,
        query_words: List[str],
        candidate_words: List[str],
        query_text: str,
    ) -> Dict[str, Any]:
        """Calcule les métriques de l'évaluation."""
        found_count = len(found)
        query_count = len(query_words)
        candidate_count = len(candidate_words)
        avg_distance = total_distance / found_count if found_count > 0 else 0.0
        missing_terms = len(not_found)

        length_ratio = (
            min(query_count, candidate_count) / max(query_count, candidate_count)
            if query_count and candidate_count
            else 1.0
        )
        coverage_ratio = found_count / query_count if query_count > 0 else 1.0

        found_positions = {f["position"] for f in found}
        extra_length = sum(
            len(word) for pos, word in enumerate(candidate_words) if pos not in found_positions
        )
        query_length = len(query_text)
        extra_length_ratio = extra_length / query_length if query_length > 0 else 0.0

        metrics = {
            "total_distance": total_distance,
            "average_distance": avg_distance,
            "found_count": found_count,
            "query_count": query_count,
            "result_count": candidate_count,
            "extra_length": extra_length,
            "extra_length_ratio": extra_length_ratio,
        }
        metrics["penalties"] = {
            "mots_manquants": missing_terms,
            "distance_moyenne": avg_distance,
            "longueur_ratio": length_ratio,
            "coverage_ratio": coverage_ratio,
            "extra_length": extra_length,
            "extra_length_ratio": extra_length_ratio,
        }
        return metrics

    def evaluate_field(
        self, query_words: List[str], candidate_words: List[str], query_text: str
    ) -> Dict[str, Any]:
        """Évalue un champ en comparant les mots de la query aux mots du candidat."""
        found, not_found, total_distance = [], [], 0
        used_positions: Dict[int, bool] = {}

        for q_word in query_words:
            best = self.find_best_word_match(q_word, candidate_words, used_positions)
            if best and best["distance"] <= self.max_distance:
                found.append(
                    {
                        "query_word": q_word,
                        "matched_word": best["matched_word"],
                        "distance": best["distance"],
                        "type": best["type"],
                        "position": best["position"],
                    }
                )
                total_distance += best["distance"]
            else:
                not_found.append(q_word)

        metrics = self._calculate_evaluation_metrics(
            found, not_found, total_distance, query_words, candidate_words, query_text
        )
        return {"found": found, "not_found": not_found, **metrics}

    def _calculate_strategy_score(self, eval_result: Dict[str, Any]) -> float:
        """Calcule le score ajusté pour une évaluation de stratégie."""
        if eval_result["found_count"] == 0:
            return 0.0

        p = eval_result["penalties"]
        score = 10 - eval_result["total_distance"]
        score = max(0.0, min(10.0, score))

        penalty = (
            settings.W_MISSING * p["mots_manquants"]
            + settings.W_FUZZY * max(0.0, p["distance_moyenne"])
            + settings.W_RATIO * (1.0 - max(0.0, min(1.0, p["longueur_ratio"])))
            + settings.W_EXTRA_LENGTH * p["extra_length_ratio"] * 10
        )
        return max(0.0, score - penalty)

    def _determine_winning_strategy(
        self,
        name_search_score: float,
        no_space_score: float,
        eval_search: Dict[str, Any],
        eval_no_space: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Détermine la stratégie gagnante entre name_search et no_space."""
        search_valid = name_search_score > 0 and eval_search["found_count"] > 0
        no_space_valid = no_space_score > 0 and eval_no_space["found_count"] > 0

        if no_space_valid and (not search_valid or no_space_score >= name_search_score):
            return {"strategy": "no_space", "base_score": no_space_score, "eval": eval_no_space}
        if search_valid:
            return {"strategy": "name_search", "base_score": name_search_score, "eval": eval_search}
        return {"strategy": "none", "base_score": 0.0, "eval": eval_search}

    def _determine_match_type(
        self, winning_eval: Dict[str, Any], winning_strategy: str, total_score: float
    ) -> str:
        """Détermine le type de match basé sur l'évaluation gagnante."""
        if winning_eval["found_count"] == 0:
            return "partial"

        avg = winning_eval["average_distance"]
        missing = winning_eval["penalties"]["mots_manquants"]
        extra_ratio = winning_eval["penalties"]["extra_length_ratio"]

        if avg == 0.0:
            if missing == 0 and extra_ratio == 0.0:
                match_type = "exact_full"
            elif missing == 0:
                match_type = (
                    "no_space_match"
                    if winning_strategy == "no_space"
                    else "exact_with_extras"
                )
            else:
                match_type = "exact_with_missing"
        else:
            match_type = "fuzzy_full" if missing == 0 else "fuzzy_partial"

        if match_type == "fuzzy_full" and total_score >= 8.0:
            match_type = "near_perfect"
        return match_type

    def calculate_main_score(
        self, hit: Dict[str, Any], query_data: QueryData
    ) -> Dict[str, Any]:
        """Calcule le score principal (name_search vs no_space)."""
        if not query_data.wordsCleaned:
            return {
                "total_score": 0.0, "winning_strategy": "none", "match_type": "partial",
                "match_priority": settings.TYPE_PRIORITY["partial"], "details": {"error": "empty_query"}
            }

        name_search_words = str(hit.get("name_search", "")).lower().split()
        name_no_space_words = str(hit.get("name_no_space", "")).lower().split()

        eval_search = self.evaluate_field(
            query_data.wordsCleaned, name_search_words, query_data.cleaned
        )
        name_search_score = self._calculate_strategy_score(eval_search)

        eval_no_space = self.evaluate_field(
            query_data.wordsNoSpace, name_no_space_words, query_data.no_space
        )
        no_space_score = self._calculate_strategy_score(eval_no_space)
        if no_space_score < settings.NO_SPACE_MIN_SCORE:
            no_space_score = 0.0

        winner = self._determine_winning_strategy(
            name_search_score, no_space_score, eval_search, eval_no_space
        )
        base_score = winner["base_score"]
        winning_eval = winner["eval"]

        name_words = str(hit.get("name") or hit.get("nom", "")).lower().split()
        eval_name = self.evaluate_field(
            query_data.wordsOriginal, name_words, query_data.original
        )
        bonus = self.calculate_name_bonus(eval_name, query_data.wordsOriginal)
        total_score = min(12.0, base_score + bonus)

        match_type = self._determine_match_type(
            winning_eval, winner["strategy"], total_score
        )

        return {
            "name_search_score": name_search_score, "no_space_score": no_space_score,
            "base_score": base_score, "winning_strategy": winner["strategy"],
            "name_score": bonus, "total_score": total_score,
            "name_search_matches": eval_search, "no_space_matches": eval_no_space,
            "name_matches": eval_name, "_penalty_indices": winning_eval["penalties"],
            "all_words_found": winning_eval["penalties"]["mots_manquants"] == 0,
            "match_type": match_type,
            "match_priority": settings.TYPE_PRIORITY.get(
                match_type, settings.TYPE_PRIORITY["partial"]
            ),
        }

    def _calculate_bonus_score_terms(self, found_matches: List[Dict]) -> float:
        """Calcule le score pondéré des termes trouvés pour le bonus."""
        score_terms = 0.0
        for m in found_matches:
            dist = m["distance"]
            if dist == 0: score_terms += 1.0
            elif dist == 1: score_terms += 0.7
            elif dist == 2: score_terms += 0.4
            else: score_terms += 0.2
        return score_terms

    def calculate_name_bonus(
        self, eval_name: Dict[str, Any], query_words: List[str]
    ) -> float:
        """Calcule le bonus progressif sur le champ name."""
        pn = eval_name["penalties"]
        word_count_ratio = pn["longueur_ratio"]
        extra_length_ratio = pn["extra_length_ratio"]

        if (
            word_count_ratio < settings.BONUS_WORD_RATIO_MIN
            or extra_length_ratio > settings.BONUS_EXTRA_RATIO_MAX
        ):
            return 0.0

        score_terms = self._calculate_bonus_score_terms(eval_name["found"])
        score_ratio = score_terms / max(1, len(query_words))
        bonus_base = settings.BONUS_MAX * score_ratio

        bonus_reduction = (
            settings.BONUS_A_MISSING * pn["mots_manquants"]
            + settings.BONUS_C_AVGDIST * max(0.0, eval_name["average_distance"])
            + settings.BONUS_MAX * extra_length_ratio * 0.6
        )
        bonus = max(0.0, min(settings.BONUS_MAX, bonus_base - bonus_reduction))

        attenuation_range = 1.0 - settings.BONUS_WORD_RATIO_MIN
        attenuation_factor = (
            (word_count_ratio - settings.BONUS_WORD_RATIO_MIN) / attenuation_range
        )
        attenuation_factor = max(0.0, min(1.0, attenuation_factor))

        return bonus * attenuation_factor

    def calculate_final_score(
        self, main_score: Dict[str, Any], phon_score: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Calcule le score final en combinant score textuel et score phonétique."""
        if not main_score or "total_score" not in main_score:
            return {"score": 0.0, "type": "invalid", "method": "error"}

        text_score = float(main_score.get("total_score", 0))
        phon_value = float(phon_score.get("score", 0)) if phon_score else 0.0

        if text_score >= 8.5:
            return {
                "score": text_score, "type": main_score.get("match_type", "text"),
                "method": "text_only",
            }

        if 6.0 <= text_score < 8.5 and phon_value > 0:
            text_weight = 0.7 + (text_score / 40.0)
            phon_weight = 1.0 - text_weight
            hybrid_score = (text_score * text_weight) + (phon_value * phon_weight)
            return {
                "score": round(hybrid_score, 2), "type": "hybrid", "method": "weighted",
                "weights": {"text": round(text_weight, 2), "phon": round(phon_weight, 2)},
            }

        if phon_value > text_score:
            return {
                "score": phon_value,
                "type": phon_score.get("match_type", "phonetic") if phon_score else "phonetic",
                "method": "phonetic_fallback",
            }

        return {
            "score": text_score, "type": main_score.get("match_type", "text"),
            "method": "text_only",
        }