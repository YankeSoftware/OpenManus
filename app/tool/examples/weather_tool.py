"""Example weather tool to demonstrate the dynamic tool system."""
import json
import random
from typing import Dict, Any

from app.tool.base import BaseTool
from app.tool.tool_collection import ToolCollection


class WeatherTool(BaseTool):
    """Tool for getting weather information for a location."""
    
    name = "weather"
    description = "Get weather information for a location"
    parameters = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The location to get weather for (city name)"
            },
            "units": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "Temperature units (celsius or fahrenheit)",
                "default": "celsius"
            }
        },
        "required": ["location"]
    }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the weather tool.
        
        Args:
            location: The location to get weather for
            units: Temperature units (celsius or fahrenheit)
            
        Returns:
            Dict with weather information
        """
        location = kwargs.get("location", "")
        units = kwargs.get("units", "celsius")
        
        # In a real implementation, this would call a weather API
        # For demonstration, we'll return mock data
        
        # Generate random temperature between 0 and 30 celsius
        temp_c = random.uniform(0, 30)
        
        # Convert to fahrenheit if requested
        if units == "fahrenheit":
            temp = (temp_c * 9/5) + 32
            temp_unit = "°F"
        else:
            temp = temp_c
            temp_unit = "°C"
            
        # Generate random conditions
        conditions = random.choice([
            "Sunny", "Partly Cloudy", "Cloudy", 
            "Rainy", "Thunderstorms", "Snowy", "Foggy"
        ])
        
        # Generate random humidity
        humidity = random.randint(30, 90)
        
        # Generate random wind speed
        wind_speed = random.uniform(0, 30)
        
        return {
            "location": location,
            "temperature": round(temp, 1),
            "temperature_unit": temp_unit,
            "conditions": conditions,
            "humidity": humidity,
            "wind_speed": round(wind_speed, 1),
            "wind_unit": "km/h",
            "forecast": "This is a mock weather forecast for demonstration purposes."
        }


# Register the tool with the global tool collection
ToolCollection.register_tool(WeatherTool()) 