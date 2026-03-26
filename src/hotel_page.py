"""
Hotel detail page scraper for TUI.nl.
Extracts all offer combinations (meal plan × airport) for a given hotel,
selecting cheapest room and flight for each combo.
"""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)

from utils import logger, random_delay, safe_text, safe_attribute, retry


def _click_element(driver, element):
    """Click an element, using JS click as fallback."""
    try:
        element.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", element)


def _get_dropdown_options(driver, dropdown_selectors, option_selectors):
    """
    Open a dropdown and extract all option texts and values.
    Returns list of (text, value) tuples.
    """
    options = []

    for d_by, d_sel in dropdown_selectors:
        try:
            dropdown = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((d_by, d_sel))
            )
            _click_element(driver, dropdown)
            random_delay(0.5, 1.5)

            for o_by, o_sel in option_selectors:
                try:
                    option_elements = driver.find_elements(o_by, o_sel)
                    if option_elements:
                        for opt in option_elements:
                            text = safe_text(opt)
                            value = safe_attribute(opt, "value") or safe_attribute(opt, "data-value") or text
                            if text:
                                options.append((text, value, opt))
                        break
                except Exception:
                    continue

            if options:
                # Close dropdown by clicking elsewhere
                try:
                    driver.find_element(By.TAG_NAME, "body").click()
                    random_delay(0.3, 0.5)
                except Exception:
                    pass
                return options
        except (TimeoutException, NoSuchElementException):
            continue

    return options


def _select_duration_8_days(driver):
    """Select 8 days / 7 nights duration if not already selected."""
    duration_selectors = [
        (By.XPATH, "//button[contains(text(), '8 dagen')]"),
        (By.XPATH, "//option[contains(text(), '8 dagen')]"),
        (By.XPATH, "//*[contains(text(), '8 dagen')]"),
        (By.XPATH, "//button[contains(text(), '8 dag')]"),
        (By.CSS_SELECTOR, "[data-testid='duration-select']"),
        (By.CSS_SELECTOR, "[class*='duration'] select"),
        (By.CSS_SELECTOR, "select[name*='duration']"),
    ]

    # First check if there's a dropdown for duration
    select_selectors = [
        (By.CSS_SELECTOR, "[data-testid='duration-select']"),
        (By.CSS_SELECTOR, "[class*='duration'] select"),
        (By.CSS_SELECTOR, "select[name*='duration']"),
        (By.XPATH, "//select[.//option[contains(text(), 'dagen')]]"),
    ]

    for by, selector in select_selectors:
        try:
            from selenium.webdriver.support.ui import Select
            select_el = driver.find_element(by, selector)
            select = Select(select_el)
            for option in select.options:
                if "8" in option.text and "dag" in option.text:
                    select.select_by_visible_text(option.text)
                    logger.info(f"Selected duration: {option.text}")
                    random_delay(1, 2)
                    return True
        except Exception:
            continue

    # Try clicking a duration button/tab
    for by, selector in duration_selectors:
        try:
            el = driver.find_element(by, selector)
            _click_element(driver, el)
            logger.info(f"Clicked duration selector: {selector}")
            random_delay(1, 2)
            return True
        except (NoSuchElementException, ElementClickInterceptedException):
            continue

    logger.warning("Could not find duration selector for 8 days")
    return False


