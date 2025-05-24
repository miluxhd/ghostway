import socket
import threading

from config import logger, TCP_PORT
from response_handler import active_tcp_connections, connection_lock
from tcp_client import TcpClient

class TcpToHttp:
    def __init__(self):
        self.tcp_client = TcpClient()

    def start(self):
        logger.info('Starting TCP to HTTP mode')
        
        self.tcp_client.response_server_thread = threading.Thread(target=self.tcp_client.start_response_server)
        self.tcp_client.response_server_thread.daemon = True
        self.tcp_client.response_server_thread.start()
        
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', TCP_PORT))
        server_socket.listen(5)
        logger.info(f'TCP server listening on 0.0.0.0:{TCP_PORT}')

        while True:
            client_socket, addr = server_socket.accept()
            session_id = str(addr[1])  # Use port as session ID for simplicity
            
            # Store the client socket for bidirectional communication
            with connection_lock:
                active_tcp_connections[session_id] = client_socket
                
            logger.info(f'Accepted connection from {addr}, session ID: {session_id}')
            
            # Initialize session with http_to_tcp using PUT request
            self.tcp_client.initialize_session(session_id)
            
            client_handler = threading.Thread(
                target=self.tcp_client.handle_tcp_client,
                args=(client_socket, session_id)
            )
            client_handler.daemon = True
            client_handler.start()

if __name__ == '__main__':
    tcp_to_http = TcpToHttp()
    tcp_to_http.start() 