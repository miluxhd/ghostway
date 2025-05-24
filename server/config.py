import os
import logging

# Environment variables
HTTP_PORT = int(os.getenv('HTTP_PORT', 8002))
TARGET_IP = os.getenv('TARGET_IP', 'localhost')
TARGET_TCP_PORT = int(os.getenv('TARGET_TCP_PORT', 8003))

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) 