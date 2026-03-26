"""
Listing page scraper for TUI.nl.
Extracts all hotel names and URLs from the Formentera destination page.
"""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
)

from utils import logger, random_delay, safe_text, safe_attribute

LISTING_URL = "https://www.tui.nl/reizen/spanje/formentera/"


def accept_cookies(driver):
    """Accept the cookie consent banner if present."""
    cookie_selectors = [
        (By.ID, "cmAcceptAll"),
        (By.CSS_SELECTOR, "button[data-testid='accept-cookies']"),
        (By.CSS_SELECTOR, "button.js-accept-cookies"),
        (By.XPATH, "//button[contains(text(), 'Akkoord')]"),
        (By.XPATH, "//button[contains(text(), 'akkoord')]"),
        (By.XPATH, "//button[contains(text(), 'Accept')]"),
        (By.XPATH, "//button[contains(text(), 'Accepteren')]"),
        (By.XPATH, "//button[contains(text(), 'Alle cookies')]"),
        (By.CSS_SELECTOR, "#onetrust-accept-btn-handler"),
    ]

    for by, selector in cookie_selectors:
        try:
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((by, selector))
            )
            btn.click()
            logger.info(f"Accepted cookies via selector: {selector}")
            random_delay(1, 2)
            return True
        except (TimeoutException, NoSuchElementException):
            continue

    logger.info("No cookie banner found or already accepted")
    return False


def load_all_hotels(driver):
    """Click 'Show more' / 'Meer tonen' until all hotels are loaded."""
    show_more_selectors = [
        (By.XPATH, "//button[contains(text(), 'Meer tonen')]"),
        (By.XPATH, "//button[contains(text(), 'Toon meer')]"),
        (By.XPATH, "//button[contains(text(), 'meer resultaten')]"),
        (By.XPATH, "//a[contains(text(), 'Meer tonen')]"),
        (By.CSS_SELECTOR, "button[data-testid='show-more']"),
        (By.CSS_SELECTOR, ".show-more-button"),
    ]

    clicks = 0
    max_clicks = 20  # Safety limit

    while clicks < max_clicks:
        found = False
        for by, selector in show_more_selectors:
            try:
                btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((by, selector))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                random_delay(0.5, 1)
                btn.click()
                clicks += 1
                logger.info(f"Clicked 'show more' ({clicks} times)")
                random_delay(2, 4)
                found = True
                break
            except (TimeoutException, NoSuchElementException, ElementClickInterceptedException):
                continue

        if not found:
            logger.info(f"No more 'show more' buttons found after {clicks} clicks")
            break

    return clicks


def extract_hotels(driver) -> list[dict]:
    """
    Extract all hotel cards from the listing page.
    Returns a list of dicts with 'name', 'url', 'location', 'rating'.
    """
    hotels = []

    # Try multiple selector strategies for hotel cards
    card_selectors = [
        (By.CSS_SELECTOR, "a[data-testid='accommodation-card']"),
        (By.CSS_SELECTOR, "article a[href*='/reizen/']"),
        (By.CSS_SELECTOR, ".search-result-card a"),
        (By.CSS_SELECTOR, "[class*='AccommodationCard'] a"),
        (By.CSS_SELECTOR, "[class*='SearchResult'] a"),
        (By.CSS_SELECTOR, "[class*='productcard'] a"),
        (By.CSS_SELECTOR, "a[href*='formentera'][href*='hotel']"),
        (By.CSS_SELECTOR, "a[href*='/reizen/spanje/formentera/']"),
    ]

    card_elements = []
    for by, selector in card_selectors:
        try:
            elements = driver.find_elements(by, selector)
            if elements:
                card_elements = elements
                logger.info(f"Found {len(elements)} hotel cards with selector: {selector}")
                break
        except Exception:
            continue

    if not card_elements:
        # Fallback: look for all links that look like hotel detail pages
        logger.warning("No hotel cards found via standard selectors, trying broad link search")
        all_links = driver.find_elements(By.TAG_NAME, "a")
        for link in all_links:
            href = safe_attribute(link, "href")
            if (
                href
                and "/reizen/spanje/" in href
                and "formentera" in href
                and href != LISTING_URL
                and href.rstrip("/") != LISTING_URL.rstrip("/")
                and len(href) > len(LISTING_URL) + 5
            ):
                card_elements.append(link)
        logger.info(f"Found {len(card_elements)} hotel links via fallback search")

    # Deduplicate by URL
    seen_urls = set()
    for card in card_elements:
        href = safe_attribute(card, "href")
        if not href or href in seen_urls:
            continue

        # Skip non-hotel links (category pages, etc.)
        if href.rstrip("/") == LISTING_URL.rstrip("/"):
            continue

        seen_urls.add(href)

        name = safe_text(card)
        # If the card text is too long, it likely contains extra info; try to get just the heading
        if len(name) > 100:
            try:
                heading = card.find_element(By.CSS_SELECTOR, "h2, h3, [class*='title'], [class*='name']")
                name = safe_text(heading)
            except NoSuchElementException:
                name = name[:100]

        # Try to extract location and rating from the card
        location = ""
        rating = ""
        try:
            loc_el = card.find_element(By.CSS_SELECTOR, "[class*='location'], [class*='subtitle']")
            location = safe_text(loc_el)
        except NoSuchElementException:
            pass
        try:
            rating_el = card.find_element(By.CSS_SELECTOR, "[class*='rating'], [class*='stars']")
            rating = safe_text(rating_el)
        except NoSuchElementException:
            pass

        hotels.append({
            "name": name if name else f"Hotel at {href}",
            "url": href,
            "location": location,
            "rating": rating,
        })

    logger.info(f"Extracted {len(hotels)} unique hotels")
    return hotels


def get_all_hotels(driver) -> list[dict]:
    """
    Main entry point: navigate to listing page, load all hotels, extract data.
    """
    logger.info(f"Navigating to listing page: {LISTING_URL}")
    driver.get(LISTING_URL)
    random_delay(3, 5)

    accept_cookies(driver)
    random_delay(1, 2)

    load_all_hotels(driver)
    random_delay(1, 2)

    hotels = extract_hotels(driver)
    return hotels
