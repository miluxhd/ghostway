import asyncio
from aiohttp import web

from config import logger, HTTP_PORT
from request_handler import setup_routes
from tcp_server import TcpServer

class HttpToTcp:
    def __init__(self):
        self.tcp_server = TcpServer()

    async def start_server(self):
        app = web.Application()
        app['tcp_server'] = self.tcp_server
        
        setup_routes(app)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', HTTP_PORT)
        
        logger.info(f"HTTP server (aiohttp) listening on 0.0.0.0:{HTTP_PORT}")
        await site.start()
        
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("HTTP server task cancelled.")
        finally:
            await runner.cleanup()
            logger.info("HTTP server runner cleaned up.")
            await self.tcp_server.cleanup_connections()

async def main():
    http_to_tcp_service = HttpToTcp()
    try:
        await http_to_tcp_service.start_server()
    except KeyboardInterrupt:
        logger.info("HTTP to TCP service interrupted by user. Shutting down...")
    except asyncio.CancelledError:
        logger.info("Main HTTP to TCP service task cancelled.")
    finally:
        logger.info("Shutting down HttpToTcp service...")
        if hasattr(http_to_tcp_service.tcp_server, 'close_internal_http_session') and \
           asyncio.iscoroutinefunction(http_to_tcp_service.tcp_server.close_internal_http_session):
            await http_to_tcp_service.tcp_server.close_internal_http_session()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user (KeyboardInterrupt in asyncio.run).")
    except Exception as e:
        logger.error(f"Unhandled exception in server main: {e}", exc_info=True) 