"""
TUI.nl Formentera Travel Package Scraper
=========================================
Main orchestrator that coordinates listing page and hotel page scrapers
to extract all travel package options.

Usage:
    python src/scraper.py [--headless] [--max-hotels N]
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    ChromeDriverManager = None

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import logger, random_delay
from listing_page import get_all_hotels
from hotel_page import scrape_hotel_offers

# Defaults
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "tui_formentera_packages.json")
SOURCE_URL = "https://www.tui.nl/reizen/spanje/formentera/"


def create_driver(headless: bool = False) -> webdriver.Chrome:
    """Create and configure a Chrome WebDriver instance."""
    options = ChromeOptions()

    if headless:
        options.add_argument("--headless=new")

    # Anti-detection measures
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # General stability
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=nl-NL")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # Disable images for faster loading (optional)
    # prefs = {"profile.managed_default_content_settings.images": 2}
    # options.add_experimental_option("prefs", prefs)

    if ChromeDriverManager:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    # Override navigator.webdriver property
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )

    driver.implicitly_wait(5)
    return driver


def save_results(packages: list[dict], output_path: str):
    """Save scraped packages to a JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    result = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source_url": SOURCE_URL,
        "total_packages": len(packages),
        "packages": packages,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(packages)} packages to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="TUI.nl Formentera Travel Package Scraper")
    parser.add_argument(
        "--headless", action="store_true",
        help="Run browser in headless mode (no visible window)"
    )
    parser.add_argument(
        "--max-hotels", type=int, default=0,
        help="Maximum number of hotels to scrape (0 = all)"
    )
    parser.add_argument(
        "--output", type=str, default=OUTPUT_FILE,
        help=f"Output JSON file path (default: {OUTPUT_FILE})"
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("TUI.nl Formentera Travel Package Scraper")
    logger.info("=" * 60)

    driver = None
    try:
        # 1. Launch browser
        logger.info(f"Starting Chrome (headless={args.headless})...")
        driver = create_driver(headless=args.headless)

        # 2. Get all hotels from listing page
        logger.info("Step 1/3: Fetching hotel listings...")
        hotels = get_all_hotels(driver)

        if not hotels:
            logger.error("No hotels found on the listing page. Exiting.")
            return

        logger.info(f"Found {len(hotels)} hotels on the listing page:")
        for i, h in enumerate(hotels, 1):
            logger.info(f"  {i}. {h['name']} — {h['url']}")

        # Limit hotels if requested
        if args.max_hotels > 0:
            hotels = hotels[: args.max_hotels]
            logger.info(f"Limiting to first {args.max_hotels} hotel(s)")

        # 3. Scrape each hotel's offers
        logger.info("Step 2/3: Scraping hotel offers...")
        all_packages = []

        for i, hotel in enumerate(hotels, 1):
            logger.info(f"\n{'—' * 40}")
            logger.info(f"Hotel {i}/{len(hotels)}: {hotel['name']}")
            logger.info(f"{'—' * 40}")

            packages = scrape_hotel_offers(driver, hotel)
            all_packages.extend(packages)

            logger.info(f"Cumulative packages: {len(all_packages)}")
            random_delay(2, 4)

        # 4. Save results
        logger.info("Step 3/3: Saving results...")

        # Remove non-serializable 'element' keys from packages
        for pkg in all_packages:
            pkg.pop("element", None)

        save_results(all_packages, args.output)

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("SCRAPING COMPLETE")
        logger.info(f"  Hotels scraped: {len(hotels)}")
        logger.info(f"  Total packages: {len(all_packages)}")
        logger.info(f"  Output file:    {args.output}")
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.info("\nScraping interrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()
            logger.info("Browser closed.")


if __name__ == "__main__":
    main()
