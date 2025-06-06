import os
import logging

# Environment variables
HTTP_PORT = int(os.getenv('HTTP_PORT', 80))
TARGET_IP = os.getenv('TARGET_IP', 'localhost')
TARGET_TCP_PORT = int(os.getenv('TARGET_TCP_PORT', 8003))

# Gzip Configuration
GZIP_ENABLED = os.getenv('GZIP_ENABLED', 'true').lower() == 'true'
GZIP_THRESHOLD_BYTES = int(os.getenv('GZIP_THRESHOLD_BYTES', 1024))

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) 