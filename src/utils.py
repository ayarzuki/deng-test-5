"""
Utility functions for the TUI.nl scraper.
Provides logging, delays, and retry logic for polite and robust scraping.
"""

import time
import random
import logging
from functools import wraps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("tui_scraper")


def random_delay(min_seconds: float = 2.0, max_seconds: float = 5.0):
    """Sleep for a random duration between min and max seconds (scraping etiquette)."""
    delay = random.uniform(min_seconds, max_seconds)
    logger.debug(f"Waiting {delay:.1f}s...")
    time.sleep(delay)


def retry(max_retries: int = 3, delay_base: float = 2.0):
    """
    Decorator: retry a function with exponential backoff.
    Usage: @retry(max_retries=3)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    wait = delay_base * (2 ** (attempt - 1)) + random.uniform(0, 1)
                    logger.warning(
                        f"Attempt {attempt}/{max_retries} for {func.__name__} failed: {e}. "
                        f"Retrying in {wait:.1f}s..."
                    )
                    time.sleep(wait)
            logger.error(f"All {max_retries} attempts failed for {func.__name__}")
            raise last_exception
        return wrapper
    return decorator


def safe_text(element) -> str:
    """Safely extract text from a Selenium WebElement, returning empty string on failure."""
    try:
        return element.text.strip()
    except Exception:
        return ""


def safe_attribute(element, attr: str) -> str:
    """Safely extract an attribute from a Selenium WebElement."""
    try:
        return (element.get_attribute(attr) or "").strip()
    except Exception:
        return ""
