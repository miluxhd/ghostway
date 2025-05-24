import socket
import threading
import time
import logging
import random
import string

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TCP_TO_HTTP_IP = 'ghostway-client'
TCP_TO_HTTP_PORT = 8001  # Port of the TCP to HTTP service
TARGET_TCP_PORT = 8003   # Port of the TCP server for testing responses

# To indicate when to stop
stop_flag = threading.Event()

def generate_random_message(length=2000):
    """Generate a random message for testing."""
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for _ in range(length))

def tcp_server(echo_responses=True):
    """Simple TCP echo server that responds to messages."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind(('0.0.0.0', TARGET_TCP_PORT))
        server_socket.listen(5)
        logger.info(f"TCP echo server listening on port {TARGET_TCP_PORT}")
        
        server_socket.settimeout(1)
        
        while not stop_flag.is_set():
            try:
                client_socket, address = server_socket.accept()
                logger.info(f"TCP server: Accepted connection from {address}")
                
                client_handler = threading.Thread(
                    target=handle_tcp_client,
                    args=(client_socket, address, echo_responses)
                )
                client_handler.daemon = True
                client_handler.start()
                
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error accepting connection: {e}")
                if stop_flag.is_set():
                    break
    finally:
        server_socket.close()
        logger.info("TCP echo server shut down")

def handle_tcp_client(client_socket, address, echo_responses):
    """Handle a client connection to the TCP echo server."""
    try:
        client_socket.settimeout(1)  # Set timeout to allow checking stop flag
        
        while not stop_flag.is_set():
            try:
                data = client_socket.recv(4000)
                if not data:
                    logger.info(f"TCP server: Client {address} closed connection")
                    break
                
                message = data.decode('utf-8', errors='replace')
                logger.info(f"TCP server received: {message}")
                
                if echo_responses:
                    response = f"Echo: {message}"
                    client_socket.send(response.encode())
                    logger.info(f"TCP server sent echo response: {response}")
                
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error handling client {address}: {e}")
                break
    finally:
        client_socket.close()
        logger.info(f"TCP server: Connection with {address} closed")

def send_tcp_messages(num_messages=3, message_interval=2):
    """Send messages to the TCP to HTTP service and receive responses."""
    tcp_client = None
    try:
        tcp_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_client.connect((TCP_TO_HTTP_IP, TCP_TO_HTTP_PORT))
        logger.info(f"Connected to TCP to HTTP service at {TCP_TO_HTTP_IP}:{TCP_TO_HTTP_PORT}")
        
        response_thread = threading.Thread(
            target=receive_responses,
            args=(tcp_client,)
        )
        response_thread.daemon = True
        response_thread.start()
        
        for i in range(num_messages):
            if stop_flag.is_set():
                break
                
            message = f"Test message {i+1}: {generate_random_message()}"
            tcp_client.send(message.encode())
            logger.info(f"Sent message: {message}")
            
            time.sleep(message_interval)
        
        time.sleep(5)
        
    except Exception as e:
        logger.error(f"Error sending TCP messages: {e}")
    finally:
        if tcp_client:
            tcp_client.close()
            logger.info("TCP client closed")

def receive_responses(sock):
    """Receive responses from the TCP to HTTP service."""
    try:
        sock.settimeout(1)  # Shorter timeout to be more responsive to stop flag
        
        while not stop_flag.is_set():
            try:
                data = sock.recv(4000)
                if not data:
                    logger.info("Connection closed by server")
                    break
                
                response = data.decode('utf-8', errors='replace')
                logger.info(f"Received response: {response}")
                
            except socket.timeout:
                continue
            except socket.error as e:
                if e.errno == 9:  # Bad file descriptor - socket is closed
                    logger.info("Socket closed, stopping receiver")
                else:
                    logger.error(f"Socket error in receiver: {e}")
                break
            except Exception as e:
                logger.error(f"Error receiving response: {e}")
                break
    except Exception as e:
        if isinstance(e, socket.error) and e.errno == 9:
            logger.info("Socket closed, stopping receiver")
        else:
            logger.error(f"Error in response receiver: {e}")

def run_bidirectional_test():
    """Run the full bidirectional test."""
    logger.info("================ STARTING BIDIRECTIONAL TEST ================")
    
    server_thread = threading.Thread(target=tcp_server)
    server_thread.daemon = True
    server_thread.start()
    
    logger.info("Waiting for TCP echo server to start...")
    time.sleep(2)
    
    try:
        send_tcp_messages(num_messages=3, message_interval=2)
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    finally:
        stop_flag.set()
        logger.info("Waiting for threads to finish...")
        time.sleep(2)  # Reduced wait time since we have shorter timeouts
    
    logger.info("================ BIDIRECTIONAL TEST COMPLETED ================")

if __name__ == "__main__":
    try:
        run_bidirectional_test()
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    finally:
        stop_flag.set()
        time.sleep(1)  # Give threads a moment to clean up 
