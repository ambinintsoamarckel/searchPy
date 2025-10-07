from pydantic import BaseModel
from typing import Optional

class SearchRequest(BaseModel):
    query: str
    location: Optional[str] = None
    limit: int = 50

class SearchResult(BaseModel):
    id: str
    name: str
    score: float
    distance_m: Optional[float] = None
