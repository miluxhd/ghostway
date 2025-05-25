import base64
from http.server import BaseHTTPRequestHandler
import socket
import threading
import gzip

from config import logger

# Global variables for connection management
active_tcp_connections = {}
connection_lock = threading.Lock()

class ResponseHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            session_id = self.headers.get('Session-ID')
            content_encoding = self.headers.get('X-Content-Encoding')
            
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
                
                if content_encoding == 'gzip':
                    decoded_data = gzip.decompress(decoded_data)
                    logger.info(f"Decompressed gzip response for session {session_id}, decompressed size: {len(decoded_data)}")
                
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