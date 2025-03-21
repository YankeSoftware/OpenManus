"""
Create Tool Tool.

This tool allows agents to dynamically create new tools with custom functionality.
"""

from typing import Dict, Optional

from app.logger import logger
from app.tool.base import BaseTool
from app.tool.dynamic_tool_generator import DynamicToolGenerator
from app.tool.tool_collection import ToolCollection


class CreateTool(BaseTool):
    """
    Tool for dynamically creating new tools with custom functionality.
    
    This tool enables:
    - Creating new tools with custom code
    - Persisting tools for future use
    - Extending the agent's capabilities on-the-fly
    """
    
    name: str = "create_tool"
    description: str = "Create a new tool with custom functionality that can be used by the agent."
    parameters: dict = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the tool to create (should be descriptive and unique).",
            },
            "description": {
                "type": "string",
                "description": "Description of what the tool does.",
            },
            "code": {
                "type": "string",
                "description": "Python code implementing the tool's functionality. Should return a dictionary with an 'observation' key.",
            },
            "parameters": {
                "type": "object",
                "description": "JSON schema for the tool's parameters.",
            },
            "save_to_db": {
                "type": "boolean",
                "description": "Whether to save the tool to the database for future use.",
            },
        },
        "required": ["name", "description", "code"],
    }
    
    async def execute(
        self,
        name: str,
        description: str,
        code: str,
        parameters: Optional[Dict] = None,
        save_to_db: bool = True,
    ) -> Dict:
        """
        Execute the tool by creating a new tool with the provided specifications.
        
        Args:
            name: Name of the tool
            description: Description of the tool
            code: Python code implementing the tool
            parameters: Optional parameters schema
            save_to_db: Whether to save the tool to the database
            
        Returns:
            Dict: Result with tool information
        """
        try:
            # Create the tool generator
            tool_generator = DynamicToolGenerator()
            
            # Generate the tool class
            tool_class = tool_generator.create_tool(
                name=name,
                description=description,
                code=code,
                parameters=parameters,
                save_to_db=save_to_db
            )
            
            if not tool_class:
                return {
                    "success": False,
                    "error": "Failed to create tool",
                    "observation": "Could not create the tool. Check the code for errors."
                }
                
            # Create an instance of the tool
            tool_instance = tool_class()
            
            # Register the tool with the tool collection
            ToolCollection.register_tool(tool_instance)
            
            return {
                "success": True,
                "tool_name": name,
                "observation": f"Successfully created and registered tool '{name}'. The tool is now available for use."
            }
            
        except Exception as e:
            logger.error(f"Error in CreateTool tool: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "observation": f"Error creating tool: {str(e)}"
            }
            
    @staticmethod
    def generate_tool_code_template() -> str:
        """
        Generate a template for tool code.
        
        Returns:
            str: Template code for a new tool
        """
        return """
# Import any necessary libraries
import requests
from typing import Dict

# Your tool implementation
# The execute method should return a dictionary with at least an 'observation' key
# You can use any Python code here, but be careful with external dependencies

# Example implementation:
response = requests.get("https://api.example.com/data")
data = response.json()

# Process the data
result = process_data(data)  # Replace with your actual processing

# Return the result
return {
    "observation": result,
    "additional_info": "Any additional information you want to include"
}
""" 