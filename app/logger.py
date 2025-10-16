
import logging
from logging.handlers import RotatingFileHandler
import sys

# ==============================================================================
# Configuration
# ==============================================================================

LOG_DIR = "logs"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5

# ==============================================================================
# Formatters
# ==============================================================================

# Formatter standard pour les logs généraux
standard_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Formatter simple pour le débug, centré sur le message
debug_formatter = logging.Formatter(
    '%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ==============================================================================
# Handlers
# ==============================================================================

# Handler pour la sortie console (stdout)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(standard_formatter)

# Handler pour les logs généraux dans un fichier rotatif
info_handler = RotatingFileHandler(
    f'{LOG_DIR}/info.log',
    maxBytes=MAX_BYTES,
    backupCount=BACKUP_COUNT
)
info_handler.setFormatter(standard_formatter)

# Handler pour les logs de débug dans un fichier rotatif
debug_handler = RotatingFileHandler(
    f'{LOG_DIR}/debug.log',
    maxBytes=MAX_BYTES,
    backupCount=BACKUP_COUNT
)
debug_handler.setFormatter(debug_formatter)

# ==============================================================================
# Loggers
# ==============================================================================

# --- Logger Principal ---
# Usage : pour les informations générales de l'application
logger = logging.getLogger("searchpy_logger")
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)
logger.addHandler(info_handler)
logger.propagate = False

# --- Logger de Débug ---
# Usage : pour le débogage spécifique (ex: requêtes, user_id)
debug_logger = logging.getLogger("debug_logger")
debug_logger.setLevel(logging.DEBUG)
debug_logger.addHandler(debug_handler)
debug_logger.propagate = False

# ==============================================================================
# Initialisation
# ==============================================================================

def init_loggers():
    """Crée le répertoire de logs s'il n'existe pas."""
    import os
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

# Appel à l'initialisation pour s'assurer que le répertoire existe
init_loggers()
