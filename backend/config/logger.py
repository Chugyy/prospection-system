# app/logger.py
import logging
from logging.handlers import RotatingFileHandler
from config.config import settings

LOG_FORMAT = "%(asctime)s — %(name)s — %(levelname)s — %(message)s"
LOG_LEVEL = logging.DEBUG if settings.debug else logging.INFO
LOG_FILE = "app/log/app.log"

formatter = logging.Formatter(LOG_FORMAT)

# Handler pour fichier
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
file_handler.setFormatter(formatter)

# Handler pour console/terminal
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

logger = logging.getLogger(settings.app_name)
logger.setLevel(LOG_LEVEL)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
