import os
import logging

# Environment variables
TCP_PORT = int(os.getenv('TCP_PORT', 8001))
RESPONSE_HTTP_PORT = int(os.getenv('RESPONSE_HTTP_PORT', 9001)) # Internal port client listens on
# Use service names for Docker Compose compatibility by default
GHOSTWAY_SERVER_URL = os.getenv('GHOSTWAY_SERVER_URL', f'http://ghostway-server:{os.getenv("TARGET_HTTP_PORT", 8002)}') 
GHOSTWAY_CLIENT_CALLBACK_BASE_URL = os.getenv('GHOSTWAY_CLIENT_CALLBACK_BASE_URL', f'http://ghostway-client:{RESPONSE_HTTP_PORT}') # Client's public callback URL

# Gzip Configuration
GZIP_ENABLED = os.getenv('GZIP_ENABLED', 'true').lower() == 'true'
GZIP_THRESHOLD_BYTES = int(os.getenv('GZIP_THRESHOLD_BYTES', 1024))

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) 