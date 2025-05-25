import base64
from http.server import BaseHTTPRequestHandler
import gzip

from config import logger
from tcp_server import TcpServer

class HttpRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        self.tcp_server = server.tcp_server
        super().__init__(request, client_address, server)

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
        
        with self.tcp_server.connection_lock:
            self.tcp_server.response_endpoints[session_id] = {
                'ip': self.client_address[0],
                'port': response_port
            }
            logger.info(f"Registered response endpoint for session {session_id}: {self.client_address[0]}:{response_port}")
        
        # Initialize TCP connection
        success = self.tcp_server.ensure_tcp_connection(session_id)
        
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

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        session_id = self.headers.get('Session-ID', str(self.client_address[1]))
        response_port = self.headers.get('Response-Port')
        content_encoding = self.headers.get('X-Content-Encoding')
        
        if response_port:
            with self.tcp_server.connection_lock:
                self.tcp_server.response_endpoints[session_id] = {
                    'ip': self.client_address[0],
                    'port': response_port
                }
                logger.info(f"Updated response endpoint for session {session_id}: {self.client_address[0]}:{response_port}")
        
        encoded_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            decoded_data = base64.b64decode(encoded_data)
            
            if content_encoding == 'gzip':
                decoded_data = gzip.decompress(decoded_data)
                logger.info(f"Decompressed gzip data for session {session_id}, decompressed size: {len(decoded_data)}")
            
            logger.info(f"Received data from HTTP, session: {session_id}, length: {len(decoded_data)}")
            
            with self.tcp_server.connection_lock:
                if session_id not in self.tcp_server.tcp_connections:
                    logger.error(f"No TCP connection found for session {session_id}. Session must be initialized first.")
                    self.send_response(400)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b"Session not initialized. Send PUT request first.")
                    return
                
                try:
                    self.tcp_server.tcp_connections[session_id].sendall(decoded_data)
                    logger.info(f"Sent data to TCP server, session: {session_id}, length: {len(decoded_data)}")
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b"Data forwarded to TCP server successfully")
                except Exception as e:
                    logger.error(f"Error forwarding data to TCP server: {e}")
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
            if isinstance(e, UnicodeDecodeError):
                logger.error(f"UnicodeDecodeError: {e}. Original data (first 100 bytes if available): {encoded_data[:100]}")
    
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
        with self.tcp_server.connection_lock:
            if session_id in self.tcp_server.tcp_connections:
                logger.info(f"Closing TCP connection for session {session_id}")
                try:
                    self.tcp_server.tcp_connections[session_id].close()
                except Exception as e:
                    logger.error(f"Error closing connection for session {session_id}: {e}")
                finally:
                    del self.tcp_server.tcp_connections[session_id]
                    
            if session_id in self.tcp_server.response_endpoints:
                del self.tcp_server.response_endpoints[session_id]
                logger.info(f"Removed response endpoint for session {session_id}")
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Session terminated successfully") 