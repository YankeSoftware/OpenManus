import asyncio
import json
from typing import Dict, List, Any, Optional
import os
import tomli

import aiohttp
from pydantic import Field

from app.tool.base import BaseTool


class BraveSearch(BaseTool):
    name: str = "brave_search"
    description: str = """Perform a Brave Search and return a list of relevant search results.
Use this tool when you need to find information on the web, get up-to-date data, or research specific topics.
The tool returns search results with titles, descriptions, and URLs.
"""
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "(required) The search query to submit to Brave Search.",
            },
            "num_results": {
                "type": "integer",
                "description": "(optional) The number of search results to return. Default is 10. Maximum is 20.",
                "default": 10,
            },
        },
        "required": ["query"],
    }
    
    # Define these as proper fields for Pydantic model
    config: Dict[str, Any] = Field(default_factory=dict)
    api_key: str = Field(default="")
    endpoint: str = Field(default="https://api.search.brave.com/res/v1/web/search")

    def __init__(self, **kwargs):
        """Initialize the Brave Search tool with API configuration."""
        # First call super() with kwargs to initialize the Pydantic model
        super().__init__(**kwargs)
        
        # Load the configuration
        loaded_config = self._load_config()
        
        # Update the fields with loaded values
        self.config = loaded_config
        self.api_key = loaded_config.get("api_key", "")
        self.endpoint = loaded_config.get("endpoint", "https://api.search.brave.com/res/v1/web/search")

    def _load_config(self) -> Dict[str, Any]:
        """Load the Brave Search configuration from the config file."""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "config.toml")
        try:
            with open(config_path, "rb") as f:
                config = tomli.load(f)
                return config.get("brave_search", {})
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return {}

    async def execute(self, query: str, num_results: int = 10) -> Dict[str, Any]:
        """
        Execute a Brave Search and return search results.

        Args:
            query (str): The search query to submit to Brave Search.
            num_results (int, optional): The number of search results to return. Default is 10. Maximum is 20.

        Returns:
            Dict[str, Any]: A dictionary containing search results including titles, descriptions, and URLs.
        """
        if not self.api_key:
            return {"error": "Brave Search API key is not configured. Please add your API key to config/config.toml."}

        if num_results > 20:
            num_results = 20  # Enforce API limit

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key
        }

        params = {
            "q": query,
            "count": num_results
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.endpoint, headers=headers, params=params) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Format results in a more readable way
                        formatted_results = {
                            "query": query,
                            "results": []
                        }
                        
                        if "web" in result and "results" in result["web"]:
                            for item in result["web"]["results"]:
                                formatted_results["results"].append({
                                    "title": item.get("title", ""),
                                    "description": item.get("description", ""),
                                    "url": item.get("url", "")
                                })
                        
                        return formatted_results
                    else:
                        return {
                            "error": f"API request failed with status code: {response.status}",
                            "message": await response.text()
                        }
        except Exception as e:
            return {"error": f"Request failed: {str(e)}"} 