def _get_available_meal_plans(driver) -> list[dict]:
    """
    Find all available meal plan (verzorging) options.
    Returns list of dicts with 'text' and 'element' or empty list.
    """
    meal_plans = []

    # Strategy 1: Look for a select dropdown
    select_selectors = [
        (By.CSS_SELECTOR, "select[name*='board'], select[name*='meal'], select[name*='verzorging']"),
        (By.CSS_SELECTOR, "[data-testid*='board'] select, [data-testid*='meal'] select"),
        (By.XPATH, "//select[.//option[contains(text(), 'inclusief') or contains(text(), 'ontbijt') or contains(text(), 'halfpension')]]"),
    ]

    for by, selector in select_selectors:
        try:
            from selenium.webdriver.support.ui import Select
            select_el = driver.find_element(by, selector)
            select = Select(select_el)
            for option in select.options:
                text = option.text.strip()
                if text and text != "---":
                    meal_plans.append({
                        "text": text,
                        "value": option.get_attribute("value") or text,
                        "type": "select",
                        "selector_info": (by, selector),
                    })
            if meal_plans:
                logger.info(f"Found {len(meal_plans)} meal plans via <select>")
                return meal_plans
        except (NoSuchElementException, Exception):
            continue

    # Strategy 2: Look for radio buttons or clickable options
    radio_selectors = [
        (By.CSS_SELECTOR, "[class*='board'] input[type='radio'], [class*='meal'] input[type='radio']"),
        (By.CSS_SELECTOR, "[data-testid*='board-type'] label"),
        (By.CSS_SELECTOR, "[class*='mealplan'] label, [class*='verzorging'] label"),
    ]

    for by, selector in radio_selectors:
        try:
            elements = driver.find_elements(by, selector)
            for el in elements:
                text = safe_text(el)
                if text:
                    meal_plans.append({"text": text, "element": el, "type": "radio"})
            if meal_plans:
                logger.info(f"Found {len(meal_plans)} meal plans via radio buttons")
                return meal_plans
        except Exception:
            continue

    # Strategy 3: Look for any section labeled verzorging / meal plan
    section_selectors = [
        (By.XPATH, "//*[contains(text(), 'Verzorging') or contains(text(), 'verzorging')]"),
        (By.XPATH, "//*[contains(text(), 'Maaltijden') or contains(text(), 'maaltijden')]"),
    ]

    for by, selector in section_selectors:
        try:
            section = driver.find_element(by, selector)
            parent = section.find_element(By.XPATH, "./..")
            options = parent.find_elements(By.CSS_SELECTOR, "button, label, a, li, option")
            for opt in options:
                text = safe_text(opt)
                if text and len(text) < 100:
                    meal_plans.append({"text": text, "element": opt, "type": "button"})
            if meal_plans:
                logger.info(f"Found {len(meal_plans)} meal plan options near 'verzorging' label")
                return meal_plans
        except Exception:
            continue

    logger.warning("No meal plan options found, will use default")
    return [{"text": "Default (as shown)", "value": "default", "type": "none"}]


def _get_available_airports(driver) -> list[dict]:
    """
    Find all available departure airport options.
    Returns list of dicts with 'text' and optionally 'element'.
    """
    airports = []

    # Strategy 1: Look for a <select> dropdown
    select_selectors = [
        (By.CSS_SELECTOR, "select[name*='airport'], select[name*='departure'], select[name*='vertrek']"),
        (By.CSS_SELECTOR, "[data-testid*='airport'] select, [data-testid*='departure'] select"),
        (By.XPATH, "//select[.//option[contains(text(), 'Schiphol') or contains(text(), 'Amsterdam') or contains(text(), 'Eindhoven') or contains(text(), 'Rotterdam')]]"),
    ]

    for by, selector in select_selectors:
        try:
            from selenium.webdriver.support.ui import Select
            select_el = driver.find_element(by, selector)
            select = Select(select_el)
            for option in select.options:
                text = option.text.strip()
                if text and text != "---" and text.lower() != "kies":
                    airports.append({
                        "text": text,
                        "value": option.get_attribute("value") or text,
                        "type": "select",
                        "selector_info": (by, selector),
                    })
            if airports:
                logger.info(f"Found {len(airports)} airports via <select>")
                return airports
        except (NoSuchElementException, Exception):
            continue

    # Strategy 2: Look near "vertrekplaats" / airport label
    section_selectors = [
        (By.XPATH, "//*[contains(text(), 'Vertrek') or contains(text(), 'vertrek')]"),
        (By.XPATH, "//*[contains(text(), 'Luchthaven') or contains(text(), 'luchthaven')]"),
        (By.XPATH, "//*[contains(text(), 'Airport') or contains(text(), 'airport')]"),
    ]

    for by, selector in section_selectors:
        try:
            section = driver.find_element(by, selector)
            parent = section.find_element(By.XPATH, "./..")
            options = parent.find_elements(By.CSS_SELECTOR, "button, label, a, li, option, input[type='radio']")
            for opt in options:
                text = safe_text(opt)
                if text and len(text) < 100:
                    airports.append({"text": text, "element": opt, "type": "button"})
            if airports:
                logger.info(f"Found {len(airports)} airports near 'vertrek' label")
                return airports
        except Exception:
            continue

    logger.warning("No airport options found, will use default")
    return [{"text": "Default (as shown)", "value": "default", "type": "none"}]


