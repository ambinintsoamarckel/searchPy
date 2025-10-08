"""Évaluation et scoring des champs."""
import re
from typing import Dict, List, Tuple, Any, Optional
from app.config import settings
from app.scoring.distance import string_distance
from app.models import QueryData


class FieldEvaluator:
    """Évaluateur de champs pour le scoring."""

    def __init__(self, max_distance: int = settings.MAX_LEVENSHTEIN_DISTANCE, synonyms: Optional[Dict] = None):
        self.max_distance = max_distance
        self.synonyms = synonyms or {}

    def apply_synonyms(self, word1: str, word2: str) -> Optional[str]:
        """Vérifie si deux mots sont synonymes."""
        w1 = word1.lower()
        w2 = word2.lower()

        for base, syns in self.synonyms.items():
            in1 = (w1 == base) or (w1 in syns)
            in2 = (w2 == base) or (w2 in syns)
            if in1 and in2:
                return word2

        return None

    def calculate_word_match(self, query_word: str, candidate_word: str) -> Dict[str, Any]:
        """Calcule le match entre deux mots."""
        q = query_word.lower()
        c = candidate_word.lower()

        # Match exact
        if q == c:
            return {
                'distance': 0,
                'type': 'exact',
                'matched_word': candidate_word
            }

        # Synonyme
        if self.apply_synonyms(q, c) is not None:
            return {
                'distance': 0,
                'type': 'synonym',
                'matched_word': candidate_word
            }

        # Levenshtein
        max_dist = min(self.max_distance, string_distance.dynamic_max(q))
        distance = string_distance.distance(q, c, max_dist)

        return {
            'distance': distance,
            'type': 'levenshtein',
            'matched_word': candidate_word
        }

    def find_best_word_match(
        self,
        query_word: str,
        candidate_words: List[str],
        used_positions: Dict[int, bool]
    ) -> Optional[Dict[str, Any]]:
        """Trouve le meilleur match pour un mot de la query."""
        best_match = None
        best_distance = self.max_distance + 1

        for position, candidate_word in enumerate(candidate_words):
            if used_positions.get(position, False):
                continue

            match = self.calculate_word_match(query_word, candidate_word)

            if match['distance'] < best_distance:
                best_match = match
                best_match['position'] = position
                best_distance = match['distance']

                if best_distance == 0:
                    break

        if best_match:
            used_positions[best_match['position']] = True

        return best_match

    def evaluate_field(
        self,
        query_words: List[str],
        candidate_words: List[str],
        query_text: str
    ) -> Dict[str, Any]:
        """
        Évalue un champ en comparant les mots de la query aux mots du candidat.

        Returns:
            Dict contenant found, not_found, distances, pénalités, etc.
        """
        found = []
        not_found = []
        total_distance = 0
        used_positions = {}

        # Match de chaque mot de la query
        for q_word in query_words:
            best = self.find_best_word_match(q_word, candidate_words, used_positions)

            if best and best['distance'] <= self.max_distance:
                found.append({
                    'query_word': q_word,
                    'matched_word': best['matched_word'],
                    'distance': best['distance'],
                    'type': best['type'],
                    'position': best['position']
                })
                total_distance += best['distance']
            else:
                not_found.append(q_word)

        found_count = len(found)
        query_count = len(query_words)
        result_count = len(candidate_words)

        avg_distance = total_distance / found_count if found_count > 0 else 0.0
        missing_terms = len(not_found)
        length_ratio = (
            min(query_count, result_count) / max(query_count, result_count)
            if query_count and result_count else 1.0
        )
        coverage_ratio = found_count / query_count if query_count > 0 else 1.0

        # Calcul de la longueur des extras
        extra_length = 0
        found_positions = [f['position'] for f in found]
        for pos, word in enumerate(candidate_words):
            if pos not in found_positions:
                extra_length += len(word)

        query_length = len(query_text)
        extra_length_ratio = extra_length / query_length if query_length > 0 else 0.0

        return {
            'found': found,
            'not_found': not_found,
            'total_distance': total_distance,
            'average_distance': avg_distance,
            'found_count': found_count,
            'query_count': query_count,
            'result_count': result_count,
            'extra_length': extra_length,
            'extra_length_ratio': extra_length_ratio,
            'penalties': {
                'mots_manquants': missing_terms,
                'distance_moyenne': avg_distance,
                'longueur_ratio': length_ratio,
                'coverage_ratio': coverage_ratio,
                'extra_length': extra_length,
                'extra_length_ratio': extra_length_ratio,
            }
        }

    def calculate_main_score(self, hit: Dict[str, Any], query_data: QueryData) -> Dict[str, Any]:
        """
        Calcule le score principal (name_search vs no_space).

        Args:
            hit: Le hit Meilisearch
            query_data: Les données de la query préprocessée

        Returns:
            Dict avec scores, match_type, winning_strategy, etc.
        """
        query_clean_words = query_data.wordsCleaned
        query_original_words = query_data.wordsOriginal
        query_no_space_words = query_data.wordsNoSpace

        if not query_clean_words:
            return {
                'name_search_score': 0.0,
                'no_space_score': 0.0,
                'base_score': 0.0,
                'name_score': 0.0,
                'total_score': 0.0,
                'winning_strategy': 'none',
                '_penalty_indices': {},
                'details': {'error': 'empty_query'},
                'all_words_found': False,
                'match_type': 'partial',
                'match_priority': settings.TYPE_PRIORITY['partial'],
            }

        # Extraction des champs
        name_search = str(hit.get('name_search', ''))
        name_no_space = str(hit.get('name_no_space', ''))
        name = str(hit.get('name') or hit.get('nom', ''))

        # Tokenization
        name_search_words = [w for w in re.split(r'\s+', name_search.lower().strip()) if w]
        name_no_space_words = [w for w in re.split(r'\s+', name_no_space.lower().strip()) if w]
        name_words = [w for w in re.split(r'\s+', name.lower().strip()) if w]

        # Évaluation name_search
        eval_search = self.evaluate_field(query_clean_words, name_search_words, query_data.cleaned)
        p_search = eval_search['penalties']

        if eval_search['found_count'] == 0:
            name_search_score_adj = 0.0
        else:
            name_search_score = 10 - eval_search['total_distance']
            name_search_score = max(0.0, min(10.0, name_search_score))

            penalty_search = (
                settings.W_MISSING * p_search['mots_manquants']
                + settings.W_FUZZY * max(0.0, p_search['distance_moyenne'])
                + settings.W_RATIO * (1.0 - max(0.0, min(1.0, p_search['longueur_ratio'])))
                + settings.W_EXTRA_LENGTH * p_search['extra_length_ratio'] * 10
            )
            name_search_score_adj = max(0.0, name_search_score - penalty_search)

        # Évaluation no_space
        eval_no_space = self.evaluate_field(query_no_space_words, name_no_space_words, query_data.no_space)
        p_no_space = eval_no_space['penalties']

        if eval_no_space['found_count'] == 0:
            no_space_score_adj = 0.0
        else:
            no_space_score = 10 - eval_no_space['total_distance']
            no_space_score = max(0.0, min(10.0, no_space_score))

            penalty_no_space = (
                settings.W_MISSING * p_no_space['mots_manquants']
                + settings.W_FUZZY * max(0.0, p_no_space['distance_moyenne'])
                + settings.W_RATIO * (1.0 - max(0.0, min(1.0, p_no_space['longueur_ratio'])))
                + settings.W_EXTRA_LENGTH * p_no_space['extra_length_ratio'] * 10
            )
            no_space_score_adj = max(0.0, no_space_score - penalty_no_space)

            # Seuil minimal no_space
            if no_space_score_adj < settings.NO_SPACE_MIN_SCORE:
                no_space_score_adj = 0.0

        # Choix de la stratégie gagnante
        search_valid = name_search_score_adj > 0 and eval_search['found_count'] > 0
        no_space_valid = no_space_score_adj > 0 and eval_no_space['found_count'] > 0

        if no_space_valid and (not search_valid or no_space_score_adj >= name_search_score_adj):
            winning_strategy = 'no_space'
            base_score = no_space_score_adj
            winning_eval = eval_no_space
            winning_penalties = p_no_space
        elif search_valid:
            winning_strategy = 'name_search'
            base_score = name_search_score_adj
            winning_eval = eval_search
            winning_penalties = p_search
        else:
            winning_strategy = 'none'
            base_score = 0.0
            winning_eval = eval_search
            winning_penalties = p_search

        # Bonus sur name
        eval_name = self.evaluate_field(query_original_words, name_words, query_data.original)
        bonus = self.calculate_name_bonus(eval_name, query_original_words, query_data.original)

        total_score = min(12.0, base_score + bonus)

        # Détermination du match_type
        no_winning_match = winning_eval['found_count'] == 0

        if no_winning_match:
            match_type = 'partial'
        else:
            avg = winning_eval['average_distance']
            missing = winning_penalties['mots_manquants']
            extra_ratio = winning_penalties['extra_length_ratio']

            if avg == 0.0:
                if missing == 0 and extra_ratio == 0.0:
                    match_type = 'exact_full'
                elif missing == 0:
                    match_type = 'no_space_match' if winning_strategy == 'no_space' else 'exact_with_extras'
                else:
                    match_type = 'exact_with_missing'
            else:
                match_type = 'fuzzy_full' if missing == 0 else 'fuzzy_partial'

            if match_type == 'fuzzy_full' and total_score >= 8.0:
                match_type = 'near_perfect'

        return {
            'name_search_score': name_search_score_adj,
            'no_space_score': no_space_score_adj,
            'base_score': base_score,
            'winning_strategy': winning_strategy,
            'name_score': bonus,
            'total_score': total_score,
            'name_search_matches': {
                'found': eval_search['found'],
                'not_found': eval_search['not_found'],
                'total_distance': eval_search['total_distance'],
                'average_distance': eval_search['average_distance'],
                'extra_length': eval_search['extra_length'],
                'extra_length_ratio': eval_search['extra_length_ratio'],
            },
            'no_space_matches': {
                'found': eval_no_space['found'],
                'not_found': eval_no_space['not_found'],
                'total_distance': eval_no_space['total_distance'],
                'average_distance': eval_no_space['average_distance'],
                'extra_length': eval_no_space['extra_length'],
                'extra_length_ratio': eval_no_space['extra_length_ratio'],
            },
            'name_matches': {
                'found': eval_name['found'],
                'not_found': eval_name['not_found'],
                'total_distance': eval_name['total_distance'],
                'average_distance': eval_name['average_distance'],
                'extra_length': eval_name['extra_length'],
                'extra_length_ratio': eval_name['extra_length_ratio'],
            },
            '_penalty_indices': winning_penalties,
            'all_words_found': winning_penalties['mots_manquants'] == 0,
            'match_type': match_type,
            'match_priority': settings.TYPE_PRIORITY.get(match_type, settings.TYPE_PRIORITY['partial']),
            'details': {
                'query_words_count': len(query_clean_words),
                'name_search_words_count': len(name_search_words),
                'no_space_words_count': len(name_no_space_words),
                'name_words_count': len(name_words),
            }
        }

    def calculate_name_bonus(
        self,
        eval_name: Dict[str, Any],
        query_words: List[str],
        query_text: str
    ) -> float:
        """Calcule le bonus progressif sur le champ name."""
        query_word_count = len(query_words)
        name_word_count = eval_name['result_count']

        # Ratio nombre de mots
        word_count_ratio = (
            min(query_word_count, name_word_count) / max(query_word_count, name_word_count)
            if name_word_count > 0 else 0.0
        )

        # Ratio longueur d'extras
        extra_length_ratio = eval_name['extra_length_ratio']

        # Gates
        if word_count_ratio < settings.BONUS_WORD_RATIO_MIN or extra_length_ratio > settings.BONUS_EXTRA_RATIO_MAX:
            return 0.0

        # Score pondéré des termes trouvés
        score_terms = 0.0
        for m in eval_name['found']:
            dist = m['distance']
            if dist == 0:
                score_terms += 1.0
            elif dist == 1:
                score_terms += 0.7
            elif dist == 2:
                score_terms += 0.4
            else:
                score_terms += 0.2

        max_score = max(1, query_word_count)
        score_ratio = score_terms / max_score

        # Bonus de base
        bonus_base = settings.BONUS_MAX * score_ratio

        # Réductions
        pn = eval_name['penalties']
        bonus_reduction = (
            settings.BONUS_A_MISSING * pn['mots_manquants']
            + settings.BONUS_C_AVGDIST * max(0.0, eval_name['average_distance'])
            + settings.BONUS_MAX * extra_length_ratio * 0.6
        )

        bonus = max(0.0, min(settings.BONUS_MAX, bonus_base - bonus_reduction))

        # Atténuation selon ratio
        attenuation_range = 1.0 - settings.BONUS_WORD_RATIO_MIN
        attenuation_factor = (word_count_ratio - settings.BONUS_WORD_RATIO_MIN) / attenuation_range
        attenuation_factor = max(0.0, min(1.0, attenuation_factor))

        return bonus * attenuation_factor
    def calculate_final_score(
        self,
        main_score: Dict[str, Any],
        phon_score: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Calcule le score final en combinant score textuel et score phonétique.

        Args:
            main_score: Dictionnaire contenant 'total_score' et 'match_type'
            phon_score: Dictionnaire contenant 'score' et 'match_type' (optionnel)

        Returns:
            Dictionnaire avec le score final, le type de match et la méthode utilisée.
        """
        # Sécurité sur les entrées
        if not main_score or 'total_score' not in main_score:
            return {
                'score': 0.0,
                'type': 'invalid',
                'method': 'error',
                'details': {'reason': 'missing_main_score'}
            }

        text_score = float(main_score.get('total_score', 0))
        phon_value = float(phon_score.get('score', 0)) if phon_score else 0.0

        # Cas 1 : score textuel excellent → on ignore le phonétique
        if text_score >= 8.5:
            return {
                'score': text_score,
                'type': main_score.get('match_type', 'text'),
                'method': 'text_only',
            }

        # Cas 2 : score textuel bon (6 à 8.5) ET phonétique présent → hybride pondéré
        if 6.0 <= text_score < 8.5 and phon_value > 0:
            text_weight = 0.7 + (text_score / 40.0)  # pondération croissante
            phon_weight = 1.0 - text_weight
            hybrid_score = (text_score * text_weight) + (phon_value * phon_weight)

            return {
                'score': round(hybrid_score, 2),
                'type': 'hybrid',
                'method': 'weighted',
                'weights': {'text': round(text_weight, 2), 'phon': round(phon_weight, 2)},
            }

        # Cas 3 : textuel faible, mais phonétique meilleur → fallback phonétique
        if phon_value > text_score:
            return {
                'score': phon_value,
                'type': phon_score.get('match_type', 'phonetic') if phon_score else 'phonetic',
                'method': 'phonetic_fallback',
            }

        # Cas 4 : par défaut, on garde le score textuel
        return {
            'score': text_score,
            'type': main_score.get('match_type', 'text'),
            'method': 'text_only',
        }
