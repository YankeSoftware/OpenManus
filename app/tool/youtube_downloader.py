import os
import asyncio
from typing import Dict, Any, Optional, List
import subprocess
import sys
from pydantic import Field

from app.tool.base import BaseTool
from app.logger import logger


class YouTubeDownloader(BaseTool):
    """Tool for downloading YouTube videos."""
    
    name: str = "youtube_downloader"
    description: str = """Download YouTube videos in various quality formats.
Use this tool when you need to download videos from YouTube.
The tool supports different quality options and returns information about the downloaded video.
"""
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "(required) The YouTube video URL to download.",
            },
            "output_dir": {
                "type": "string",
                "description": "(required) Directory where the video should be saved.",
            },
            "quality": {
                "type": "string",
                "description": "(optional) Video quality to download. Options: 'highest', 'lowest', '720p', '1080p', etc.",
                "default": "highest",
            },
            "audio_only": {
                "type": "boolean",
                "description": "(optional) Whether to download only the audio track.",
                "default": False,
            },
        },
        "required": ["url", "output_dir"],
    }
    
    def _ensure_pytube_installed(self) -> bool:
        """Check if pytube is installed, and install if not."""
        try:
            import pytube
            return True
        except ImportError:
            logger.info("Installing pytube package...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pytube"])
                return True
            except Exception as e:
                logger.error(f"Failed to install pytube: {str(e)}")
                return False
    
    async def execute(self, url: str, output_dir: str, quality: str = "highest", audio_only: bool = False) -> Dict[str, Any]:
        """
        Download a YouTube video.
        
        Args:
            url: YouTube video URL
            output_dir: Directory to save the video
            quality: Video quality ('highest', 'lowest', '720p', '1080p', etc.)
            audio_only: If True, download only audio
            
        Returns:
            Dict containing download status and information
        """
        if not self._ensure_pytube_installed():
            return {
                "success": False,
                "error": "Failed to install required pytube package",
                "message": "The pytube package is required but could not be installed."
            }
        
        # Import here to ensure it's available
        import pytube
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            # Run YouTube operations in a thread to prevent blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._download_video, url, output_dir, quality, audio_only)
        except Exception as e:
            logger.error(f"Error downloading YouTube video: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to download video from {url}"
            }
    
    def _download_video(self, url: str, output_dir: str, quality: str, audio_only: bool) -> Dict[str, Any]:
        """Execute the actual download in a separate thread."""
        import pytube
        
        try:
            # Create YouTube object
            yt = pytube.YouTube(url)
            
            # Get video details
            video_details = {
                "title": yt.title,
                "author": yt.author,
                "length_seconds": yt.length,
                "views": yt.views,
                "description": yt.description[:200] + "..." if len(yt.description) > 200 else yt.description
            }
            
            # Get available streams
            if audio_only:
                # Download audio only
                stream = yt.streams.get_audio_only()
                file_extension = "mp4"  # Audio is usually in mp4 container
            else:
                # Handle video quality selection
                if quality == "highest":
                    stream = yt.streams.get_highest_resolution()
                elif quality == "lowest":
                    stream = yt.streams.get_lowest_resolution()
                else:
                    # Try to get specific resolution
                    stream = yt.streams.filter(res=quality, progressive=True).first()
                    
                    # If not found, fall back to highest resolution
                    if not stream:
                        logger.warning(f"Resolution {quality} not available, using highest resolution")
                        stream = yt.streams.get_highest_resolution()
                
                file_extension = stream.subtype
            
            # Download the stream
            logger.info(f"Downloading {yt.title} ({stream.resolution if not audio_only else 'audio only'})")
            output_path = stream.download(output_path=output_dir)
            
            # Rename to include quality info if video
            if not audio_only:
                base_path = os.path.splitext(output_path)[0]
                new_path = f"{base_path}_{stream.resolution}.{file_extension}"
                os.rename(output_path, new_path)
                output_path = new_path
            
            # Get file size
            file_size = os.path.getsize(output_path)
            
            return {
                "success": True,
                "video_details": video_details,
                "download_details": {
                    "file_path": output_path,
                    "file_size_bytes": file_size,
                    "file_size_mb": round(file_size / (1024 * 1024), 2),
                    "resolution": stream.resolution if not audio_only else "audio only",
                    "format": file_extension
                },
                "message": f"Successfully downloaded {yt.title} to {output_path}"
            }
            
        except Exception as e:
            logger.error(f"Error in YouTube download: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to download YouTube video: {str(e)}"
            } 