def _select_option(driver, option_info: dict):
    """Select a meal plan or airport option based on its type."""
    if option_info["type"] == "select":
        from selenium.webdriver.support.ui import Select
        by, selector = option_info["selector_info"]
        select_el = driver.find_element(by, selector)
        select = Select(select_el)
        select.select_by_value(option_info["value"])
        random_delay(1, 3)
    elif option_info["type"] in ("radio", "button"):
        if "element" in option_info:
            _click_element(driver, option_info["element"])
            random_delay(1, 3)
    # type "none" means default, nothing to do


def _extract_room_options(driver) -> list[dict]:
    """Extract available room types and prices from the current page state."""
    rooms = []

    room_selectors = [
        (By.CSS_SELECTOR, "[class*='room-type'], [class*='RoomType'], [class*='roomtype']"),
        (By.CSS_SELECTOR, "[data-testid*='room']"),
        (By.CSS_SELECTOR, "[class*='accommodation-option']"),
        (By.CSS_SELECTOR, "tr[class*='room'], li[class*='room']"),
    ]

    for by, selector in room_selectors:
        try:
            elements = driver.find_elements(by, selector)
            if elements:
                for el in elements:
                    text = safe_text(el)
                    # Try to extract name and price
                    name = text
                    price = None

                    # Look for a name element inside
                    try:
                        name_el = el.find_element(By.CSS_SELECTOR,
                            "[class*='name'], [class*='title'], h3, h4, strong")
                        name = safe_text(name_el)
                    except NoSuchElementException:
                        pass

                    # Look for price
                    try:
                        price_el = el.find_element(By.CSS_SELECTOR,
                            "[class*='price'], [class*='Price']")
                        price_text = safe_text(price_el)
                        price = _parse_price(price_text)
                    except NoSuchElementException:
                        pass

                    if name:
                        rooms.append({"name": name, "price": price, "element": el})

                if rooms:
                    logger.info(f"Found {len(rooms)} room options")
                    return rooms
        except Exception:
            continue

    logger.warning("No room options found")
    return []


def _extract_flight_options(driver) -> list[dict]:
    """Extract available flight options from the current page state."""
    flights = []

    flight_selectors = [
        (By.CSS_SELECTOR, "[class*='flight'], [class*='Flight']"),
        (By.CSS_SELECTOR, "[data-testid*='flight']"),
        (By.CSS_SELECTOR, "[class*='vlucht'], [class*='Vlucht']"),
    ]

    for by, selector in flight_selectors:
        try:
            elements = driver.find_elements(by, selector)
            if elements:
                for el in elements:
                    text = safe_text(el)
                    flight = {
                        "departure_time": "",
                        "arrival_time": "",
                        "airline": "",
                        "price": None,
                    }

                    # Try to extract structured data
                    try:
                        dep_el = el.find_element(By.CSS_SELECTOR,
                            "[class*='departure'], [class*='depart']")
                        flight["departure_time"] = safe_text(dep_el)
                    except NoSuchElementException:
                        pass

                    try:
                        arr_el = el.find_element(By.CSS_SELECTOR,
                            "[class*='arrival'], [class*='arriv']")
                        flight["arrival_time"] = safe_text(arr_el)
                    except NoSuchElementException:
                        pass

                    try:
                        airline_el = el.find_element(By.CSS_SELECTOR,
                            "[class*='airline'], [class*='carrier']")
                        flight["airline"] = safe_text(airline_el)
                    except NoSuchElementException:
                        pass

                    try:
                        price_el = el.find_element(By.CSS_SELECTOR,
                            "[class*='price'], [class*='Price']")
                        flight["price"] = _parse_price(safe_text(price_el))
                    except NoSuchElementException:
                        pass

                    # If we couldn't get structured data, parse from full text
                    if not flight["departure_time"] and text:
                        flight["raw_text"] = text
                        # Try to extract times from text (HH:MM pattern)
                        import re
                        times = re.findall(r'\d{1,2}:\d{2}', text)
                        if len(times) >= 2:
                            flight["departure_time"] = times[0]
                            flight["arrival_time"] = times[1]
                        elif len(times) == 1:
                            flight["departure_time"] = times[0]

                    flights.append(flight)

                if flights:
                    logger.info(f"Found {len(flights)} flight options")
                    return flights
        except Exception:
            continue

    logger.warning("No flight options found")
    return []


