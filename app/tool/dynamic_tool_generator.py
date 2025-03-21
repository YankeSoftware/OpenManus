"""
Dynamic tool generator for creating new tools on-the-fly.

This module allows agents to dynamically create new tools by generating Python code
and persisting tools for future use.
"""

import importlib
import importlib.util
import json
import os
import uuid
from typing import Any, Dict, List, Optional, Type

from app.logger import logger
from app.persistence.db_manager import DatabaseManager
from app.tool.base import BaseTool


class DynamicToolGenerator:
    """
    Dynamic tool generator for creating and registering tools at runtime.
    
    This class enables:
    - On-the-fly creation of new tools with custom functionality
    - Persistence of created tools for future use
    - Loading previously created tools
    - Validation of dynamically generated tool code
    """
    
    def __init__(self, tools_dir: str = "data/tools"):
        """Initialize the dynamic tool generator.
        
        Args:
            tools_dir: Directory where tool definitions are stored
        """
        self.tools_dir = tools_dir
        os.makedirs(tools_dir, exist_ok=True)
        
    def create_tool(self, 
                   name: str, 
                   description: str, 
                   parameters: Dict[str, Any],
                   implementation: str) -> str:
        """Create a new tool and save it to the database.
        
        Args:
            name: Name of the tool
            description: Description of the tool
            parameters: Parameters schema for the tool
            implementation: Python code implementing the tool
            
        Returns:
            The ID of the created tool
        """
        # Generate a unique ID for the tool
        tool_id = str(uuid.uuid4())
        
        # Create the tool definition
        tool_def = {
            "id": tool_id,
            "name": name,
            "description": description,
            "parameters": parameters,
            "implementation": implementation
        }
        
        # Save the tool definition to a file
        tool_path = os.path.join(self.tools_dir, f"{tool_id}.json")
        with open(tool_path, "w") as f:
            json.dump(tool_def, f, indent=2)
            
        return tool_id
        
    def list_available_tools(self) -> List[Dict[str, Any]]:
        """List all available tools in the database.
        
        Returns:
            List of tool definitions (without implementation)
        """
        tools = []
        
        # Ensure the directory exists
        if not os.path.exists(self.tools_dir):
            return []
            
        # List all JSON files in the directory
        for filename in os.listdir(self.tools_dir):
            if filename.endswith(".json"):
                tool_path = os.path.join(self.tools_dir, filename)
                try:
                    with open(tool_path, "r") as f:
                        tool_def = json.load(f)
                        # Remove implementation from the definition
                        tool_info = {
                            "id": tool_def.get("id"),
                            "name": tool_def.get("name"),
                            "description": tool_def.get("description"),
                            "parameters": tool_def.get("parameters")
                        }
                        tools.append(tool_info)
                except Exception as e:
                    print(f"Error loading tool {filename}: {e}")
                    
        return tools
        
    def load_tool_from_db(self, tool_id: str) -> Optional[Type[BaseTool]]:
        """Load a tool from the database by ID.
        
        Args:
            tool_id: ID of the tool to load
            
        Returns:
            The tool class if found, None otherwise
        """
        tool_path = os.path.join(self.tools_dir, f"{tool_id}.json")
        
        if not os.path.exists(tool_path):
            return None
            
        try:
            # Load the tool definition
            with open(tool_path, "r") as f:
                tool_def = json.load(f)
                
            # Extract the implementation
            implementation = tool_def.get("implementation")
            if not implementation:
                return None
                
            # Create a module for the tool
            module_name = f"dynamic_tool_{tool_id}"
            spec = importlib.util.spec_from_loader(module_name, loader=None)
            module = importlib.util.module_from_spec(spec)
            
            # Execute the implementation in the module
            exec(implementation, module.__dict__)
            
            # Find the tool class in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseTool) and 
                    attr is not BaseTool):
                    return attr
                    
            return None
        except Exception as e:
            print(f"Error loading tool {tool_id}: {e}")
            return None
            
    def delete_tool(self, tool_id: str) -> bool:
        """Delete a tool from the database.
        
        Args:
            tool_id: ID of the tool to delete
            
        Returns:
            True if the tool was deleted, False otherwise
        """
        tool_path = os.path.join(self.tools_dir, f"{tool_id}.json")
        
        if not os.path.exists(tool_path):
            return False
            
        try:
            os.remove(tool_path)
            return True
        except Exception:
            return False 