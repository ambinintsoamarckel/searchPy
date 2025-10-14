"""Module de service pour l'enrichissement des données restaurant."""

import asyncio
from typing import List, Dict, Any, Optional

PostgresConnector = Any


class RestoPastilleService:  # pylint: disable=too-few-public-methods
    """
    Service d'enrichissement des données de restaurant.

    Ajoute les pastilles (isDeleted, Favori, Modifs).
    """

    def __init__(self, db_connector: PostgresConnector):
        self.db = db_connector

    def _validate_user_id(self, user_id: int) -> int:
        """
        Valide que user_id est un entier positif.

        Évite les injections SQL.

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

    def _extract_ids_from_data(
            self,
            datas: List[Dict[str, Any]]) -> List[int]:
        """
        Extrait les IDs uniques des données.

        Args:
            datas: Liste des données de restaurant

        Returns:
            List[int]: Liste des IDs uniques
        """
        ids_set: Dict[int, bool] = {}
        for d in datas:
            if d.get('id') is not None:
                try:
                    ids_set[int(d['id'])] = True
                except (ValueError, TypeError):
                    continue
        return list(ids_set.keys())

    def _build_database_tasks(
            self,
            all_ids: List[int],
            user_id: Optional[int]) -> Dict[str, Any]:
        """
        Construit les tâches de requêtes en base de données.

        Args:
            all_ids: Liste des IDs à rechercher
            user_id: ID utilisateur optionnel

        Returns:
            Dict[str, Any]: Dictionnaire des tâches asyncio
        """
        tasks = {
            "is_deleted": self.db.execute_query(
                "SELECT id, is_deleted FROM bdd_resto WHERE id = ANY($1)",
                all_ids
            ),
            "modifs": self.db.execute_query(
                """SELECT resto_id, status, action
                FROM bdd_resto_usrmodif WHERE resto_id = ANY($1)""",
                all_ids
            )
        }

        if user_id:
            try:
                table_favori = self._get_favori_table_name(user_id)
                # Safe: user_id is validated as positive integer
                # Table name is constructed from validated integer only
                sql_favori = f"SELECT idRubrique FROM {table_favori} WHERE (rubriqueType = 'resto' OR rubriqueType = 'restaurant') AND idRubrique = ANY($1)"  # nosec B608

                tasks["favoris"] = self.db.execute_query(
                    sql_favori, all_ids
                )
            except ValueError as e:
                print(f"Invalid user_id for favoris query: {e}")
                empty_result = asyncio.sleep(0, result=[])
                tasks["favoris"] = asyncio.create_task(empty_result)

        return tasks

    def _build_maps_from_results(
            self,
            is_deleted_rows: List[Dict[str, Any]],
            modif_rows: List[Dict[str, Any]],
            favori_rows: List[Dict[str, Any]],
            user_id: Optional[int]) -> tuple:
        """
        Construit les maps à partir des résultats de requêtes.

        Args:
            is_deleted_rows: Résultats de la requête is_deleted
            modif_rows: Résultats de la requête modifs
            favori_rows: Résultats de la requête favoris
            user_id: ID utilisateur optionnel

        Returns:
            tuple: (is_deleted_map, modif_map, favori_map)
        """
        is_deleted_map: Dict[int, int] = {
            row['id']: int(row['is_deleted'])
            for row in is_deleted_rows
        }

        modif_map: Dict[int, Dict[str, Any]] = {
            int(row['resto_id']): {
                'status': int(row['status']),
                'action': str(row['action']),
            }
            for row in modif_rows
        }

        favori_map: Dict[int, bool] = {}
        if user_id:
            favori_map = {
                int(row['idRubrique']): True
                for row in favori_rows
            }

        return is_deleted_map, modif_map, favori_map

    def _enrich_single_data(
            self,
            data: Dict[str, Any],
            maps: Dict[str, Any],
            user_id: Optional[int]) -> None:
        """
        Enrichit un élément de données avec les pastilles.

        Args:
            data: Élément de données à enrichir
            maps: Dictionnaire contenant is_deleted_map, modif_map, favori_map
            user_id: ID utilisateur optionnel
        """
        id_resto = int(data.get('id', 0))

        # isDeleted
        data['isDeleted'] = maps['is_deleted'].get(id_resto, 0)

        # Modifs (isWaiting, isModified)
        modif = maps['modif'].get(id_resto)
        is_waiting = modif is not None and modif['status'] == -1
        is_modified = modif is not None and modif['action'] == 'modifier'

        data['isWaiting'] = is_waiting
        data['isModified'] = is_modified

        # Favoris (hasFavori)
        data['hasFavori'] = bool(
            user_id and maps['favori'].get(id_resto)
        )

    async def append_resto_pastille(
        self,
        datas: List[Dict[str, Any]],
        user_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """
        Enrichit les données de restaurant avec les pastilles.

        Args:
            datas: Liste des données de restaurant
            user_id: ID utilisateur optionnel

        Returns:
            List[Dict[str, Any]]: Données enrichies
        """
        if not datas:
            return datas

        # 1) Extraire les IDs
        all_ids = self._extract_ids_from_data(datas)
        if not all_ids:
            return datas

        # 2) Construire et exécuter les requêtes en parallèle
        tasks = self._build_database_tasks(all_ids, user_id)
        results = await asyncio.gather(*tasks.values())

        # Récupération des résultats
        is_deleted_rows = results[0]
        modif_rows = results[1]
        favori_rows = results[2] if user_id else []

        # 3) Construire les maps
        is_deleted_map, modif_map, favori_map = (
            self._build_maps_from_results(
                is_deleted_rows,
                modif_rows,
                favori_rows,
                user_id
            )
        )

        # Regrouper les maps dans un dictionnaire
        maps = {
            'is_deleted': is_deleted_map,
            'modif': modif_map,
            'favori': favori_map
        }

        # 4) Enrichir les données
        for data in datas:
            self._enrich_single_data(data, maps, user_id)

        return datas
