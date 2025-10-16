"""Modèles Pydantic pour les requêtes et réponses."""
from typing import List, Optional, Dict, Any,Union
from pydantic import BaseModel, Field, ConfigDict
from app.config import settings

class QueryData(BaseModel): # pylint: disable=too-few-public-methods
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


class SearchOptions(BaseModel): # pylint: disable=too-few-public-methods
    """Options for a search query."""
    # Limite de récupération des candidats depuis Meilisearch (surtout pour la recherche avancée)
    limit: int = 200
    # Nombre de résultats par page pour la pagination finale
    per_page: int = 10
    offset: int = 0
    # Le tri pour Meilisearch est une liste de chaînes: ["field:order"]
    sort: Optional[List[str]] = None
    # Le champ filters est déjà pris en compte
    filters: Optional[list[str]] = None
    max_distance: int = settings.MAX_LEVENSHTEIN_DISTANCE
    # ... autres options ...


class SearchRequest(BaseModel): # pylint: disable=too-few-public-methods
    """Requête de recherche."""
    index_name: str
    query_data: Optional[Union[str,  QueryData]] = None
    user_id: Optional[int] = None  # 👈 Ajout de user_id dans la requête
    options: SearchOptions = Field(default_factory=SearchOptions)



class SearchResponse(BaseModel): # pylint: disable=too-few-public-methods
    """Réponse de recherche."""
    hits: List[Dict[str, Any]]
    total: int # Représente le nombre total de résultats avant pagination
    has_exact_results: bool
    exact_count: int
    total_before_filter: int
    query_time_ms: float
    preprocessing: Optional[QueryData] = None
    memory_used_mb: Optional[float] = None
    count_per_dep: Dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")
