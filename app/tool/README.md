# Tool System

This directory contains the implementation of the tool system, which allows for the creation, management, and execution of tools within the application.

## Overview

The tool system consists of several key components:

1. **BaseTool**: The base class for all tools, providing a common interface for tool execution.
2. **ToolCollection**: A collection class for managing multiple tools, with methods for adding, retrieving, and executing tools.
3. **DynamicToolGenerator**: A utility for creating and loading tools dynamically at runtime.

## Tool Collection

The `ToolCollection` class provides a way to manage multiple tools and execute them by name. It includes the following features:

- Singleton pattern for global tool registration
- Methods for adding and retrieving tools
- Tool execution with error handling
- Support for loading tools from the database

### Usage

```python
from app.tool.tool_collection import ToolCollection
from app.tool.examples.weather_tool import WeatherTool

# Create a tool collection
tools = ToolCollection()

# Add a tool
tools.add_tool(WeatherTool())

# Execute a tool
result = await tools.execute(
    name="weather",
    tool_input={"location": "New York", "units": "celsius"}
)
```

### Global Registration

Tools can be registered with the global tool collection using the static `register_tool` method:

```python
from app.tool.tool_collection import ToolCollection
from app.tool.examples.weather_tool import WeatherTool

# Register a tool with the global collection
ToolCollection.register_tool(WeatherTool())

# Get the global instance
tools = ToolCollection.get_instance()

# Execute the registered tool
result = await tools.execute(
    name="weather",
    tool_input={"location": "London"}
)
```

## Dynamic Tool Generator

The `DynamicToolGenerator` class allows for the creation and loading of tools at runtime. This is useful for creating tools dynamically based on user input or loading tools from a database.

### Creating a Dynamic Tool

```python
from app.tool.dynamic_tool_generator import DynamicToolGenerator

# Create a generator
generator = DynamicToolGenerator()

# Define tool parameters
parameters = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "description": "The message to echo"
        }
    },
    "required": ["message"]
}

# Define tool implementation
implementation = """
from typing import Dict, Any
from app.tool.base import BaseTool

class EchoTool(BaseTool):
    \"\"\"Tool for echoing a message.\"\"\"
    
    name = "echo"
    description = "Echo a message back to the user"
    parameters = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message to echo"
            }
        },
        "required": ["message"]
    }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        message = kwargs.get("message", "")
        return {"message": message}
"""

# Create the tool
tool_id = generator.create_tool(
    name="echo",
    description="Echo a message back to the user",
    parameters=parameters,
    implementation=implementation
)

# Load the tool
echo_tool_class = generator.load_tool_from_db(tool_id)
echo_tool = echo_tool_class()

# Register with the tool collection
ToolCollection.register_tool(echo_tool)
```

## Examples

The `examples` directory contains example tools that demonstrate how to create and use tools:

- `weather_tool.py`: A tool for getting weather information for a location
- More examples coming soon!

For a complete example of creating and using dynamic tools, see the `examples/create_dynamic_tool.py` script. 