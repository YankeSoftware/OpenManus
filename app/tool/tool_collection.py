"""Collection classes for managing multiple tools."""
from typing import Any, Dict, List, Optional, Type

from app.exceptions import ToolError
from app.tool.base import BaseTool, ToolFailure, ToolResult


class ToolCollection:
    """A collection of defined tools."""

    # Static instance for global tool registration
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'ToolCollection':
        """Get the singleton instance of ToolCollection."""
        if cls._instance is None:
            cls._instance = ToolCollection()
        return cls._instance
    
    @classmethod
    def register_tool(cls, tool: BaseTool) -> None:
        """Register a tool with the global tool collection."""
        instance = cls.get_instance()
        instance.add_tool(tool)

    def __init__(self, *tools: BaseTool):
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}
        
        # Register this instance if no global instance exists
        if ToolCollection._instance is None:
            ToolCollection._instance = self

    def __iter__(self):
        return iter(self.tools)

    def to_params(self) -> List[Dict[str, Any]]:
        return [tool.to_param() for tool in self.tools]

    async def execute(
        self, *, name: str, tool_input: Dict[str, Any] = None
    ) -> ToolResult:
        tool = self.tool_map.get(name)
        if not tool:
            # Try to load the tool from the database
            tool = await self._load_tool_from_db(name)
            if not tool:
                return ToolFailure(error=f"Tool {name} is invalid")
                
        try:
            result = await tool(**tool_input)
            return result
        except ToolError as e:
            return ToolFailure(error=e.message)

    async def execute_all(self) -> List[ToolResult]:
        """Execute all tools in the collection sequentially."""
        results = []
        for tool in self.tools:
            try:
                result = await tool()
                results.append(result)
            except ToolError as e:
                results.append(ToolFailure(error=e.message))
        return results

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name, optionally loading it from the database."""
        tool = self.tool_map.get(name)
        if tool:
            return tool
            
        # Try to load from database (synchronous version)
        try:
            from app.tool.dynamic_tool_generator import DynamicToolGenerator
            generator = DynamicToolGenerator()
            
            # Find tool by name in database
            tools = generator.list_available_tools()
            for tool_data in tools:
                if tool_data['name'] == name:
                    # Load the tool class
                    tool_class = generator.load_tool_from_db(tool_data['id'])
                    if tool_class:
                        # Create an instance and register it
                        tool_instance = tool_class()
                        self.add_tool(tool_instance)
                        return tool_instance
        except Exception:
            pass
            
        return None
        
    async def _load_tool_from_db(self, name: str) -> Optional[BaseTool]:
        """Asynchronously load a tool from the database by name."""
        try:
            from app.tool.dynamic_tool_generator import DynamicToolGenerator
            generator = DynamicToolGenerator()
            
            # Find tool by name in database
            tools = generator.list_available_tools()
            for tool_data in tools:
                if tool_data['name'] == name:
                    # Load the tool class
                    tool_class = generator.load_tool_from_db(tool_data['id'])
                    if tool_class:
                        # Create an instance and register it
                        tool_instance = tool_class()
                        self.add_tool(tool_instance)
                        return tool_instance
        except Exception:
            pass
            
        return None

    def add_tool(self, tool: BaseTool):
        """Add a tool to the collection."""
        self.tools = self.tools + (tool,)
        self.tool_map[tool.name] = tool
        return self

    def add_tools(self, *tools: BaseTool):
        """Add multiple tools to the collection."""
        for tool in tools:
            self.add_tool(tool)
        return self
        
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools with their descriptions."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
            for tool in self.tools
        ]
