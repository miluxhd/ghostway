# Ghostway - TCP-HTTP Protocol Bridge

Ghostway is a bidirectional bridge between TCP and HTTP protocols. 
It enables TCP clients to communicate with TCP servers through an HTTP tunnel.

## Architecture

The project consists of two main services:

1. **Client Service (ghostway-client)**: 
   - Accepts TCP connections and forwards data via HTTP
   - Listens on port 8001 for external TCP client connections
   - Uses port 9001 internally for receiving HTTP responses

2. **Server Service (ghostway-server)**:
   - Receives HTTP requests and forwards data via TCP
   - Listens on port 8002 internally for HTTP communication
   - Forwards data to target TCP server (default port 8003)

## Communication Flow
```
                               +-------------+     8002 (HTTP     +-------------+
+--------+      TCP (8001)     |  Ghostway   |+------------------>|   Ghostway  |     TCP (8003)    +------------------+
|  User  |+------------------->|   Client    |<------------------+|    Server   |+----------------->|  Target Service  |
+--------+                     +-------------+     9001 (HTTP)    +-------------+                   +------------------+

```

Data flow:
1. External TCP Client -> Ghostway Client (8001/TCP)
2. Ghostway Client -> Ghostway Server (8002/HTTP POST, internal)
3. Ghostway Server -> TCP Server (8003/TCP)
4. TCP Server -> Ghostway Server (TCP Response)
5. Ghostway Server -> Ghostway Client (9001/HTTP Response, internal)
6. Ghostway Client -> TCP Client (8001/TCP Response)

## Features

- Bidirectional communication
- Session-based connection management
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
- Docker Compose Plugin

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

### Ghostway Client:
- `TCP_PORT`: TCP server port (default: 8001)
- `TARGET_HTTP_PORT`: Target (Ghostway Server) HTTP port (default: 8002)
- `TARGET_IP`: IP of Ghostway Server
- `GZIP_ENABLED`: Enable or disable gzip compression (default: `true`). Set to `false` to disable.
- `GZIP_THRESHOLD_BYTES`: Minimum payload size in bytes to trigger gzip compression (default: `1024`).

### Ghostway Server:
- `HTTP_PORT`: HTTP server port (default: 8002)
- `TARGET_TCP_PORT`: Target TCP port (default: 8003)
- `TARGET_IP`: Target TCP server address
- `GZIP_ENABLED`: Enable or disable gzip compression (default: `true`). Set to `false` to disable.
- `GZIP_THRESHOLD_BYTES`: Minimum payload size in bytes to trigger gzip compression (default: `1024`).

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
- Non-blocking I/O

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

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
 