def _extract_price_and_tax(driver) -> tuple:
    """Extract the final price per person and tourist tax from the page."""
    price_per_person = None
    tourist_tax = None

    # Price per person
    price_selectors = [
        (By.CSS_SELECTOR, "[class*='price-per-person'], [class*='pricePerPerson']"),
        (By.CSS_SELECTOR, "[data-testid*='price']"),
        (By.CSS_SELECTOR, "[class*='total-price'], [class*='totalPrice']"),
        (By.CSS_SELECTOR, "[class*='MainPrice'], [class*='main-price']"),
        (By.XPATH, "//*[contains(text(), 'p.p.')]"),
        (By.XPATH, "//*[contains(text(), 'per persoon')]"),
    ]

    for by, selector in price_selectors:
        try:
            el = driver.find_element(by, selector)
            text = safe_text(el)
            parsed = _parse_price(text)
            if parsed is not None:
                price_per_person = parsed
                logger.debug(f"Found price per person: {price_per_person}")
                break
        except (NoSuchElementException, Exception):
            continue

    # Tourist tax
    tax_selectors = [
        (By.XPATH, "//*[contains(text(), 'toeristenbelasting')]"),
        (By.XPATH, "//*[contains(text(), 'Toeristenbelasting')]"),
        (By.XPATH, "//*[contains(text(), 'tourist tax')]"),
        (By.CSS_SELECTOR, "[class*='tourist-tax'], [class*='touristTax']"),
    ]

    for by, selector in tax_selectors:
        try:
            el = driver.find_element(by, selector)
            text = safe_text(el)
            parsed = _parse_price(text)
            if parsed is not None:
                tourist_tax = parsed
                logger.debug(f"Found tourist tax: {tourist_tax}")
                break
        except (NoSuchElementException, Exception):
            continue

    return price_per_person, tourist_tax


def _parse_price(text: str):
    """Parse a price from text like '€ 899', '899,-', '€899,50', etc."""
    if not text:
        return None
    import re
    # Remove currency symbols and whitespace
    cleaned = text.replace("€", "").replace("EUR", "").strip()
    # Try to find a number (with optional decimal part)
    match = re.search(r'(\d[\d.,]*\d|\d+)', cleaned)
    if match:
        price_str = match.group(1)
        # Handle Dutch notation: 1.234,56 → 1234.56
        if "," in price_str and "." in price_str:
            price_str = price_str.replace(".", "").replace(",", ".")
        elif "," in price_str:
            price_str = price_str.replace(",", ".")
        try:
            return float(price_str)
        except ValueError:
            return None
    return None


