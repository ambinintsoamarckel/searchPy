from typing import List, Dict, Any, Optional
# On ne met pas 'import asyncpg' ici, car seul le Connector en a besoin.
# from .config import settings # ❌ Retiré: le service n'a pas besoin de la config, seulement du Connector.

# 💡 Nous supposons que PostgresConnector est importable pour l'annotation de type.
# Si PostgresConnector est dans un chemin comme 'app.db.postgres_connector', vous devez l'importer.
# Dans un environnement moderne, vous pouvez utiliser un string forward reference pour éviter la dépendance circulaire.
# Pour la simplicité, supposons que PostgresConnector est importé (ou utilisez un commentaire).

# from app.db.postgres_connector import PostgresConnector # Import requis si utilisé

# Utilisé pour l'annotation de type si l'importation crée des problèmes de cycle.
PostgresConnector = Any

class RestoPastilleService:
    """Service d'enrichissement des données de restaurant avec les pastilles (isDeleted, Favori, Modifs)."""

    def __init__(self, db_connector: PostgresConnector):
        # 💡 Injection de la dépendance du connecteur DB
        self.db = db_connector

    async def append_resto_pastille(
        self,
        datas: List[Dict[str, Any]],
        user_id: Optional[int] # L'ID de l'utilisateur est conservé
    ) -> List[Dict[str, Any]]:
        """
        Enrichit les données de restaurant existantes (datas) avec les pastilles.
        """
        if not datas:
            return datas

        # 1) Construire la liste unique d'IDs depuis 'datas' uniquement
        ids_set: Dict[int, bool] = {}
        for d in datas:
            if d.get('id') is not None:
                # S'assurer que 'id' est un entier valide
                try:
                    ids_set[int(d['id'])] = True
                except (ValueError, TypeError):
                    continue

        all_ids: List[int] = list(ids_set.keys())
        if not all_ids:
            return datas

        # --- 2) Accès à la base de données en bulk (SQL Brutes) ---

        # 2a) is_deleted
        is_deleted_rows: List[Dict[str, Any]] = await self.db.execute_query(
            "SELECT id, is_deleted FROM bdd_resto WHERE id = ANY(:ids)",
            {'ids': all_ids}
        )
        is_deleted_map: Dict[int, int] = {
            row['id']: int(row['is_deleted']) for row in is_deleted_rows
        }

        # 2b) Modifs
        modif_rows: List[Dict[str, Any]] = await self.db.execute_query(
            "SELECT resto_id, status, action FROM bdd_resto_usrmodif WHERE resto_id = ANY(:ids)",
            {'ids': all_ids}
        )
        modif_map: Dict[int, Dict[str, Any]] = {
            int(row['resto_id']): {
                'status': int(row['status']),
                'action': str(row['action']),
            }
            for row in modif_rows
        }

        # 2c) Favoris : SQL natif
        favori_map: Dict[int, bool] = {}
        if user_id:
            table_favori_folder = f'favori_folder_{user_id}'
            table_favori = f'favori_etablisment_{user_id}'

            # Requête SQL pour récupérer tous les IDs favoris
            sql_favori = f"""
                SELECT idRubrique
                FROM {table_favori}
                WHERE (rubriqueType = 'resto' OR rubriqueType = 'restaurant')
                  AND idRubrique = ANY(:ids)
            """

            favori_rows: List[Dict[str, Any]] = await self.db.execute_query(
                sql_favori,
                {'ids': all_ids}
            )

            for row in favori_rows:
                favori_map[int(row['idRubrique'])] = True

        # 3) Enrichir datas (boucle finale)
        for data in datas:
            id_resto = int(data.get('id', 0))

            # a) isDeleted
            data['isDeleted'] = is_deleted_map.get(id_resto, 0)

            # b) Modifs (isWaiting, isModified)
            modif = modif_map.get(id_resto)

            is_waiting = modif is not None and modif['status'] == -1
            is_modified = modif is not None and modif['action'] == 'modifier'

            data['isWaiting'] = is_waiting
            data['isModified'] = is_modified

            # c) Favoris (hasFavori)
            # True si user_id est présent ET l'ID resto est dans favori_map
            data['hasFavori'] = bool(user_id and favori_map.get(id_resto))

        return datas
