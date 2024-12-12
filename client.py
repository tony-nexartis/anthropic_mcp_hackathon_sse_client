import asyncio
from typing import Optional
from contextlib import AsyncExitStack
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env

class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()
        self.stdio = None
        self.write = None

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server
        
        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")
            
        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )
        
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        await self.session.initialize()
        
        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        response = await self.session.list_tools()
        
        # Convert MCP tool schema to Claude tool schema
        available_tools = []
        for tool in response.tools:
            tool_schema = {
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": tool.inputSchema["properties"],
                    "required": tool.inputSchema.get("required", [])
                }
            }
            available_tools.append(tool_schema)

        print("\nAvailable tools:", available_tools)  # Debug output
        
        try:
            print("\nSending query to Claude:", query)
            # Initial Claude API call
            response = self.anthropic.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=1000,
                messages=messages,
                tools=available_tools,
                temperature=0
            )
            print("\nClaude response type:", [content.type for content in response.content])
        except Exception as e:
            print(f"Claude API Error: {str(e)}")
            print(f"Tools format sent: {available_tools}")  # Additional debug info
            return "Sorry, I encountered an error while processing your request."

        # Process response and handle tool calls
        tool_results = []
        final_text = []

        # Store Claude's initial text response
        initial_text = None
        tool_use_block = None

        # Process Claude's response
        for content in response.content:
            print(f"\nProcessing content type: {content.type}")
            if content.type == 'text':
                print("Text content:", content.text)
                initial_text = content.text
                final_text.append(content.text)
            elif content.type == 'tool_use':
                print(f"\nTool use content:", content)
                tool_use_block = content
                # Handle the ToolUseBlock directly
                tool_name = content.name
                tool_args = content.input
                tool_id = content.id
                    
        if tool_use_block:
            print(f"\nCalling tool: {tool_name}")
            print(f"Arguments: {tool_args}")
                
            try:
                # Execute tool call
                print("Making tool call to server...")
                result = await self.session.call_tool(tool_name, tool_args)
                print("Server response:", result.content)
                tool_results.append({"call": tool_name, "result": result})
                # Get just the text content from the response
                raw_text = result.content[0].text

                # Continue conversation with tool results
                messages = [
                    {
                        "role": "user",
                        "content": raw_text
                    }
                ]

                # Get next response from Claude
                response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    messages=messages
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
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                    
                response = await self.process_query(query)
                print("\n" + response)
                    
            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        if self.exit_stack:
            await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)
        
    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())
