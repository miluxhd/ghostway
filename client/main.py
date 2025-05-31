import asyncio
import atexit

from config import logger, TCP_PORT
from response_handler import start_response_http_server
from tcp_client import TcpClient

class TcpToHttp:
    def __init__(self):
        self.tcp_client = TcpClient()
        atexit.register(self.cleanup_sync)
        self.response_server_task = None

    async def handle_new_client(self, reader, writer):
        """Callback for each new TCP client connection."""
        addr = writer.get_extra_info('peername')
        session_id = str(addr[1])  # Use port as session ID for simplicity
        logger.info(f'Accepted connection from {addr}, session ID: {session_id}')
        
        # Initialize session with http_to_tcp using PUT request (will be async)
        await self.tcp_client.initialize_session(session_id)
        
        # Handle the client communication (will be async)
        # This passes the reader, writer, and session_id to the tcp_client instance
        await self.tcp_client.handle_tcp_client(reader, writer, session_id)

    async def start(self):
        logger.info('Starting TCP to HTTP mode (async)')
        
        # Start the HTTP server for receiving responses (will be async)
        # Assuming start_response_http_server is now an async function that returns a task or server object
        self.response_server_task = asyncio.create_task(start_response_http_server('0.0.0.0', self.tcp_client.response_http_port))
        logger.info(f"Response HTTP server starting on 0.0.0.0:{self.tcp_client.response_http_port}")

        server = await asyncio.start_server(
            self.handle_new_client, '0.0.0.0', TCP_PORT
        )

        addr = server.sockets[0].getsockname()
        logger.info(f'TCP server listening on {addr}')

        async with server:
            await server.serve_forever()

    def cleanup_sync(self):
        """Synchronous cleanup for atexit."""
        logger.info("Initiating synchronous cleanup...")
        # For async cleanup, it's better to handle it within the async context or use asyncio.run for cleanup tasks.
        # Closing the session in TcpClient might need to be async if it involves async operations.
        # This is a simplification for atexit.
        if hasattr(self.tcp_client, 'close_http_session_sync') and callable(getattr(self.tcp_client, 'close_http_session_sync')):
            self.tcp_client.close_http_session_sync()
        else:
            logger.warning("TcpClient does not have a synchronous close_http_session_sync method for atexit.")
        # Stopping the response server task might be more complex and require async cancellation
        if self.response_server_task and not self.response_server_task.done():
            self.response_server_task.cancel()
            logger.info("Response server task cancellation requested.")
        logger.info("Synchronous cleanup attempt complete.")

async def main():
    tcp_to_http = TcpToHttp()
    try:
        await tcp_to_http.start()
    except KeyboardInterrupt:
        logger.info("TCP to HTTP service interrupted by user. Shutting down...")
    except asyncio.CancelledError:
        logger.info("Main task cancelled, shutting down.")
    finally:
        # Async cleanup should ideally happen here
        logger.info("Performing final async cleanup...")
        # We might need an async cleanup method in TcpToHttp
        if hasattr(tcp_to_http.tcp_client, 'close_http_session') and asyncio.iscoroutinefunction(tcp_to_http.tcp_client.close_http_session):
             await tcp_to_http.tcp_client.close_http_session() # Assuming close_http_session is async
        if tcp_to_http.response_server_task and not tcp_to_http.response_server_task.done():
            tcp_to_http.response_server_task.cancel()
            try:
                await tcp_to_http.response_server_task
            except asyncio.CancelledError:
                logger.info("Response server task successfully cancelled.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user (KeyboardInterrupt in asyncio.run).")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}", exc_info=True) 