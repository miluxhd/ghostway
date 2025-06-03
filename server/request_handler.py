import base64
import gzip
import asyncio
from aiohttp import web

from config import logger
# TcpServer will be imported and used by type hint, but instance comes from request.app
# from tcp_server import TcpServer 

async def handle_put_request(request: web.Request):
    """Handle PUT requests for session initialization."""
    tcp_server = request.app['tcp_server'] # Get TcpServer instance
    session_id = request.headers.get('Session-ID')
    client_callback_url = request.headers.get('X-Client-Callback-Url')
    
    if not session_id:
        return web.Response(text="Missing Session-ID header", status=400)
    if not client_callback_url:
        return web.Response(text="Missing X-Client-Callback-Url header", status=400)
    
    # Assuming tcp_server.connection_lock is now asyncio.Lock
    async with tcp_server.connection_lock:
        # Store the full callback URL directly
        tcp_server.response_endpoints[session_id] = client_callback_url
        logger.info(f"Registered response endpoint for session {session_id}: {client_callback_url}")
    
    # ensure_tcp_connection will be an async method
    success = await tcp_server.ensure_tcp_connection(session_id)
    
    if success:
        return web.Response(text="Session initialized successfully", status=200)
    else:
        return web.Response(text="Failed to initialize session", status=500)

async def handle_post_request(request: web.Request):
    """Handle POST requests to forward data to the target TCP server."""
    tcp_server = request.app['tcp_server']
    session_id = request.headers.get('Session-ID')
    # Removed Response-Port logic, callback URL is fixed at session init
    content_encoding = request.headers.get('X-Content-Encoding')

    if not session_id:
        logger.warning(f"POST request missing Session-ID from {request.remote}")
        return web.Response(text="Missing Session-ID header", status=400)

    # Removed logic for updating response_endpoints dynamically via POST
    
    try:
        raw_body = await request.read() # Read raw bytes
        encoded_data = raw_body.decode('utf-8') # Assuming base64 is utf-8 encoded
        decoded_data = base64.b64decode(encoded_data)
        
        if content_encoding == 'gzip':
            try:
                decompressed_data = gzip.decompress(decoded_data)
                logger.info(f"Decompressed gzip data for session {session_id}, original: {len(decoded_data)}, decompressed: {len(decompressed_data)}")
                decoded_data = decompressed_data
            except gzip.BadGzipFile as e:
                logger.error(f"BadGzipFile for session {session_id} in POST: {e}. Data: {decoded_data[:100]}")
                return web.Response(text=f"Bad gzip data: {e}", status=400)
            except Exception as e:
                logger.error(f"Error decompressing gzip for session {session_id} in POST: {e}")
                return web.Response(text=f"Gzip decompression error: {e}", status=500)
        
        logger.info(f"Received data from HTTP for session {session_id}, length: {len(decoded_data)}")
        
        async with tcp_server.connection_lock:
            if session_id not in tcp_server.tcp_connections:
                logger.error(f"No TCP connection for session {session_id}. Initialize with PUT.")
                return web.Response(text="Session not initialized. Send PUT request first.", status=400)
            
            target_socket_writer = tcp_server.tcp_connections[session_id]['writer'] # Assuming writer is stored
        
        if target_socket_writer and not target_socket_writer.is_closing():
            target_socket_writer.write(decoded_data)
            await target_socket_writer.drain()
            logger.info(f"Sent data to target TCP server for session: {session_id}, length: {len(decoded_data)}")
            return web.Response(text="Data forwarded to TCP server successfully", status=200)
        else:
            logger.error(f"Target TCP socket writer not available or closing for session {session_id}")
            return web.Response(text="Failed to forward data: target TCP connection issue.", status=500)
            
    except Exception as e:
        logger.error(f"Error processing POST data for session {session_id}: {e}", exc_info=True)
        return web.Response(text=f"Error processing data: {e}", status=500)

async def handle_delete_request(request: web.Request):
    """Handle DELETE requests for session termination."""
    tcp_server = request.app['tcp_server']
    session_id = request.headers.get('Session-ID')
    
    if not session_id:
        return web.Response(text="Missing Session-ID header", status=400)
            
    logger.info(f"Received session termination request for session: {session_id}")
    
    await tcp_server.close_session_components(session_id) # New async method in TcpServer
    
    return web.Response(text="Session terminated successfully", status=200)

async def handle_get_request(request: web.Request):
    """Handle GET requests for health check."""
    return web.Response(text="HTTP to TCP service is running (async)", status=200)

def setup_routes(app: web.Application):
    app.router.add_put('/', handle_put_request)
    app.router.add_post('/', handle_post_request)
    app.router.add_delete('/', handle_delete_request)
    app.router.add_get('/', handle_get_request) # Health check 