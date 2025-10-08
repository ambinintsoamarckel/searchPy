"""Configuration du microservice de recherche."""
from pydantic_settings import BaseSettings
from typing import Dict


class Settings(BaseSettings):
    """Configuration de l'application."""

    # Meilisearch
    MEILISEARCH_URL: str = "http://localhost:7700"
    MEILISEARCH_API_KEY: str = ""

    # Limites
    DEFAULT_LIMIT: int = 1_000_000
    MAX_LEVENSHTEIN_DISTANCE: int = 4
    MIN_SCORE: float = 3.0

    # Scoring - Pénalités
    W_MISSING: float = 0.6
    W_FUZZY: float = 0.5
    W_RATIO: float = 1.0
    W_EXTRA_LENGTH: float = 0.15

    # Scoring - Bonus
    BONUS_MAX: float = 2.0
    BONUS_A_MISSING: float = 0.3
    BONUS_C_AVGDIST: float = 0.35
    BONUS_WORD_RATIO_MIN: float = 0.4
    BONUS_EXTRA_RATIO_MAX: float = 1.0

    # Seuils
    EXACT_THRESHOLD: float = 10.0
    EXACT_FULL_CAP: float = 9.99
    NO_SPACE_MIN_SCORE: float = 7.0
    MIN_SCORE = 3.0


    # Priorités de type d'appariement
    TYPE_PRIORITY: Dict[str, int] = {
        'exact_full': 0,
        'exact_with_extras': 1,
        'no_space_match': 1,
        'near_perfect': 2,
        'phonetic_strict': 3,
        'exact_with_missing': 4,
        'fuzzy_full': 5,
        'hybrid': 6,
        'phonetic_tolerant': 7,
        'fuzzy_partial': 8,
        'partial': 9,
    }

    # Performance
    PARALLEL_STRATEGIES: bool = True
    ENABLE_METRICS: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