def scrape_hotel_offers(driver, hotel: dict) -> list[dict]:
    """
    Scrape all offer combinations for a single hotel.
    Returns a list of package dicts.
    """
    url = hotel["url"]
    logger.info(f"Scraping hotel: {hotel['name']} at {url}")

    try:
        driver.get(url)
        random_delay(3, 5)
    except Exception as e:
        logger.error(f"Failed to load hotel page {url}: {e}")
        return []

    # Select 8 days duration
    _select_duration_8_days(driver)
    random_delay(1, 2)

    # Get available options
    meal_plans = _get_available_meal_plans(driver)
    logger.info(f"  Meal plans: {[m['text'] for m in meal_plans]}")

    packages = []

    for meal in meal_plans:
        # Select this meal plan
        try:
            _select_option(driver, meal)
            random_delay(1, 2)
        except Exception as e:
            logger.warning(f"  Failed to select meal plan '{meal['text']}': {e}")
            continue

        # After selecting meal plan, get airports
        airports = _get_available_airports(driver)
        logger.info(f"  Airports for meal '{meal['text']}': {[a['text'] for a in airports]}")

        for airport in airports:
            # Select this airport
            try:
                _select_option(driver, airport)
                random_delay(2, 4)
            except Exception as e:
                logger.warning(f"  Failed to select airport '{airport['text']}': {e}")
                continue

            # Wait for page to update with new prices
            random_delay(1, 2)

            # Extract rooms and find cheapest
            rooms = _extract_room_options(driver)
            cheapest_room = None
            if rooms:
                priced_rooms = [r for r in rooms if r.get("price") is not None]
                if priced_rooms:
                    cheapest_room = min(priced_rooms, key=lambda r: r["price"])
                else:
                    cheapest_room = rooms[0]  # Take first if no prices found

            # Extract flights and find cheapest
            flights = _extract_flight_options(driver)
            cheapest_flight = None
            if flights:
                priced_flights = [f for f in flights if f.get("price") is not None]
                if priced_flights:
                    cheapest_flight = min(priced_flights, key=lambda f: f["price"])
                else:
                    cheapest_flight = flights[0]

            # Extract overall price and tax
            price_pp, tourist_tax = _extract_price_and_tax(driver)

            package = {
                "hotel_name": hotel["name"],
                "hotel_url": hotel["url"],
                "hotel_location": hotel.get("location", ""),
                "hotel_rating": hotel.get("rating", ""),
                "room_name": cheapest_room["name"] if cheapest_room else "N/A",
                "meal_plan": meal["text"],
                "duration_days": 8,
                "duration_nights": 7,
                "departure_airport": airport["text"],
                "flight_departure_time": cheapest_flight.get("departure_time", "N/A") if cheapest_flight else "N/A",
                "flight_arrival_time": cheapest_flight.get("arrival_time", "N/A") if cheapest_flight else "N/A",
                "flight_airline": cheapest_flight.get("airline", "N/A") if cheapest_flight else "N/A",
                "final_price_per_person": price_pp,
                "tourist_tax": tourist_tax,
                "currency": "EUR",
            }

            packages.append(package)
            logger.info(
                f"  Package: {meal['text']} | {airport['text']} | "
                f"€{price_pp or '?'} pp | room: {package['room_name']}"
            )

    if not packages:
        # If no options found via dropdowns, extract whatever is on the page
        logger.info("  No dropdown combos found, extracting visible data as single package")
        rooms = _extract_room_options(driver)
        flights = _extract_flight_options(driver)
        price_pp, tourist_tax = _extract_price_and_tax(driver)

        cheapest_room = None
        if rooms:
            priced_rooms = [r for r in rooms if r.get("price") is not None]
            cheapest_room = min(priced_rooms, key=lambda r: r["price"]) if priced_rooms else rooms[0]

        cheapest_flight = None
        if flights:
            priced_flights = [f for f in flights if f.get("price") is not None]
            cheapest_flight = min(priced_flights, key=lambda f: f["price"]) if priced_flights else flights[0]

        packages.append({
            "hotel_name": hotel["name"],
            "hotel_url": hotel["url"],
            "hotel_location": hotel.get("location", ""),
            "hotel_rating": hotel.get("rating", ""),
            "room_name": cheapest_room["name"] if cheapest_room else "N/A",
            "meal_plan": "Default",
            "duration_days": 8,
            "duration_nights": 7,
            "departure_airport": "Default",
            "flight_departure_time": cheapest_flight.get("departure_time", "N/A") if cheapest_flight else "N/A",
            "flight_arrival_time": cheapest_flight.get("arrival_time", "N/A") if cheapest_flight else "N/A",
            "flight_airline": cheapest_flight.get("airline", "N/A") if cheapest_flight else "N/A",
            "final_price_per_person": price_pp,
            "tourist_tax": tourist_tax,
            "currency": "EUR",
        })

    logger.info(f"  Total packages for {hotel['name']}: {len(packages)}")
    return packages
