import asyncio
import aiohttp
import base64
import gzip

from config import logger, TARGET_IP, TARGET_HTTP_PORT, RESPONSE_HTTP_PORT, GZIP_ENABLED, GZIP_THRESHOLD_BYTES

INITIAL_BUFFER_SIZE = 1024
MAX_BUFFER_SIZE = 65536
BUFFER_GROWTH_FACTOR = 2

# Global structures for managing client writers, now async-safe
active_client_writers = {}
client_writers_lock = asyncio.Lock()

class TcpClient:
    def __init__(self):
        self.http_session = aiohttp.ClientSession()
        self.response_http_port = RESPONSE_HTTP_PORT

    async def initialize_session(self, session_id):
        """Initialize session with http_to_tcp using PUT request."""
        try:
            headers = {
                'Session-ID': session_id,
                'Response-Port': str(self.response_http_port)
            }
            url = f'http://{TARGET_IP}:{TARGET_HTTP_PORT}/'
            async with self.http_session.put(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                logger.info(f'Initialized session with HTTP server for {session_id}, status: {response.status}')
                response.raise_for_status()
        except aiohttp.ClientError as e:
            logger.error(f'Error initializing session with HTTP server for {session_id}: {e}')
        except Exception as e:
            logger.error(f'Unexpected error initializing session for {session_id}: {e}', exc_info=True)

    async def handle_tcp_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: str):
        """Handle a TCP client connection using asyncio streams."""
        current_buffer_size = INITIAL_BUFFER_SIZE
        try:
            async with client_writers_lock:
                active_client_writers[session_id] = writer
            logger.info(f"Added writer for session {session_id}")

            while True:
                try:
                    data = await reader.read(current_buffer_size)
                    if not data:
                        logger.info(f'Connection closed by client for session {session_id}')
                        break
                    
                    received_length = len(data)
                    logger.info(f'Received data from session {session_id}, length: {received_length}, buffer_size: {current_buffer_size}')
                    
                    if received_length == current_buffer_size and current_buffer_size < MAX_BUFFER_SIZE:
                        current_buffer_size = min(current_buffer_size * BUFFER_GROWTH_FACTOR, MAX_BUFFER_SIZE)
                        logger.info(f"Buffer filled, increasing buffer size to {current_buffer_size} for session {session_id}")
                    elif received_length < current_buffer_size // (BUFFER_GROWTH_FACTOR * 2) and current_buffer_size > INITIAL_BUFFER_SIZE:
                        current_buffer_size = max(current_buffer_size // BUFFER_GROWTH_FACTOR, INITIAL_BUFFER_SIZE)
                        logger.info(f"Buffer underutilized, decreasing buffer size to {current_buffer_size} for session {session_id}")

                    await self.forward_to_http(data, session_id)
                except ConnectionResetError:
                    logger.info(f"Client {session_id} reset the connection.")
                    break
                except asyncio.IncompleteReadError as e:
                    logger.warning(f"Incomplete read from client {session_id}: {e.partial}. Assuming connection closed.")
                    break
                except Exception as e:
                    logger.error(f'Error handling TCP client {session_id}: {e}', exc_info=True)
                    break
        finally:
            logger.info(f"Cleaning up for session {session_id}")
            async with client_writers_lock:
                if session_id in active_client_writers:
                    del active_client_writers[session_id]
                    logger.info(f"Removed writer for session {session_id}")
            
            if writer and not writer.is_closing():
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception as e:
                    logger.error(f"Error during writer.wait_closed for session {session_id}: {e}")
            logger.info(f"TCP client connection closed for session {session_id}")
            await self.send_close_event(session_id)

    async def forward_to_http(self, data, session_id):
        try:
            headers = {
                'Session-ID': session_id,
                'Content-Type': 'application/octet-stream',
                'Response-Port': str(self.response_http_port)
            }
            
            payload_data = data
            if GZIP_ENABLED and len(data) > GZIP_THRESHOLD_BYTES:
                payload_data = gzip.compress(data)
                headers['X-Content-Encoding'] = 'gzip'
                logger.info(f"Compressed data for session {session_id}, original: {len(data)}, compressed: {len(payload_data)}")
            
            encoded_data = base64.b64encode(payload_data).decode('utf-8')
            url = f'http://{TARGET_IP}:{TARGET_HTTP_PORT}/'

            async with self.http_session.post(url, data=encoded_data, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                logger.info(f'Forwarded data to HTTP server for {session_id}, status: {response.status}')
                response.raise_for_status()
        except aiohttp.ClientError as e:
            logger.error(f'Error forwarding data to HTTP server for {session_id}: {e}')
        except Exception as e:
            logger.error(f'Unexpected error forwarding data for {session_id}: {e}', exc_info=True)

    async def send_close_event(self, session_id):
        """Send a DELETE request to HTTP server to terminate the corresponding TCP connection."""
        try:
            url = f'http://{TARGET_IP}:{TARGET_HTTP_PORT}/'
            headers = {'Session-ID': session_id}
            async with self.http_session.delete(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                logger.info(f'Sent session termination (DELETE) for session {session_id}, status: {response.status}')
                response.raise_for_status()
        except aiohttp.ClientError as e:
            logger.error(f'Error sending session termination to HTTP server for {session_id}: {e}')
        except Exception as e:
            logger.error(f'Unexpected error sending close event for {session_id}: {e}', exc_info=True)

    async def close_http_session(self):
        """Close the HTTP session."""
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
            logger.info("aiohttp.ClientSession closed for TcpClient.")

    # A synchronous version for atexit, if truly necessary (though atexit + async is tricky)
    def close_http_session_sync(self):
        logger.info("Attempting synchronous close of aiohttp session (not recommended with asyncio event loop running)")
        if self.http_session and not self.http_session.closed:
            # This is problematic because closing an aiohttp session should be async
            # and run within an event loop. This might not work reliably.
            try:
                # Try to run it in a new loop if no loop is running for current thread
                loop = asyncio.get_event_loop_policy().get_event_loop()
                if not loop.is_running():
                    loop.run_until_complete(self.http_session.close())
                else:
                    # If a loop is running, this sync call is bad.
                    # Schedule it if possible, but atexit context is tricky.
                    logger.warning("Cannot synchronously close aiohttp session from atexit while an event loop is running.")
            except Exception as e:
                logger.error(f"Error trying to synchronously close aiohttp session: {e}") 