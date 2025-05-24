import socket
import threading
import requests
import logging
import os
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TCP_PORT = int(os.getenv('TCP_PORT', 8001))
TARGET_HTTP_PORT = int(os.getenv('TARGET_HTTP_PORT', 8002))
RESPONSE_HTTP_PORT = int(os.getenv('RESPONSE_HTTP_PORT', 9001))  # New port for responses
TARGET_IP = os.getenv('TARGET_IP', 'localhost')

active_tcp_connections = {}
connection_lock = threading.Lock()

# HTTP response handler
class ResponseHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            session_id = self.headers.get('Session-ID')
            
            if not session_id:
                self.send_response(400)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Missing Session-ID header")
                return
            
            # Read the POST data (response from TCP server via HTTP)
            encoded_data = self.rfile.read(content_length).decode('utf-8')
            
            try:
                decoded_data = base64.b64decode(encoded_data)
                logger.info(f"Received response for session {session_id}, length: {len(decoded_data)}")
                
                # Find the TCP connection for this session
                with connection_lock:
                    if session_id in active_tcp_connections:
                        client_socket = active_tcp_connections[session_id]
                        try:
                            client_socket.sendall(decoded_data)
                            logger.info(f"Forwarded response to TCP client, session: {session_id}")
                            
                            self.send_response(200)
                            self.send_header('Content-type', 'text/plain')
                            self.end_headers()
                            self.wfile.write(b"Response forwarded to TCP client")
                        except socket.error as e:
                            logger.error(f"Socket error forwarding response to TCP client: {e}")
                            self.send_response(500)
                            self.send_header('Content-type', 'text/plain')
                            self.end_headers()
                            self.wfile.write(b"Error forwarding response to TCP client")
                    else:
                        logger.warning(f"Session {session_id} not found for response")
                        self.send_response(404)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(b"Session not found")
            except Exception as e:
                logger.error(f"Error processing response data: {e}")
                self.send_response(400)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(f"Error processing response data: {e}".encode())
        except Exception as e:
            logger.error(f"Error in response handler: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Internal server error: {e}".encode())
            
    def log_message(self, format, *args):
        logger.info(f"HTTP Response: {args[0]} {args[1]} {args[2]}")

class TcpToHttp:
    def start(self):
        logging.info('Starting TCP to HTTP mode')
        
        self.response_server_thread = threading.Thread(target=self.start_response_server)
        self.response_server_thread.daemon = True
        self.response_server_thread.start()
        
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', TCP_PORT))
        server_socket.listen(5)
        logging.info(f'TCP server listening on 0.0.0.0:{TCP_PORT}')

        while True:
            client_socket, addr = server_socket.accept()
            session_id = str(addr[1])  # Use port as session ID for simplicity
            
            # Store the client socket for bidirectional communication
            with connection_lock:
                active_tcp_connections[session_id] = client_socket
                
            logging.info(f'Accepted connection from {addr}, session ID: {session_id}')
            
            # Initialize session with http_to_tcp using PUT request
            self.initialize_session(session_id)
            
            client_handler = threading.Thread(
                target=self.handle_tcp_client,
                args=(client_socket, session_id)
            )
            client_handler.daemon = True
            client_handler.start()

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
            logging.info(f'Initialized session with HTTP server, response: {response.status_code}')
        except requests.RequestException as e:
            logging.error(f'Error initializing session with HTTP server: {e}')

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
        try:
            with client_socket:
                while True:
                    try:
                        data = client_socket.recv(1024)
                        if not data:
                            break
                        logging.info(f'Received data from session {session_id}, length: {len(data)}')
                        # Forward data to HTTP server
                        self.forward_to_http(data, session_id)
                    except socket.error as e:
                        logging.error(f'Socket error in TCP client handler: {e}')
                        break
            
            # After connection is closed, send a close event to HTTP server
            self.send_close_event(session_id)
            
            with connection_lock:
                if session_id in active_tcp_connections:
                    del active_tcp_connections[session_id]
            
        except Exception as e:
            logging.error(f'Error handling TCP client: {e}')
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
            logging.info(f'Forwarded data to HTTP server, response: {response.status_code}')
        except requests.RequestException as e:
            logging.error(f'Error forwarding data to HTTP server: {e}')
        except Exception as e:
            logging.error(f'Unexpected error forwarding data to HTTP server: {e}')

    def send_close_event(self, session_id):
        """Send a DELETE request to HTTP server to terminate the corresponding TCP connection."""
        try:
            # Use DELETE method with session ID in header for more efficient connection termination
            response = requests.delete(
                f'http://{TARGET_IP}:{TARGET_HTTP_PORT}/', 
                headers={'Session-ID': session_id}
            )
            logging.info(f'Sent session termination (DELETE) for session {session_id}, response: {response.status_code}')
        except requests.RequestException as e:
            logging.error(f'Error sending session termination to HTTP server: {e}')

if __name__ == '__main__':
    tcp_to_http = TcpToHttp()
    tcp_to_http.start() 