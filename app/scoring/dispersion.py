"""Service de dispersion géographique pour pagination équilibrée."""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from ..logger import logger

# 🎯 CONSTANTES DE CONFIGURATION
GEO_DISPERSION_GRID_SIZE = 0.1  # Taille de grille en degrés (≈11km)
GEO_DISPERSION_STRATEGY = "grid"


@dataclass
class GeoPoint:
    """Représente un point géographique."""
    lat: float
    lng: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional['GeoPoint']:
        """Crée un GeoPoint depuis un dictionnaire avec support multi-format."""
        try:
            # Support pour différents formats de coordonnées
            if "_geo" in data:
                lat = data["_geo"].get("lat")
                lng = data["_geo"].get("lng")
            elif "lat" in data and "lng" in data:
                lat = data.get("lat")
                lng = data.get("lng")
            elif "lat" in data and "long" in data:
                lat = data.get("lat")
                lng = data.get("long")
            else:
                return None

            if lat is not None and lng is not None:
                return cls(lat=float(lat), lng=float(lng))
        except (ValueError, TypeError, KeyError):
            pass
        return None


class GeoDispersionService:  # pylint: disable=too-few-public-methods
    """Service pour disperser géographiquement les résultats de recherche."""

    def __init__(self, grid_size_degrees: float = GEO_DISPERSION_GRID_SIZE):
        """
        Initialise le service de dispersion.

        Args:
            grid_size_degrees: Taille de la grille en degrés (défaut 0.1° ≈ 11km)
        """
        self.grid_size = grid_size_degrees

    # NOTE : La méthode 'has_geo_filter' a été retirée,
    # car la dispersion doit être appliquée systématiquement
    # sur tous les résultats candidats récupérés.

    def _get_grid_cell(self, point: GeoPoint) -> str:
        """Calcule l'identifiant de la cellule de grille pour un point."""
        lat_cell = int(point.lat / self.grid_size)
        lng_cell = int(point.lng / self.grid_size)
        return f"{lat_cell}_{lng_cell}"

    def disperse_results(
        self,
        hits: List[Dict[str, Any]],
        strategy: str = GEO_DISPERSION_STRATEGY
    ) -> Dict[str, Any]:
        """
        Disperse géographiquement les résultats et applique la pagination.
        ... (Docstring abrégée)
        """
        if not hits:
            return {"hits": [], "cells_used": 0, "geo_hits": 0, "non_geo_hits": 0}

        # Séparer les résultats avec et sans coordonnées
        geo_hits = []
        non_geo_hits = []

        for hit in hits:
            point = GeoPoint.from_dict(hit)
            if point:
                geo_hits.append(hit)
            else:
                non_geo_hits.append(hit)

        if not geo_hits:
            # Pas de données géographiques, retourner pagination normale
            logger.warning("Aucune coordonnée géographique trouvée dans les résultats")
            return {
                "hits": hits,
                "cells_used": 0,
                "geo_hits": 0,
                "non_geo_hits": len(hits)
            }


        # Utilise la dispersion par grille (Round-Robin déterministe)
        dispersed, cells_used = self._disperse_by_grid(geo_hits)
        # Ajouter les résultats sans coordonnées à la fin
        all_dispersed = dispersed + non_geo_hits

        logger.info(
            "Dispersion géographique (stratégie=%s): %d résultats géo sur %d cellules, "
            "%d sans géo",
            strategy, len(geo_hits), cells_used, len(non_geo_hits),
        )

        return {
            "hits": all_dispersed,
            "cells_used": cells_used,
            "geo_hits": len(geo_hits),
            "non_geo_hits": len(non_geo_hits)
        }

    def _disperse_by_grid(
        self, hits: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Dispersion par grille spatiale (Round-Robin) - DÉTERMINISTE.
        ... (Docstring abrégée)
        """
        # Grouper par cellule de grille
        cells: Dict[str, List[Dict[str, Any]]] = {}

        for hit in hits:
            point = GeoPoint.from_dict(hit)
            if point:
                cell_id = self._get_grid_cell(point)
                if cell_id not in cells:
                    cells[cell_id] = []
                cells[cell_id].append(hit)

        if not cells:
            return hits, 0

        # 🔒 TRI DES CELLULES pour garantir un ordre déterministe
        sorted_cell_ids = sorted(cells.keys())
        cell_lists = [cells[cell_id] for cell_id in sorted_cell_ids]

        # 🔒 TRI DES ÉLÉMENTS dans chaque cellule par ID pour stabilité
        for cell in cell_lists:
            cell.sort(key=lambda x: (
                x.get('id', ''),  # Tri primaire par ID
                x.get('name', ''),  # Tri secondaire par nom si pas d'ID
                x.get('lat', 0),  # Tri tertiaire par coordonnées
                x.get('lng', 0)
            ))

        # Round-robin entre les cellules pour une distribution équilibrée
        dispersed = []
        max_items = max(len(cell) for cell in cell_lists)

        for i in range(max_items):
            for cell in cell_lists:
                if i < len(cell):
                    dispersed.append(cell[i])

        logger.debug("Dispersion par grille: %d cellules utilisées (ordre déterministe)", len(cells))
        return dispersed, len(cells)
