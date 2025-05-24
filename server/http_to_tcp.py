import socket
import threading
import logging
import os
import base64
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HTTP_PORT = int(os.getenv('HTTP_PORT', 8002))
TARGET_IP = os.getenv('TARGET_IP', 'localhost')
TARGET_TCP_PORT = int(os.getenv('TARGET_TCP_PORT', 8003))

tcp_connections = {}
response_endpoints = {}
connection_lock = threading.Lock()

class HttpRequestHandler(BaseHTTPRequestHandler):
    def do_PUT(self):
        """Handle PUT requests for session initialization."""
        session_id = self.headers.get('Session-ID')
        response_port = self.headers.get('Response-Port')
        
        if not session_id:
            self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Missing Session-ID header")
            return
            
        if not response_port:
            self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Missing Response-Port header")
            return
        
        with connection_lock:
            response_endpoints[session_id] = {
                'ip': self.client_address[0],
                'port': response_port
            }
            logger.info(f"Registered response endpoint for session {session_id}: {self.client_address[0]}:{response_port}")
        
        # Initialize TCP connection
        success = self.ensure_tcp_connection(session_id)
        
        if success:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Session initialized successfully")
        else:
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Failed to initialize session")

    def ensure_tcp_connection(self, session_id):
        """Ensure a TCP connection exists for the given session ID."""
        try:
            # Check if connection already exists
            with connection_lock:
                if session_id in tcp_connections:
                    logger.info(f"TCP connection already exists for session {session_id}")
                    return True
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((TARGET_IP, TARGET_TCP_PORT))
                logger.info(f"Created new TCP connection for session {session_id} to {TARGET_IP}:{TARGET_TCP_PORT}")
                
                if session_id in response_endpoints:
                    response_thread = threading.Thread(
                        target=self.handle_tcp_responses,
                        args=(sock, session_id)
                    )
                    response_thread.daemon = True
                    response_thread.start()
                    logger.info(f"Started TCP response handler for session {session_id}")
                
                tcp_connections[session_id] = sock
                return True
                
        except Exception as e:
            logger.error(f"Error establishing TCP connection: {e}")
            return False

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        session_id = self.headers.get('Session-ID', str(self.client_address[1]))
        response_port = self.headers.get('Response-Port')
        
        if response_port:
            with connection_lock:
                response_endpoints[session_id] = {
                    'ip': self.client_address[0],
                    'port': response_port
                }
                logger.info(f"Updated response endpoint for session {session_id}: {self.client_address[0]}:{response_port}")
        
        encoded_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            decoded_data = base64.b64decode(encoded_data)
            logger.info(f"Received base64 data from HTTP, session: {session_id}, length: {len(decoded_data)}")
            logger.info(f"Decoded data: {decoded_data.decode('utf-8', errors='replace')}")
            
            with connection_lock:
                if session_id not in tcp_connections:
                    logger.error(f"No TCP connection found for session {session_id}. Session must be initialized first.")
                    self.send_response(400)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b"Session not initialized. Send PUT request first.")
                    return
            
            success = self.forward_to_tcp(decoded_data, session_id)
            
            if success:
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Data forwarded to TCP server successfully")
            else:
                self.send_response(500)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Failed to forward data to TCP server")
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Error processing data: {e}".encode())
    
    def do_GET(self):
        # Simple health check
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"HTTP to TCP service is running")
    
    def do_DELETE(self):
        """Handle DELETE requests for session termination."""
        session_id = self.headers.get('Session-ID', None)
        
        if not session_id:
            self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Missing Session-ID header")
            return
            
        logger.info(f"Received session termination request for session: {session_id}")
        
        # Close and remove the TCP connection for this session
        with connection_lock:
            if session_id in tcp_connections:
                logger.info(f"Closing TCP connection for session {session_id}")
                try:
                    tcp_connections[session_id].close()
                except Exception as e:
                    logger.error(f"Error closing connection for session {session_id}: {e}")
                finally:
                    del tcp_connections[session_id]
                    
            if session_id in response_endpoints:
                del response_endpoints[session_id]
                logger.info(f"Removed response endpoint for session {session_id}")
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Session terminated successfully")
    
    def forward_to_tcp(self, data, session_id):
        try:
            with connection_lock:
                if session_id not in tcp_connections:
                    logger.error(f"No TCP connection found for session {session_id}. Session must be initialized first.")
                    return False
                sock = tcp_connections[session_id]
            
            sock.sendall(data)
            logger.info(f"Sent data to TCP server, session: {session_id}, length: {len(data)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error forwarding data to TCP server: {e}")
            with connection_lock:
                if session_id in tcp_connections:
                    try:
                        tcp_connections[session_id].close()
                    except:
                        pass
                    del tcp_connections[session_id]
            return False
    
    def handle_tcp_responses(self, sock, session_id):
        """Listen for responses from the TCP server and forward them back to the TCP client."""
        with connection_lock:
            if session_id not in response_endpoints:
                logger.error(f"No response endpoint for session {session_id}")
                return
            
            endpoint = response_endpoints[session_id]
            response_url = f"http://{endpoint['ip']}:{endpoint['port']}/"
            
        try:
            # Set socket to non-blocking mode for reading
            sock.settimeout(0.5)
            
            while True:
                try:
                    response_data = sock.recv(1024)
                    
                    if not response_data:
                        logger.info(f"TCP server closed connection for session {session_id}")
                        break
                    
                    logger.info(f"Received data from TCP server for session {session_id}, length: {len(response_data)}")
                    
                    encoded_response = base64.b64encode(response_data).decode('utf-8')
                    try:
                        http_response = requests.post(
                            response_url,
                            data=encoded_response,
                            headers={
                                'Session-ID': session_id,
                                'Content-Type': 'application/octet-stream'
                            }
                        )
                        logger.info(f"Forwarded TCP server response to TCP client via HTTP, status: {http_response.status_code}")
                    except Exception as e:
                        logger.error(f"Error forwarding TCP response to client: {e}")
                        break
                
                except socket.timeout:
                    with connection_lock:
                        if session_id not in tcp_connections or tcp_connections[session_id] != sock:
                            logger.info(f"Session {session_id} closed, stopping response handler")
                            break
                except Exception as e:
                    logger.error(f"Error receiving data from TCP server: {e}")
                    break
        
        except Exception as e:
            logger.error(f"Error in TCP response handler: {e}")
        finally:
            # Make sure to clean up the socket if the session is still valid
            with connection_lock:
                if session_id in tcp_connections and tcp_connections[session_id] == sock:
                    try:
                        tcp_connections[session_id].close()
                    except:
                        pass
                    del tcp_connections[session_id]
                    logger.info(f"Closed TCP connection for session {session_id}")

def cleanup_connections():
    """Close all TCP connections when shutting down."""
    with connection_lock:
        for session_id, sock in tcp_connections.items():
            try:
                sock.close()
                logger.info(f"Closed TCP connection for session {session_id}")
            except:
                pass
        tcp_connections.clear()
        response_endpoints.clear()

class HttpToTcp:
    def start(self):
        logger.info("Starting HTTP to TCP mode")
        server = HTTPServer(('0.0.0.0', HTTP_PORT), HttpRequestHandler)
        logger.info(f"HTTP server listening on 0.0.0.0:{HTTP_PORT}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down server...")
        finally:
            cleanup_connections()
            server.server_close()

if __name__ == '__main__':
    http_to_tcp = HttpToTcp()
    try:
        http_to_tcp.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        cleanup_connections() 