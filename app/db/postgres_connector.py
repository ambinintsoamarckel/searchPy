"""PostgreSQL database connector."""
from typing import List, Dict, Any, Optional
import asyncpg

class PostgresConnector:
    """Gère un pool de connexions asynchrone à PostgreSQL en utilisant l'URL."""

    # 1. Le constructeur prend maintenant l'URL directement
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Initialise le pool de connexions avec l'URL et max_size."""

        # asyncpg.create_pool accepte l'URL comme premier argument (dsn)
        # On passe l'URL et les autres paramètres optionnels (max_size, timeout, etc.)
        self._pool = await asyncpg.create_pool(
            dsn=self.database_url,  # 👈 Utilisation de l'URL complète
            max_size=10             # Nombre maximal de connexions simultanées
        )
        print("Pool de connexions asyncpg initialisé.")

    # ... (Les méthodes execute_query, is_table_exist, create_favori_table restent inchangées) ...

    async def execute_query(self, sql: str, *args) -> List[Dict[str, Any]]:
        """Exécute une requête SQL avec des paramètres variables."""
        if not self._pool:
            raise ConnectionError("Connection pool not initialized. Call .connect() first.")

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [dict(row) for row in rows]

    async def is_table_exist(self, table_name: str) -> bool:
        """Vérifie l'existence de la table."""
        sql = """SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = $1)"""
        if not self._pool:
            return False
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, table_name.lower())

    async def create_favori_table(self, user_id: int):
        """Crée les tables de favoris si elles n'existent pas."""
        logger.info(f"Tentative de création des tables de favoris pour l'utilisateur {user_id}.")

    async def close(self):
        """Ferme le pool de connexions proprement."""
        if self._pool:
            await self._pool.close()
