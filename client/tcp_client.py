import socket
import threading
import requests
import base64
from http.server import HTTPServer

from config import logger, TARGET_IP, TARGET_HTTP_PORT, RESPONSE_HTTP_PORT
from response_handler import ResponseHandler, active_tcp_connections, connection_lock

INITIAL_BUFFER_SIZE = 1024
MAX_BUFFER_SIZE = 65536 # Max TCP packet size
BUFFER_GROWTH_FACTOR = 2

class TcpClient:
    def __init__(self):
        self.response_server_thread = None

    def initialize_session(self, session_id):
        """Initialize session with http_to_tcp using PUT request."""
        try:
            # Send PUT request to initialize session
            headers = {
                'Session-ID': session_id,
                'Response-Port': str(RESPONSE_HTTP_PORT)
            }
            
            response = requests.put(
                f'http://{TARGET_IP}:{TARGET_HTTP_PORT}/',
                headers=headers
            )
            logger.info(f'Initialized session with HTTP server, response: {response.status_code}')
        except requests.RequestException as e:
            logger.error(f'Error initializing session with HTTP server: {e}')

    def start_response_server(self):
        """Start HTTP server to receive response data."""
        try:
            server = HTTPServer(('0.0.0.0', RESPONSE_HTTP_PORT), ResponseHandler)
            logger.info(f"Response HTTP server listening on 0.0.0.0:{RESPONSE_HTTP_PORT}")
            server.serve_forever()
        except Exception as e:
            logger.error(f"Error starting response server: {e}")

    def handle_tcp_client(self, client_socket, session_id):
        """Handle a TCP client connection."""
        current_buffer_size = INITIAL_BUFFER_SIZE
        try:
            with client_socket:
                while True:
                    try:
                        data = client_socket.recv(current_buffer_size)
                        if not data:
                            break
                        
                        received_length = len(data)
                        logger.info(f'Received data from session {session_id}, length: {received_length}, buffer_size: {current_buffer_size}')
                        
                        if received_length == current_buffer_size:
                            current_buffer_size = min(current_buffer_size * BUFFER_GROWTH_FACTOR, MAX_BUFFER_SIZE)
                            logger.info(f"Buffer filled, increasing buffer size to {current_buffer_size} for session {session_id}")
                        elif received_length < current_buffer_size // (BUFFER_GROWTH_FACTOR * 2) and current_buffer_size > INITIAL_BUFFER_SIZE:
                            current_buffer_size = max(current_buffer_size // BUFFER_GROWTH_FACTOR, INITIAL_BUFFER_SIZE)
                            logger.info(f"Buffer underutilized, decreasing buffer size to {current_buffer_size} for session {session_id}")

                        # Forward data to HTTP server
                        self.forward_to_http(data, session_id)
                    except socket.error as e:
                        logger.error(f'Socket error in TCP client handler: {e}')
                        break
            
            # After connection is closed, send a close event to HTTP server
            self.send_close_event(session_id)
            
            with connection_lock:
                if session_id in active_tcp_connections:
                    del active_tcp_connections[session_id]
            
        except Exception as e:
            logger.error(f'Error handling TCP client: {e}')
            self.send_close_event(session_id)
            
            # Clean up the connection
            with connection_lock:
                if session_id in active_tcp_connections:
                    del active_tcp_connections[session_id]

    def forward_to_http(self, data, session_id):
        try:
            encoded_data = base64.b64encode(data).decode('utf-8')
            
            headers = {
                'Session-ID': session_id,
                'Content-Type': 'application/octet-stream',
                'Response-Port': str(RESPONSE_HTTP_PORT)
            }
            
            response = requests.post(
                f'http://{TARGET_IP}:{TARGET_HTTP_PORT}/', 
                data=encoded_data, 
                headers=headers
            )
            logger.info(f'Forwarded data to HTTP server, response: {response.status_code}')
        except requests.RequestException as e:
            logger.error(f'Error forwarding data to HTTP server: {e}')
        except Exception as e:
            logger.error(f'Unexpected error forwarding data to HTTP server: {e}')

    def send_close_event(self, session_id):
        """Send a DELETE request to HTTP server to terminate the corresponding TCP connection."""
        try:
            response = requests.delete(
                f'http://{TARGET_IP}:{TARGET_HTTP_PORT}/', 
                headers={'Session-ID': session_id}
            )
            logger.info(f'Sent session termination (DELETE) for session {session_id}, response: {response.status_code}')
        except requests.RequestException as e:
            logger.error(f'Error sending session termination to HTTP server: {e}') 