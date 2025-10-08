"""Modèles Pydantic pour les requêtes et réponses."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


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
    """Options de recherche."""
    limit: int = Field(default=1_000_000, ge=1, le=1_000_000)
    max_distance: int = Field(default=4, ge=0, le=10)
    filters: Optional[List[str]] = None


class SearchRequest(BaseModel):
    """Requête de recherche."""
    index_name: str
    query_data: QueryData
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
