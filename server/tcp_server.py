import asyncio
import aiohttp
import base64
import gzip

from config import logger, TARGET_IP, TARGET_TCP_PORT, GZIP_ENABLED, GZIP_THRESHOLD_BYTES

INITIAL_BUFFER_SIZE = 1024
MAX_BUFFER_SIZE = 65536
BUFFER_GROWTH_FACTOR = 2

class TcpServer:
    def __init__(self):
        self.tcp_connections = {}
        self.response_endpoints = {}
        self.connection_lock = asyncio.Lock()
        self.http_session = aiohttp.ClientSession()

    async def ensure_tcp_connection(self, session_id: str):
        """Ensure a TCP connection to the target server exists for the given session ID."""
        async with self.connection_lock:
            if session_id in self.tcp_connections:
                logger.info(f"TCP connection already exists for session {session_id}")
                return True
            
            if session_id not in self.response_endpoints:
                logger.error(f"No response endpoint configured for session {session_id} before attempting TCP connection.")
                return False

            try:
                logger.info(f"Creating new TCP connection for session {session_id} to {TARGET_IP}:{TARGET_TCP_PORT}")
                reader, writer = await asyncio.open_connection(TARGET_IP, TARGET_TCP_PORT)
                
                response_handler_task = asyncio.create_task(
                    self.handle_tcp_responses(reader, writer, session_id)
                )
                
                self.tcp_connections[session_id] = {
                    'reader': reader,
                    'writer': writer,
                    'task': response_handler_task
                }
                logger.info(f"Successfully created TCP connection and started response handler for session {session_id}")
                return True
            except ConnectionRefusedError:
                logger.error(f"Connection refused when connecting to {TARGET_IP}:{TARGET_TCP_PORT} for session {session_id}")
            except asyncio.TimeoutError:
                logger.error(f"Timeout when connecting to {TARGET_IP}:{TARGET_TCP_PORT} for session {session_id}")
            except Exception as e:
                logger.error(f"Error establishing TCP connection for session {session_id} to {TARGET_IP}:{TARGET_TCP_PORT}: {e}", exc_info=True)
            return False

    async def handle_tcp_responses(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: str):
        """Listen for responses from the target TCP server and forward them via HTTP to ghostway-client."""
        current_buffer_size = INITIAL_BUFFER_SIZE
        response_url = None

        async with self.connection_lock:
            if session_id not in self.response_endpoints:
                logger.error(f"No response endpoint for session {session_id} in handle_tcp_responses. Aborting.")
                return 
            response_url = self.response_endpoints[session_id]
            if not isinstance(response_url, str):
                logger.error(f"Response endpoint for session {session_id} is not a string: {response_url}. Aborting.")
                return
            logger.info(f"Using callback URL for session {session_id}: {response_url}")

        try:
            while True:
                try:
                    response_data = await reader.read(current_buffer_size)
                    if not response_data:
                        logger.info(f"Target TCP server closed connection for session {session_id}")
                        break
                    
                    received_length = len(response_data)
                    logger.info(f"Received data from target TCP for {session_id}, len: {received_length}, buf: {current_buffer_size}")
                    
                    if received_length == current_buffer_size and current_buffer_size < MAX_BUFFER_SIZE:
                        current_buffer_size = min(current_buffer_size * BUFFER_GROWTH_FACTOR, MAX_BUFFER_SIZE)
                    elif received_length < current_buffer_size // (BUFFER_GROWTH_FACTOR * 2) and current_buffer_size > INITIAL_BUFFER_SIZE:
                        current_buffer_size = max(current_buffer_size // BUFFER_GROWTH_FACTOR, INITIAL_BUFFER_SIZE)

                    http_payload = response_data
                    http_headers = {
                        'Session-ID': session_id,
                        'Content-Type': 'application/octet-stream'
                    }
                    if GZIP_ENABLED and len(response_data) > GZIP_THRESHOLD_BYTES:
                        http_payload = gzip.compress(response_data)
                        http_headers['X-Content-Encoding'] = 'gzip'
                        logger.info(f"Compressed response for {session_id}, orig: {len(response_data)}, comp: {len(http_payload)}")

                    encoded_http_payload = base64.b64encode(http_payload).decode('utf-8')
                    
                    async with self.http_session.post(response_url, data=encoded_http_payload, headers=http_headers, timeout=aiohttp.ClientTimeout(total=10)) as http_resp:
                        logger.info(f"Forwarded TCP response via HTTP for {session_id} to {response_url}, status: {http_resp.status}")
                        http_resp.raise_for_status()
                
                except asyncio.IncompleteReadError as e:
                    logger.warning(f"Incomplete read from target TCP for session {session_id}: {e.partial}. Assuming connection closed.")
                    break
                except ConnectionResetError:
                    logger.info(f"Target TCP server reset connection for session {session_id}.")
                    break
                except aiohttp.ClientError as e:
                    logger.error(f"HTTP error forwarding TCP response for {session_id} to {response_url}: {e}")
                    break 
                except Exception as e:
                    logger.error(f"Error processing TCP response for session {session_id}: {e}", exc_info=True)
                    break
        except Exception as e:
            logger.error(f"Outer error in TCP response handler for session {session_id}: {e}", exc_info=True)
        finally:
            logger.info(f"TCP response handler for session {session_id} is stopping.")
            
            original_exception_to_reraise = None

            if writer and not writer.is_closing():
                writer.close()
                try:
                    await writer.wait_closed()
                except asyncio.CancelledError as e_cancel:
                    logger.warning(f"writer.wait_closed() cancelled for session {session_id} in HTR finally.")
                    original_exception_to_reraise = e_cancel # Mark for re-raising
                except Exception as e_other:
                    logger.error(f"Error during target TCP writer.wait_closed for session {session_id}: {e_other}", exc_info=True)
                    # Do not set original_exception_to_reraise for general errors here by default,
                    # but allow critical CSC errors to be prioritized later if this was the only issue.
                    if original_exception_to_reraise is None: # Don't overwrite a CancelledError
                        original_exception_to_reraise = e_other


            try:
                # This call is vital for cleanup. originating_task_cancelled=True because HTR is cleaning itself up.
                await self.close_session_components(session_id, originating_task_cancelled=True)
            except Exception as e_csc:
                logger.critical(f"CRITICAL: Error in self.close_session_components called from HTR finally for session {session_id}: {e_csc}", exc_info=True)
                # If CSC fails, this session's resources are likely leaked.
                # Prioritize raising the original CancelledError if it exists, otherwise this CSC error.
                if not isinstance(original_exception_to_reraise, asyncio.CancelledError):
                    original_exception_to_reraise = e_csc

            if original_exception_to_reraise is not None:
                raise original_exception_to_reraise

    async def close_session_components(self, session_id: str, originating_task_cancelled: bool = False):
        """Close and clean up all components related to a session."""
        async with self.connection_lock:
            logger.info(f"Closing components for session {session_id}")
            
            connection_details = self.tcp_connections.pop(session_id, None)
            if connection_details:
                writer = connection_details.get('writer')
                task = connection_details.get('task')

                if writer and not writer.is_closing():
                    writer.close()
                    try:
                        await writer.wait_closed()
                        logger.info(f"Target TCP writer for session {session_id} closed.")
                    except Exception as e:
                        logger.error(f"Error closing target TCP writer for session {session_id}: {e}")
                
                if task and not task.done() and not originating_task_cancelled:
                    task.cancel()
                    logger.info(f"Response handler task for session {session_id} cancellation requested.")
                    try:
                        # Wait for the task to finish with a timeout
                        await asyncio.wait_for(task, timeout=5.0) # 5 seconds timeout
                    except asyncio.CancelledError:
                        logger.info(f"Response handler task for session {session_id} successfully cancelled.")
                    except asyncio.TimeoutError:
                        logger.error(f"Response handler task for session {session_id} did not terminate within timeout after cancellation. It might be orphaned.")
                    except Exception as e:
                        logger.error(f"Error awaiting cancelled response handler task for session {session_id}: {e}", exc_info=True)
            
            if session_id in self.response_endpoints:
                del self.response_endpoints[session_id]
                logger.info(f"Removed response endpoint for session {session_id}")
            logger.info(f"Finished closing components for session {session_id}")

    async def cleanup_connections(self):
        """Close all active TCP connections and tasks when shutting down."""
        logger.info("Cleaning up all TCP server connections...")
        async with self.connection_lock:
            session_ids = list(self.tcp_connections.keys())
        
        for session_id in session_ids:
            await self.close_session_components(session_id)
        
        logger.info("All TCP server connections cleanup process initiated.")
        await asyncio.sleep(0.1)

    async def close_internal_http_session(self):
        """Close the internal aiohttp ClientSession."""
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
            logger.info("Internal aiohttp.ClientSession closed for TcpServer.") 