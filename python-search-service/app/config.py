from pydantic import BaseSettings

class Settings(BaseSettings):
    MEILISEARCH_HOST: str = "http://127.0.0.1:7700"
    MEILISEARCH_KEY: str = "masterKey"
    CACHE_MAX_SIZE: int = 1000

settings = Settings()
