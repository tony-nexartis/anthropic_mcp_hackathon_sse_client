import os
import json
import asyncio
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from anthropic import Anthropic
import aiohttp
from aiohttp import ClientSession

load_dotenv()

class MCPClientSSE:
    def __init__(self, server_url: str):
        """Initialize the MCP client with SSE support
        
        Args:
            server_url: URL of the MCP server (e.g., 'http://localhost:3000')
        """
        self.server_url = server_url.rstrip('/')
        self.session = None
        self.anthropic = Anthropic()
        self.tools = []
        self.session_id = None
        
        # Get API keys from env
        self.anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        self.mcp_key = os.getenv('MCP_API_KEY')
        
        if not self.anthropic_key:
            raise Exception("ANTHROPIC_API_KEY not found in environment")
        if not self.mcp_key:
            raise Exception("MCP_API_KEY not found in environment")

    async def handle_sse_events(self):
        """Handle SSE events in the background"""
        print(f"\nStarting SSE connection to {self.server_url}/sse")
        async with self.session.get(f"{self.server_url}/sse") as response:
            print(f"SSE Response status: {response.status}")
            print(f"SSE Response headers: {json.dumps(dict(response.headers), indent=2)}")
            
            if response.status != 200:
                response_text = await response.text()
                raise Exception(f"Failed to connect: {response.status} - {response_text}")
            
            print("\nReading SSE events...")
            current_event = None
            async for line in response.content:
                line = line.decode('utf-8').strip()
                if not line:
                    continue
                    
                print(f"SSE Line: {line}")
                    
                if line.startswith('event: '):
                    current_event = line[7:]
                    print(f"Event type: {current_event}")
                    continue
                
                if line.startswith('data: '):
                    data = line[6:]
                    print(f"Event data: {data}")
                    
                    if current_event == 'endpoint':
                        # Extract session ID from endpoint URL
                        self.session_id = data.split('session_id=')[1]
                        print(f"\nGot session ID: {self.session_id}")
                    elif current_event == 'tools':
                        try:
                            self.tools = json.loads(data)
                            print("\nReceived tools from server:", [tool.get('name') for tool in self.tools])
                        except json.JSONDecodeError:
                            print(f"Warning: Failed to parse tools data: {data}")
                    elif current_event == 'error':
                        try:
                            error_data = json.loads(data)
                            print(f"MCP server error: {error_data}")
                        except json.JSONDecodeError:
                            print(f"MCP server error (unparseable): {data}")
                    else:
                        print(f"Unknown event type: {current_event}")

    async def connect_and_chat(self):
        """Connect to server and start chat loop"""
        print(f"\nConnecting to MCP server at {self.server_url}")
        
        headers = {
            'api_key': self.mcp_key,
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream'
        }
        
        print(f"Using headers: {json.dumps(headers, indent=2)}")
        
        self.session = aiohttp.ClientSession(headers=headers)
        
        try:
            # Start SSE event handling task
            sse_task = asyncio.create_task(self.handle_sse_events())
            
            # Wait for session ID
            while not self.session_id:
                print("Waiting for session ID...")
                await asyncio.sleep(0.5)
            
            print("\nMCP Client Started!")
            print("Type your queries or 'quit' to exit.")
            
            # Start chat loop
            await self.chat_loop()
            
        except Exception as e:
            print(f"Error in connect_and_chat: {str(e)}")
            raise
        finally:
            if 'sse_task' in locals():
                sse_task.cancel()
                try:
                    await sse_task
                except asyncio.CancelledError:
                    pass

    async def call_tool(self, tool_name: str, args: Dict[str, Any]):
        """Call a tool on the MCP server
        
        Args:
            tool_name: Name of the tool to call
            args: Arguments for the tool
        """
        if not self.session or not self.session_id:
            raise Exception("Not connected to server")

        url = f"{self.server_url}/sse"
        payload = {
            "tool": tool_name,
            "args": args,
            "session_id": self.session_id
        }
        
        print(f"\nMaking tool call to {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        async with self.session.post(url, json=payload) as response:
            print(f"Tool call response status: {response.status}")
            print(f"Tool call response headers: {json.dumps(dict(response.headers), indent=2)}")
            
            if response.status != 200:
                response_text = await response.text()
                print(f"Error response: {response_text}")
                raise Exception(f"Tool call failed: {response.status} - {response_text}")
            
            # Read SSE response for tool result
            print("Reading tool call response...")
            current_event = None
            async for line in response.content:
                line = line.decode('utf-8').strip()
                if not line:
                    continue
                    
                print(f"Tool response line: {line}")
                    
                if line.startswith('event: '):
                    current_event = line[7:]
                    print(f"Tool response event: {current_event}")
                    continue
                
                if line.startswith('data: '):
                    data = line[6:]
                    print(f"Tool response data: {data}")
                    try:
                        result = json.loads(data)
                        if current_event == 'result':
                            return result
                    except json.JSONDecodeError:
                        print(f"Warning: Failed to parse tool response: {data}")
            
            raise Exception("No tool response received")

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        if not self.tools:
            return "Error: No tools available from MCP server yet. Please wait..."

        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        # Convert MCP tool schema to Claude tool schema
        available_tools = []
        for tool in self.tools:
            tool_schema = {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"]
            }
            available_tools.append(tool_schema)

        print("\nAvailable tools:", json.dumps(available_tools, indent=2))
        print("\nSending query to Claude:", query)
        
        try:
            # Initial Claude API call
            response = self.anthropic.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=1000,
                messages=messages,
                tools=available_tools,
                temperature=0
            )
        except Exception as e:
            print(f"Claude API Error: {str(e)}")
            return "Sorry, I encountered an error while processing your request."

        # Process response and handle tool calls
        tool_results = []
        final_text = []

        for content in response.content:
            print(f"\nProcessing content type: {content.type}")
            if content.type == 'text':
                print("Text content:", content.text)
                final_text.append(content.text)
            elif content.type == 'tool_use':
                print(f"\nTool use content:", content)
                
                tool_name = content.name
                tool_args = content.input
                
                try:
                    # Execute tool call
                    print("Making tool call to server...")
                    result = await self.call_tool(tool_name, tool_args)
                    print("Server response:", result)
                    tool_results.append({"call": tool_name, "result": result})

                    # Continue conversation with tool results
                    messages = [
                        {
                            "role": "user",
                            "content": json.dumps(result)
                        }
                    ]

                    # Get next response from Claude
                    response = self.anthropic.messages.create(
                        model="claude-3-sonnet-20240229",
                        max_tokens=1000,
                        messages=messages,
                        temperature=0
                    )

                    # Only append Claude's final response
                    final_text.append(response.content[0].text)
                except Exception as e:
                    error_msg = f"Error executing tool {tool_name}: {str(e)}"
                    print(error_msg)
                    final_text.append(error_msg)

        return "\n".join(final_text)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                    
                response = await self.process_query(query)
                print("\nResponse:", response)
                    
            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()

async def main():
    # Get server URL from environment
    server_url = os.getenv('MCP_SERVER_URL')
    if not server_url:
        print("Error: MCP_SERVER_URL not found in environment")
        sys.exit(1)
        
    client = MCPClientSSE(server_url)
    try:
        # Start SSE event handling and chat loop
        await client.connect_and_chat()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"\nError: {str(e)}")
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())
