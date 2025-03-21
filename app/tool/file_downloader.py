import os
import asyncio
from typing import Dict, Any, Optional
import aiohttp
from pydantic import Field

from app.tool.base import BaseTool
from app.logger import logger


class FileDownloader(BaseTool):
    """Tool for downloading large files including videos."""
    
    name: str = "file_downloader"
    description: str = """Download large files (including videos, images, and documents) from a URL to the local file system.
Use this tool when you need to save media content from the internet, such as videos, large documents, or datasets.
The tool handles chunked downloading to support files of any size.
"""
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "(required) The URL of the file to download.",
            },
            "output_path": {
                "type": "string",
                "description": "(required) The local file path where the file should be saved.",
            },
            "chunk_size": {
                "type": "integer",
                "description": "(optional) Size of chunks to download in bytes. Default is 1MB.",
                "default": 1048576,  # 1MB
            },
        },
        "required": ["url", "output_path"],
    }
    
    async def execute(self, url: str, output_path: str, chunk_size: int = 1048576) -> Dict[str, Any]:
        """
        Download a file from a URL using chunked transfer to handle large files.
        
        Args:
            url: The URL of the file to download
            output_path: Local path where the file should be saved
            chunk_size: Size of each chunk in bytes (default: 1MB)
            
        Returns:
            Dict containing download status and information
        """
        # Ensure the directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        total_downloaded = 0
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, allow_redirects=True) as response:
                    if response.status != 200:
                        return {
                            "success": False,
                            "error": f"Failed to download file: HTTP {response.status}",
                            "details": await response.text()
                        }
                    
                    content_length = response.content_length
                    logger.info(f"Starting download of {url} ({content_length if content_length else 'unknown'} bytes)")
                    
                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            if chunk:
                                f.write(chunk)
                                total_downloaded += len(chunk)
                                
                                # Log progress periodically
                                if content_length:
                                    progress = total_downloaded / content_length * 100
                                    if total_downloaded % (chunk_size * 10) == 0:
                                        logger.info(f"Download progress: {progress:.1f}% ({total_downloaded}/{content_length} bytes)")
            
            end_time = asyncio.get_event_loop().time()
            duration = end_time - start_time
            logger.info(f"Download complete: {total_downloaded} bytes in {duration:.2f} seconds")
            
            # Get file size on disk to confirm
            file_size = os.path.getsize(output_path)
            
            return {
                "success": True,
                "file_path": output_path,
                "file_size_bytes": file_size,
                "download_time_seconds": duration,
                "download_speed_mbps": (total_downloaded / 1024 / 1024) / duration if duration > 0 else 0,
                "message": f"Successfully downloaded {url} to {output_path}"
            }
            
        except Exception as e:
            logger.error(f"Error downloading file: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to download file from {url}"
            } 