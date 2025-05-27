import base64
import gzip
import asyncio

from aiohttp import web

from config import logger, RESPONSE_HTTP_PORT
from tcp_client import active_client_writers, client_writers_lock

async def handle_http_response(request: web.Request):
    """Handles incoming HTTP POST requests containing responses for TCP clients."""
    try:
        session_id = request.headers.get('Session-ID')
        content_encoding = request.headers.get('X-Content-Encoding')

        if not session_id:
            logger.error("Missing Session-ID header in response_handler")
            return web.Response(text="Missing Session-ID header", status=400)

        encoded_data = await request.text() # Read body as text (base64 string)
        decoded_data = base64.b64decode(encoded_data)

        if content_encoding == 'gzip':
            try:
                decoded_data = gzip.decompress(decoded_data)
                logger.info(f"Decompressed gzip response for session {session_id}, size: {len(decoded_data)}")
            except gzip.BadGzipFile as e:
                logger.error(f"BadGzipFile for session {session_id}: {e}. Data (first 100): {decoded_data[:100]}")
                return web.Response(text=f"Bad gzip data: {e}", status=400)
            except Exception as e:
                logger.error(f"Error decompressing gzip for session {session_id}: {e}")
                return web.Response(text=f"Gzip decompression error: {e}", status=500)
        
        logger.info(f"Received response for session {session_id}, length: {len(decoded_data)}")

        writer: asyncio.StreamWriter = None
        async with client_writers_lock:
            writer = active_client_writers.get(session_id)

        if writer and not writer.is_closing():
            try:
                writer.write(decoded_data)
                await writer.drain()
                logger.info(f"Forwarded response to TCP client, session: {session_id}")
                return web.Response(text="Response forwarded to TCP client", status=200)
            except ConnectionResetError:
                logger.warning(f"TCP Client {session_id} connection reset while forwarding response.")
                # Clean up writer from active_client_writers if this happens?
                # The main handler in tcp_client.py should also handle this.
                return web.Response(text="TCP client connection reset", status=500)
            except Exception as e:
                logger.error(f"Socket error forwarding response to TCP client {session_id}: {e}")
                return web.Response(text="Error forwarding response to TCP client", status=500)
        elif writer and writer.is_closing():
            logger.warning(f"Session {session_id} writer is closing, cannot forward response.")
            return web.Response(text="Session writer is closing", status=410) # Gone
        else:
            logger.warning(f"Session {session_id} not found or writer not available for response.")
            return web.Response(text="Session not found or writer not available", status=404)

    except Exception as e:
        logger.error(f"Error processing HTTP POST in response_handler: {e}", exc_info=True)
        return web.Response(text=f"Error processing response data: {e}", status=500)

async def start_response_http_server(host: str, port: int):
    """Starts the aiohttp web server for handling responses."""
    app = web.Application()
    app.router.add_post('/', handle_http_response)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    try:
        await site.start()
        logger.info(f"Response HTTP server (aiohttp) listening on {host}:{port}")
        # Keep the server running until cancelled
        while True:
            await asyncio.sleep(3600) # Or some other mechanism to keep alive
    except asyncio.CancelledError:
        logger.info("Response HTTP server shutting down...")
    finally:
        await runner.cleanup()
        logger.info("Response HTTP server runner cleaned up.")

# Removed old BaseHTTPRequestHandler class and related global vars like active_tcp_connections and connection_lock
# as they are now managed in tcp_client.py with async-safe mechanisms. 