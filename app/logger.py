"""
Module de configuration pour le logger centralisé de l'application.

Ce module utilise Loguru pour fournir un logger pré-configuré avec des sorties
vers la console (avec couleurs) et des fichiers rotatifs.
"""

import sys
from loguru import logger

# ==============================================================================
# Configuration de Loguru
# ==============================================================================

# 1. Supprimer le handler par défaut pour éviter les doublons
logger.remove()

# 2. Définir un format commun pour les logs
#    Inclut le temps, le niveau, le module, la fonction et le message.
log_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

# 3. Ajouter un handler pour la sortie console (stderr)
#    - Les logs seront colorisés.
#    - Affiche les logs à partir du niveau INFO.
logger.add(
    sys.stderr,
    level="INFO",
    format=log_format,
    colorize=True,
    backtrace=True,
    diagnose=True  # Pour un meilleur débogage des exceptions
)

# 4. Ajouter un handler pour écrire les logs dans un fichier rotatif
#    - Crée un nouveau fichier chaque jour à minuit.
#    - Conserve les logs pendant 30 jours.
#    - Compresse les anciens fichiers de log.
#    - Affiche tous les logs à partir du niveau DEBUG.
logger.add(
    "logs/app.log",
    level="DEBUG",
    format=log_format,
    rotation="00:00",  # Rotation journalière
    retention="30 days",
    compression="zip",
    encoding="utf-8"
)

# Le logger est maintenant configuré et prêt à être importé dans d'autres modules.
# Exemple d'utilisation :
# from app.logger import logger
# logger.info("Ceci est un message d'information.")
# logger.debug("Ceci est un message de débogage.")
# logger.warning("Attention, quelque chose d'inattendu s'est produit.")