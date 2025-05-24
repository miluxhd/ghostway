import os
import logging

# Environment variables
TCP_PORT = int(os.getenv('TCP_PORT', 8001))
TARGET_HTTP_PORT = int(os.getenv('TARGET_HTTP_PORT', 8002))
RESPONSE_HTTP_PORT = int(os.getenv('RESPONSE_HTTP_PORT', 9001))
TARGET_IP = os.getenv('TARGET_IP', 'localhost')

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) 