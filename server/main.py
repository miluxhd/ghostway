from http.server import HTTPServer

from config import logger, HTTP_PORT
from request_handler import HttpRequestHandler
from tcp_server import TcpServer

class HttpToTcp:
    def __init__(self):
        self.tcp_server = TcpServer()

    def start(self):
        logger.info("Starting HTTP to TCP mode")
        server = HTTPServer(('0.0.0.0', HTTP_PORT), HttpRequestHandler)
        server.tcp_server = self.tcp_server  # Attach TCP server instance to HTTP server
        logger.info(f"HTTP server listening on 0.0.0.0:{HTTP_PORT}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down server...")
        finally:
            self.tcp_server.cleanup_connections()
            server.server_close()

if __name__ == '__main__':
    http_to_tcp = HttpToTcp()
    try:
        http_to_tcp.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        http_to_tcp.tcp_server.cleanup_connections() 