"""Calcul de distance Levenshtein optimisé."""
import Levenshtein as lev
from typing import Optional


class StringDistance:
    """Classe pour calculer les distances entre chaînes."""

    def distance(self, s1: str, s2: str, max_distance: Optional[int] = None) -> int:
        """
        Calcule la distance de Levenshtein entre deux chaînes.

        Args:
            s1: Première chaîne
            s2: Deuxième chaîne
            max_distance: Distance maximale (si dépassée, retourne max_distance + 1)

        Returns:
            Distance de Levenshtein
        """
        if not s1 or not s2:
            return max(len(s1), len(s2))

        # Utilise python-Levenshtein (implémentation C ultra-rapide)
        dist = lev.distance(s1, s2)

        if max_distance is not None and dist > max_distance:
            return max_distance + 1

        return dist

    def dynamic_max(self, s: str) -> int:
        """
        Calcule la distance maximale dynamique selon la longueur.

        Args:
            s: Chaîne à analyser

        Returns:
            Distance maximale recommandée
        """
        length = len(s)

        if length <= 3:
            return 1
        elif length <= 6:
            return 2
        elif length <= 10:
            return 3
        else:
            return 4


# Instance globale réutilisable
string_distance = StringDistance()
