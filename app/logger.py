import sys
from datetime import datetime
from pathlib import Path

from loguru import logger as _logger

from app.config import PROJECT_ROOT


# Define log format with colors and better structure
LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

# Ensure logs directory exists
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

def define_log_level(
    print_level="INFO",
    logfile_level="DEBUG",
    name: str = None,
    retention="1 week"
):
    """Configure logging with enhanced formatting and organization.
    
    Args:
        print_level: Log level for console output
        logfile_level: Log level for file output
        name: Optional prefix for log file name
        retention: How long to keep log files
    """
    global _print_level
    _print_level = print_level

    # Generate log file name with timestamp
    current_date = datetime.now()
    formatted_date = current_date.strftime("%Y%m%d%H%M%S")
    log_name = f"{name}_{formatted_date}" if name else formatted_date

    # Remove existing handlers
    _logger.remove()
    
    # Add console handler with color formatting
    _logger.add(
        sys.stderr,
        format=LOG_FORMAT,
        level=print_level,
        colorize=True
    )
    
    # Add file handler with rotation and retention
    _logger.add(
        LOGS_DIR / f"{log_name}.log",
        format=LOG_FORMAT,
        level=logfile_level,
        rotation="500 MB",
        retention=retention,
        compression="zip"
    )
    
    # Add error file handler for error tracking
    _logger.add(
        LOGS_DIR / f"{log_name}_error.log",
        format=LOG_FORMAT,
        level="ERROR",
        rotation="100 MB",
        retention=retention,
        compression="zip",
        filter=lambda record: record["level"].name == "ERROR"
    )
    
    return _logger


# Initialize logger with default settings
logger = define_log_level()


if __name__ == "__main__":
    logger.info("Starting application")
    logger.debug("Debug message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    try:
        raise ValueError("Test error")
    except Exception as e:
        logger.exception(f"An error occurred: {e}")
