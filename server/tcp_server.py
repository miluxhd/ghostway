import socket
import threading
import requests
import base64
import gzip

from config import logger, TARGET_IP, TARGET_TCP_PORT, GZIP_ENABLED, GZIP_THRESHOLD_BYTES

INITIAL_BUFFER_SIZE = 1024
MAX_BUFFER_SIZE = 65536 # Max TCP packet size
BUFFER_GROWTH_FACTOR = 2

class TcpServer:
    def __init__(self):
        self.tcp_connections = {}
        self.response_endpoints = {}
        self.connection_lock = threading.Lock()

    def ensure_tcp_connection(self, session_id):
        """Ensure a TCP connection exists for the given session ID."""
        try:
            # Check if connection already exists
            with self.connection_lock:
                if session_id in self.tcp_connections:
                    logger.info(f"TCP connection already exists for session {session_id}")
                    return True
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((TARGET_IP, TARGET_TCP_PORT))
                logger.info(f"Created new TCP connection for session {session_id} to {TARGET_IP}:{TARGET_TCP_PORT}")
                
                if session_id in self.response_endpoints:
                    response_thread = threading.Thread(
                        target=self.handle_tcp_responses,
                        args=(sock, session_id)
                    )
                    response_thread.daemon = True
                    response_thread.start()
                    logger.info(f"Started TCP response handler for session {session_id}")
                
                self.tcp_connections[session_id] = sock
                return True
                
        except Exception as e:
            logger.error(f"Error establishing TCP connection: {e}")
            return False

    def handle_tcp_responses(self, sock, session_id):
        """Listen for responses from the TCP server and forward them back to the TCP client."""
        with self.connection_lock:
            if session_id not in self.response_endpoints:
                logger.error(f"No response endpoint for session {session_id}")
                return
            
            endpoint = self.response_endpoints[session_id]
            response_url = f"http://{endpoint['ip']}:{endpoint['port']}/"
            
        current_buffer_size = INITIAL_BUFFER_SIZE
        try:
            # Set socket to non-blocking mode for reading
            sock.settimeout(0.5)
            
            while True:
                try:
                    response_data = sock.recv(current_buffer_size)
                    
                    if not response_data:
                        logger.info(f"TCP server closed connection for session {session_id}")
                        break
                    
                    received_length = len(response_data)
                    logger.info(f"Received data from TCP server for session {session_id}, length: {received_length}, buffer_size: {current_buffer_size}")
                    
                    if received_length == current_buffer_size:
                        current_buffer_size = min(current_buffer_size * BUFFER_GROWTH_FACTOR, MAX_BUFFER_SIZE)
                        logger.info(f"Buffer filled, increasing buffer size to {current_buffer_size} for session {session_id}")
                    elif received_length < current_buffer_size // (BUFFER_GROWTH_FACTOR * 2) and current_buffer_size > INITIAL_BUFFER_SIZE:
                        # Optional: Decrease buffer size if significantly underutilized
                        current_buffer_size = max(current_buffer_size // BUFFER_GROWTH_FACTOR, INITIAL_BUFFER_SIZE)
                        logger.info(f"Buffer underutilized, decreasing buffer size to {current_buffer_size} for session {session_id}")

                    payload_data = response_data
                    headers = {
                        'Session-ID': session_id,
                        'Content-Type': 'application/octet-stream'
                    }
                    if GZIP_ENABLED and len(response_data) > GZIP_THRESHOLD_BYTES:
                        payload_data = gzip.compress(response_data)
                        headers['X-Content-Encoding'] = 'gzip'
                        logger.info(f"Compressed response for session {session_id}, original size: {len(response_data)}, compressed size: {len(payload_data)}")

                    encoded_response = base64.b64encode(payload_data).decode('utf-8')
                    try:
                        http_response = requests.post(
                            response_url,
                            data=encoded_response,
                            headers=headers
                        )
                        logger.info(f"Forwarded TCP server response to TCP client via HTTP, status: {http_response.status_code}")
                    except Exception as e:
                        logger.error(f"Error forwarding TCP response to client: {e}")
                        break
                
                except socket.timeout:
                    with self.connection_lock:
                        if session_id not in self.tcp_connections or self.tcp_connections[session_id] != sock:
                            logger.info(f"Session {session_id} closed, stopping response handler")
                            break
                except Exception as e:
                    logger.error(f"Error receiving data from TCP server: {e}")
                    break
        
        except Exception as e:
            logger.error(f"Error in TCP response handler: {e}")
        finally:
            # Make sure to clean up the socket if the session is still valid
            with self.connection_lock:
                if session_id in self.tcp_connections and self.tcp_connections[session_id] == sock:
                    try:
                        self.tcp_connections[session_id].close()
                    except:
                        pass
                    del self.tcp_connections[session_id]
                    logger.info(f"Closed TCP connection for session {session_id}")

    def cleanup_connections(self):
        """Close all TCP connections when shutting down."""
        with self.connection_lock:
            for session_id, sock in self.tcp_connections.items():
                try:
                    sock.close()
                    logger.info(f"Closed TCP connection for session {session_id}")
                except:
                    pass
            self.tcp_connections.clear()
            self.response_endpoints.clear() 