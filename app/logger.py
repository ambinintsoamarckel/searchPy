'''
Module de configuration pour le logger centralisé de l'application.

Ce module utilise Loguru pour fournir un logger pré-configuré avec des sorties
vers la console (avec couleurs) et des fichiers rotatifs.
'''

import sys
import os
from loguru import logger

# ==============================================================================
# Configuration de Loguru
# ==============================================================================

# Création du dossier de logs s'il n'existe pas
if not os.path.exists('logs'):
    os.makedirs('logs')

# 1. Supprimer le handler par défaut pour éviter les doublons
logger.remove()

# 2. Définir les formats pour les logs
LOG_FORMAT_CONSOLE = ( # 👈 Nouveau format "élégant"
    "<white>{time:YYYY-MM-DD HH:mm:ss.SSS}</white> | "
    "<level>{level: <8}</level> | "
    "<light-black>{name}:{function}:{line}</light-black> - "
    "<level><b>{message}</b></level>"
)
LOG_FORMAT_FILE = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{name}:{function}:{line} - "
    "{message}"
)

# 3. Ajouter un handler pour la sortie console (stderr)
logger.add(
    sys.stderr,
    level="INFO",
    format=LOG_FORMAT_CONSOLE,
    colorize=True,
    backtrace=True,
    diagnose=True
)

# 4. Ajouter des handlers pour les fichiers de log spécifiques
#    - Rotation journalière, conservation de 30 jours, compression.

# Handler pour les logs de niveau DEBUG
logger.add(
    "logs/debug.log",
    level="DEBUG",
    format=LOG_FORMAT_FILE,
    rotation="00:00",
    retention="30 days",
    compression="zip",
    encoding="utf-8",
    filter=lambda record: record["level"].name == "DEBUG"
)

# Handler pour les logs de niveau INFO et WARNING
logger.add(
    "logs/info.log",
    level="INFO",
    format=LOG_FORMAT_FILE,
    rotation="00:00",
    retention="30 days",
    compression="zip",
    encoding="utf-8",
    filter=lambda record: record["level"].name in ("INFO", "WARNING")
)

# Handler pour les logs de niveau ERROR (et supérieur)
logger.add(
    "logs/error.log",
    level="ERROR",
    format=LOG_FORMAT_FILE,
    rotation="00:00",
    retention="30 days",
    compression="zip",
    encoding="utf-8",
    backtrace=True,  # 👈 Ajout pour avoir la trace d'appel complète
    diagnose=True    # 👈 Ajout pour inspecter les variables lors d'une erreur
)

# Le logger est maintenant configuré et prêt à être importé dans d'autres modules.
# Exemple d'utilisation :
# from app.logger import logger
# logger.debug("Ceci est un message de débogage.")
# logger.info("Ceci est un message d'information.")
# logger.warning("Attention, quelque chose d'inattendu s'est produit.")
# logger.error("Ceci est une erreur.")
