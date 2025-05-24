import socket
import threading
import requests
import base64

from config import logger, TARGET_IP, TARGET_TCP_PORT

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