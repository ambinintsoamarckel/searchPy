"""Modèles Pydantic pour les requêtes et réponses."""
from typing import List, Optional, Dict, Any,Union
from pydantic import BaseModel, Field
from app.config import settings

class QueryData(BaseModel):
    """Données de la query préprocessée."""
    original: str
    cleaned: str
    no_space: str
    soundex: str
    original_length: int
    cleaned_length: int
    no_space_length: int
    wordsCleaned: List[str]
    wordsOriginal: List[str]
    wordsNoSpace: List[str]


class SearchOptions(BaseModel):
    limit: int = 10
    offset: int = 0  # Ajout ou confirmation
    # Le tri pour Meilisearch est une liste de chaînes: ["field:order"]
    sort: Optional[List[str]] = None
    # Le champ filters est déjà pris en compte
    filters: Optional[list[str]] = None
    max_distance: int = settings.MAX_LEVENSHTEIN_DISTANCE
    # ... autres options ...


class SearchRequest(BaseModel):
    """Requête de recherche."""
    index_name: str
    query_data: Optional[Union[str,  QueryData]] = None
    options: SearchOptions = Field(default_factory=SearchOptions)


class MatchDetails(BaseModel):
    """Détails d'un match."""
    found: List[Dict[str, Any]]
    not_found: List[str]
    total_distance: float
    average_distance: float
    extra_length: int
    extra_length_ratio: float


class ScoredHit(BaseModel):
    """Hit avec score calculé."""
    # Données du hit original (flexible)
    id: Optional[Any] = None
    id_etab: Optional[Any] = None
    name: Optional[str] = None
    nom: Optional[str] = None

    # Scoring
    _score: float
    _match_type: str
    _match_priority: int
    _discovery_strategy: str

    # Détails optionnels
    _penalty_indices: Optional[Dict[str, float]] = None
    name_search_score: Optional[float] = None
    no_space_score: Optional[float] = None
    base_score: Optional[float] = None
    name_score: Optional[float] = None
    winning_strategy: Optional[str] = None

    class Config:
        extra = "allow"  # Permet des champs supplémentaires


class SearchResponse(BaseModel):
    """Réponse de recherche."""
    hits: List[Dict[str, Any]]
    total: int
    has_exact_results: bool
    exact_count: int
    total_before_filter: int
    query_time_ms: float
    preprocessing: Optional[QueryData] = None
    memory_used_mb: Optional[float] = None
    count_per_dep: Dict[str, int] = Field(default_factory=dict)

    class Config:
        extra = "allow"
