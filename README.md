# Ghostway - TCP-over-HTTP Tunnel

Ghostway is a bidirectional TCP-to-HTTP tunneling application. It is designed to enable applications that rely on persistent TCP connections (such as SSH, RDP, database connections, etc.) to operate across networks that restrict direct TCP access and only permit HTTP/HTTPS traffic. By encapsulating TCP data within HTTP requests and responses, Ghostway effectively bypasses such network restrictions.

This project is particularly useful in environments where firewalls or proxies block standard TCP ports or protocols but allow web traffic.

## Core Problem Solved

Many corporate or public networks restrict outbound connections to only allow HTTP (port 80) and HTTPS (port 443). This can prevent the use of essential services that require direct TCP connections on other ports, like:
- SSH (Secure Shell) for remote server access.
- RDP (Remote Desktop Protocol) for remote desktop access.
- Direct database connections.
- Other custom TCP-based application protocols.

Ghostway provides a tunnel to transfer TCP traffic through these HTTP-only gateways.

## Architecture

The project consists of two main services, typically run as Docker containers:

1.  **Ghostway Client (`ghostway-client`)**:
    *   Acts as the entry point for the application you want to tunnel.
    *   Listens for incoming TCP connections from your local application (e.g., an SSH client pointing to the Ghostway Client's address and port).
    *   Takes the TCP data, encapsulates it into HTTP POST requests, and sends it to the Ghostway Server via a configured URL (see `GHOSTWAY_SERVER_URL`).
    *   During session initialization, it provides its own public callback URL (see `GHOSTWAY_CLIENT_CALLBACK_BASE_URL`) to the Ghostway Server.
    *   Receives HTTP responses from the Ghostway Server (containing data from the target TCP service) at its callback URL, decapsulates the TCP data, and forwards it back to your local application.
    *   Built with Python using `asyncio` and `aiohttp` for efficient, non-blocking I/O.

2.  **Ghostway Server (`ghostway-server`)**:
    *   Acts as the exit point of the tunnel, deployed on a machine that can access the target TCP service.
    *   Listens for HTTP requests from the Ghostway Client at its public URL.
    *   Receives HTTP POST requests, extracts the encapsulated TCP data, and forwards it to the *actual* target TCP service (e.g., an SSH server).
    *   Receives TCP data back from the target service, encapsulates it into HTTP responses, and sends it back to the Ghostway Client using the callback URL provided by the client during session initialization.
    *   The version discussed and modified in this session uses a synchronous Python implementation with `http.server`, `socketserver`, and `requests`, managed with `threading`. *(Note: Previous versions and development efforts explored an `aiohttp`-based server as well).*

## Communication Flow

The core HTTP communication between Ghostway Client and Ghostway Server is now URL-based, facilitating deployment behind reverse proxies and services like Cloudflare.

```
                               +-------------+     80   (HTTP     +-------------+
+--------+      TCP (8001)     |  Ghostway   |+------------------>|   Ghostway  |     TCP (8003)    +------------------+
|  User  |+------------------->|   Client    |<------------------+|    Server   |+----------------->|  Target Service  |
+--------+                     +-------------+     80   (HTTP)    +-------------+                   +------------------+

```

Data flow:
1. External TCP Client -> Ghostway Client (at `TCP_PORT`)
2. Ghostway Client -> Ghostway Server (HTTP POST to `GHOSTWAY_SERVER_URL`)
3. Ghostway Server -> Target TCP Service (at `TARGET_IP`:`TARGET_TCP_PORT`)
4. Target TCP Service -> Ghostway Server (TCP Response)
5. Ghostway Server -> Ghostway Client (HTTP POST to `GHOSTWAY_CLIENT_CALLBACK_BASE_URL`)
6. Ghostway Client -> External TCP Client (TCP Response via original connection)

## Features

- Bidirectional TCP traffic tunneling over HTTP.
- URL-based configuration for inter-service HTTP communication, ideal for reverse proxies.
- Session-based connection management to handle multiple concurrent tunnels.
- Automatic connection cleanup
- Connection pooling and keep-alive support
- TCP socket optimizations
- HTTP request optimizations
- Adaptive TCP buffer sizing
- Configurable Gzip Compression for HTTP Payloads

## Configurable Gzip Compression

Ghostway supports optional gzip compression for data payloads transmitted between the `ghostway-client` and `ghostway-server` via HTTP. This can help reduce bandwidth usage for larger data packets.

Compression is applied if:
1. Gzip is enabled via the `GZIP_ENABLED` environment variable.
2. The size of the data packet exceeds the `GZIP_THRESHOLD_BYTES` environment variable.

A custom HTTP header `X-Content-Encoding: gzip` is added to requests/responses when the payload is compressed.

## Prerequisites

- Docker
- Docker Compose (Plugin for Docker CLI)

## Setup and Running

1. Clone the repository:
```bash
git clone git@github.com:miluxhd/ghostway.git
cd ghostway
```

2. Configure your target TCP server address in docker-compose.yml (optional):
```yaml
ghostway-server:
  environment:
    - TARGET_IP=your_tcp_server_host
```

3. Start the services:
```bash
docker compose up --build
```

## Environment Variables

Key environment variables for configuring the tunnel:

### Ghostway Client (`ghostway-client`):
- `TCP_PORT`: The local TCP port the Ghostway Client listens on for your application (default: 8001).
- `RESPONSE_HTTP_PORT`: The internal HTTP port the Ghostway Client's response server listens on (default: 80). Traffic from `GHOSTWAY_CLIENT_CALLBACK_BASE_URL` should be directed here by your reverse proxy.
- `GHOSTWAY_SERVER_URL`: The public URL of the Ghostway Server. The client sends its initial session requests and data packets here. (Example: `https://server.yourdomain.com`, Default for Docker tests: `http://ghostway-server:80`).
- `GHOSTWAY_CLIENT_CALLBACK_BASE_URL`: The public URL that the Ghostway Server will use to POST responses back to this Ghostway Client. This URL should point (e.g., via Cloudflare) to the `ghostway-client` service, specifically to its `RESPONSE_HTTP_PORT`. (Example: `https://client-callback.yourdomain.com`, Default for Docker tests: `http://ghostway-client:80`).
- `GZIP_ENABLED`: Enable or disable gzip compression (default: `true`). Set to `false` to disable.
- `GZIP_THRESHOLD_BYTES`: Minimum payload size in bytes to trigger gzip compression (default: `1024`).

### Ghostway Server (`ghostway-server`):
- `HTTP_PORT`: The internal HTTP port the Ghostway Server listens on (default: 80). Traffic from the Ghostway Client's `GHOSTWAY_SERVER_URL` should be directed here by your reverse proxy.
- `TARGET_TCP_PORT`: The port of the final target TCP service (e.g., SSH server's port 22) (default: 8003 for testing).
- `TARGET_IP`: The IP address or hostname of the final target TCP service.
- `GZIP_ENABLED`: Enable or disable gzip compression (default: `true`). Set to `false` to disable.
- `GZIP_THRESHOLD_BYTES`: Minimum payload size in bytes to trigger gzip compression (default: `1024`).

## Deployment with Reverse Proxies (Cloudflare, etc ..)

The URL-based configuration (`GHOSTWAY_SERVER_URL`, `GHOSTWAY_CLIENT_CALLBACK_BASE_URL`) is designed to work seamlessly with reverse proxies like Cloudflare, Nginx, or others.

**Default Ports for Docker Testing:**

For the default Docker Compose test environment (`docker compose up ghostway-tests`):
- `ghostway-client`'s `RESPONSE_HTTP_PORT` defaults to `80`.
- `ghostway-client`'s `GHOSTWAY_SERVER_URL` defaults to `http://ghostway-server:80`.
- `ghostway-client`'s `GHOSTWAY_CLIENT_CALLBACK_BASE_URL` defaults to `http://ghostway-client:80`.
- `ghostway-server`'s `HTTP_PORT` defaults to `80`.


## Testing

The project includes a test suite that verifies bidirectional communication:

1. Start the services in detached mode:
```bash
docker compose up -d ghostway-client ghostway-server
```

2. Run the tests:
```bash
docker compose up ghostway-tests
```

## Performance Optimizations

The project includes several optimizations for high performance:

- TCP socket optimizations (TCP_NODELAY, buffer sizes)
- HTTP connection pooling
- Keep-alive connections
- Efficient error handling
- Optimized buffer sizes
- Non-blocking I/O (primarily in the `ghostway-client` due to `aiohttp`).
- Threading for concurrent connection handling in the `ghostway-server`.

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## TODO

### Code Quality Improvements
- [ ] Add comprehensive error handling
- [ ] Improve logging and monitoring
- [ ] Add code documentation and comments
- [ ] Implement unit tests for core functionality

### Performance Enhancements
- [x] Implement data compression for HTTP transport
    - [x] Add gzip compression support
    - [x] Add configurable compression threshold and enable/disable flag
    - [ ] Add configurable compression levels (currently uses gzip default)
- [ ] Optimize connection speed
    - [ ] Implement connection pooling improvements
    - [x] Fine-tune buffer sizes (implemented adaptive buffers)
    - [ ] Add connection timeout configurations
    - [ ] Optimize TCP socket parameters

### Features
- [ ] Add support for encryption
- [ ] Implement authentication mechanism between client and server
- [ ] Add metrics collection and monitoring
- [ ] Create a configuration file for easier setup
- [ ] Add support for multiple target servers
- [ ] Implement rate limiting

### Documentation
- [ ] Add API documentation
- [ ] Create detailed deployment guide
- [ ] Add performance tuning guide
- [ ] Include troubleshooting section

## License

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
 
