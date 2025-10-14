import asyncio
from typing import List, Dict, Any, Optional
import re

PostgresConnector = Any

class RestoPastilleService:
    """Service d'enrichissement des données de restaurant avec les pastilles (isDeleted, Favori, Modifs)."""

    def __init__(self, db_connector: PostgresConnector):
        self.db = db_connector

    def _validate_user_id(self, user_id: int) -> int:
        """
        Valide que user_id est un entier positif pour éviter les injections SQL.

        Args:
            user_id: L'ID utilisateur à valider

        Returns:
            int: L'ID validé

        Raises:
            ValueError: Si l'ID n'est pas valide
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError(f"Invalid user_id: {user_id}")
        return user_id

    def _get_favori_table_name(self, user_id: int) -> str:
        """
        Construit le nom de la table favori de manière sécurisée.

        Args:
            user_id: L'ID utilisateur (doit être un entier positif)

        Returns:
            str: Le nom de la table favori
        """
        validated_id = self._validate_user_id(user_id)
        return f'favori_etablisment_{validated_id}'

    async def append_resto_pastille(
        self,
        datas: List[Dict[str, Any]],
        user_id: Optional[int]
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
                try:
                    ids_set[int(d['id'])] = True
                except (ValueError, TypeError):
                    continue

        all_ids: List[int] = list(ids_set.keys())
        if not all_ids:
            return datas

        # --- 2) Accès à la base de données en parallèle avec asyncio.gather ---

        tasks = {
            "is_deleted": self.db.execute_query(
                "SELECT id, is_deleted FROM bdd_resto WHERE id = ANY($1)", all_ids
            ),
            "modifs": self.db.execute_query(
                "SELECT resto_id, status, action FROM bdd_resto_usrmodif WHERE resto_id = ANY($1)", all_ids
            )
        }

        # Ajout de la requête pour les favoris si user_id est fourni
        if user_id:
            try:
                # ✅ Validation et construction sécurisée du nom de table
                table_favori = self._get_favori_table_name(user_id)

                # ✅ Utilisation de sql.Identifier si disponible avec asyncpg
                # Sinon, le nom est maintenant validé et sûr
                sql_favori = f"""
                    SELECT idRubrique
                    FROM {table_favori}
                    WHERE (rubriqueType = 'resto' OR rubriqueType = 'restaurant')
                      AND idRubrique = ANY($1)
                """
                tasks["favoris"] = self.db.execute_query(sql_favori, all_ids)
            except ValueError as e:
                # Si la validation échoue, on log et on continue sans favoris
                print(f"Invalid user_id for favoris query: {e}")
                tasks["favoris"] = asyncio.create_task(asyncio.sleep(0, result=[]))

        # Exécution des tâches en parallèle
        results = await asyncio.gather(*tasks.values())

        # Récupération des résultats
        is_deleted_rows, modif_rows = results[0], results[1]
        favori_rows = results[2] if user_id else []

        # --- Construction des maps à partir des résultats ---

        is_deleted_map: Dict[int, int] = {
            row['id']: int(row['is_deleted']) for row in is_deleted_rows
        }

        modif_map: Dict[int, Dict[str, Any]] = {
            int(row['resto_id']): {
                'status': int(row['status']),
                'action': str(row['action']),
            }
            for row in modif_rows
        }

        favori_map: Dict[int, bool] = {
            int(row['idRubrique']): True for row in favori_rows
        } if user_id else {}

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
            data['hasFavori'] = bool(user_id and favori_map.get(id_resto))

        return datas
