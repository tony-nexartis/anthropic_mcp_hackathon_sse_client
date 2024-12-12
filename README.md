# MCP Client

A Python client for interacting with Model Control Protocol (MCP) servers using Server-Sent Events (SSE).

## Architecture

### Server-Sent Events (SSE)
The client establishes a persistent connection with MCP servers using Server-Sent Events (SSE), enabling real-time, server-to-client communication. This architecture allows servers to push updates to the client without requiring constant polling.

Key SSE events:
- `endpoint`: Provides the session-specific messaging endpoint
- `tools`: Delivers available tools and capabilities
- `error`: Communicates server-side errors
- `result`: Returns tool execution results

### Connection Flow
1. Client initiates SSE connection to `/sse` endpoint
2. Server responds with session ID via `endpoint` event
3. Server sends available tools via `tools` event
4. Client maintains persistent connection for real-time updates
5. Tool calls are made via POST requests to the SSE endpoint
6. Results stream back through the SSE connection

## Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Run the client
python client_sse.py
```

## Environment Variables

- `MCP_SERVER_URL`: URL of the MCP server
- `MCP_API_KEY`: API key for authentication
- `ANTHROPIC_API_KEY`: API key for Claude integration

## Features

- Real-time bidirectional communication with MCP servers
- Automatic session management
- Dynamic tool discovery and integration
- Streaming responses for long-running operations
- Robust error handling and connection management

## Server Implementation Guide

### TODO: Adding SSE Support to an MCP Server

To modify an existing MCP server to support SSE, follow these steps:

1. **Add SSE Dependencies**
   ```typescript
   import { EventEmitter } from 'events';
   import { FastifyInstance } from 'fastify';
   ```

2. **Create Session Management**
   ```typescript
   interface Session {
     id: string;
     emitter: EventEmitter;
     tools: Tool[];
   }
   
   const sessions = new Map<string, Session>();
   ```

3. **Implement SSE Endpoint**
   ```typescript
   server.get('/sse', async (request, reply) => {
     const sessionId = generateSessionId();
     const session = createSession(sessionId);
     
     reply.raw.setHeader('Content-Type', 'text/event-stream');
     reply.raw.setHeader('Cache-Control', 'no-cache');
     reply.raw.setHeader('Connection', 'keep-alive');
     
     // Send initial session info
     reply.raw.write(`event: endpoint\ndata: /messages/?session_id=${sessionId}\n\n`);
     
     // Send available tools
     const tools = await getTools();
     reply.raw.write(`event: tools\ndata: ${JSON.stringify(tools)}\n\n`);
     
     // Handle client disconnect
     request.raw.on('close', () => {
       sessions.delete(sessionId);
     });
   });
   ```

4. **Modify Tool Handlers**
   ```typescript
   server.post('/sse', async (request, reply) => {
     const { session_id, tool, args } = request.body;
     const session = sessions.get(session_id);
     
     if (!session) {
       throw new Error('Invalid session');
     }
     
     try {
       const result = await executeToolCall(tool, args);
       reply.raw.write(`event: result\ndata: ${JSON.stringify(result)}\n\n`);
     } catch (error) {
       reply.raw.write(`event: error\ndata: ${JSON.stringify(error)}\n\n`);
     }
   });
   ```

5. **Update Server Configuration**
   ```typescript
   const server = new Server({
     name: "mcp-sse-server",
     version: "1.0.0"
   }, {
     capabilities: {
       resources: {},
       tools: {},
       sse: true  // Enable SSE capability
     }
   });
   ```

6. **Error Handling**
   ```typescript
   server.setErrorHandler(async (error, request, reply) => {
     const sessionId = request.body?.session_id;
     const session = sessions.get(sessionId);
     
     if (session) {
       session.emitter.emit('error', error);
     }
     reply.code(500).send(error);
   });
   ```

7. **Session Cleanup**
   ```typescript
   function cleanupSessions() {
     const now = Date.now();
     for (const [id, session] of sessions.entries()) {
       if (now - session.lastActive > SESSION_TIMEOUT) {
         sessions.delete(id);
       }
     }
   }
   
   setInterval(cleanupSessions, CLEANUP_INTERVAL);
   ```

### Key Considerations

1. **Connection Management**
   - Implement heartbeat mechanism
   - Handle reconnection gracefully
   - Clean up inactive sessions

2. **Security**
   - Validate session IDs
   - Implement rate limiting
   - Add authentication middleware

3. **Performance**
   - Monitor memory usage for active sessions
   - Implement connection pooling
   - Add request queuing for heavy operations

4. **Testing**
   - Add unit tests for SSE endpoints
   - Test connection edge cases
   - Verify tool execution through SSE

## Error Handling

The client implements several error handling mechanisms:
- Connection timeout detection
- Automatic reconnection attempts
- Graceful error reporting
- Session state validation

## Development

The client uses Python's aiohttp library for async HTTP and SSE handling.