"""
TUI.nl Formentera Scraper — nodriver + local NL proxy
======================================================
Bypasses Akamai Bot Manager using:
  1. Local forwarding proxy (local_proxy.py) -> iproyal NL geo
  2. nodriver (undetected Chrome) for JS rendering

Prerequisites:
  - Run `python src/local_proxy.py` first (background)
  - Then `python src/proxy_scraper.py`
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import nodriver as uc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import logger

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "tui_formentera_packages.json")
LISTING_URL = "https://www.tui.nl/reizen/spanje/formentera/"
LOCAL_PROXY = "http://127.0.0.1:18080"


async def safe_eval(page, js_code):
    """Evaluate JS and return parsed result, or None on error."""
    try:
        result = await page.evaluate(js_code)
        if isinstance(result, str):
            return json.loads(result)
        return result
    except Exception as e:
        logger.warning(f"JS eval error: {e}")
        return None


async def accept_cookies(page):
    """Dismiss cookie consent banner."""
    try:
        btn = await page.find("Accepteer cookies", best_match=True)
        if btn:
            await btn.click()
            logger.info("Accepted cookies")
            await page.sleep(2)
            return
    except Exception:
        pass
    try:
        btn = await page.find("Akkoord", best_match=True)
        if btn:
            await btn.click()
            logger.info("Accepted cookies via Akkoord")
            await page.sleep(2)
            return
    except Exception:
        pass
    logger.info("No cookie banner or already accepted")


async def wait_for_page(page, timeout=30):
    """Wait until TUI page loads past Akamai challenge."""
    for i in range(timeout // 3):
        await page.sleep(3)
        title_el = await page.query_selector("title")
        title = title_el.text if title_el else ""
        if "formentera" in title.lower() or "hotel" in title.lower() or "tui" in title.lower():
            logger.info(f"Page loaded at {i*3}s: {title}")
            return True
        content = await page.get_content()
        if "Access Denied" in content:
            logger.error("Access Denied by Akamai WAF")
            return False
    logger.warning("Timeout waiting for page")
    return False


async def extract_hotel_links(page):
    """Extract hotel links from the listing page. Handles pagination."""
    all_hotels = []

    for page_num in range(1, 10):  # Max 10 pages
        if page_num > 1:
            url = f"{LISTING_URL}?page={page_num}"
            logger.info(f"Loading page {page_num}: {url}")
            await page.evaluate(f'window.location.href = "{url}"')
            await page.sleep(5)
            if not await wait_for_page(page, timeout=20):
                break

        await page.sleep(3)

        data = await safe_eval(page, '''
            JSON.stringify((() => {
                let hotels = [];
                let seen = new Set();

                // Primary: use sr-item-hdr class (hotel card headers)
                document.querySelectorAll('.sr-item-hdr').forEach(hdr => {
                    let link = hdr.closest('a') || hdr.querySelector('a');
                    if (!link) {
                        let parent = hdr.parentElement;
                        while (parent && parent.tagName !== 'A') parent = parent.parentElement;
                        if (parent) link = parent;
                    }
                    let href = link ? link.href : '';
                    // Get clean hotel name (first line only)
                    let name = hdr.textContent.trim().split('\\n')[0].trim();
                    if (href && !seen.has(href)) {
                        seen.add(href);
                        hotels.push({name: name, url: href});
                    }
                });

                // Fallback: hotel links with numeric IDs
                if (hotels.length === 0) {
                    document.querySelectorAll('a').forEach(a => {
                        let href = a.href;
                        if (href && href.match(/tui\\.nl\\/[\\w-]+-\\d{5,}\\/?$/) && !seen.has(href)) {
                            seen.add(href);
                            let name = a.textContent.trim();
                            if (name.length > 3 && name.length < 80 && !name.match(/^\\d/) && !name.includes('Ontdek') && !name.includes('Bekijk')) {
                                hotels.push({name: name, url: href});
                            }
                        }
                    });
                }

                // Deduplicate by URL
                let unique = [];
                let seenUrls = new Set();
                for (let h of hotels) {
                    if (!seenUrls.has(h.url)) {
                        seenUrls.add(h.url);
                        unique.push(h);
                    }
                }

                // Check for next page
                let hasNext = false;
                document.querySelectorAll('a').forEach(a => {
                    if (a.href && a.href.includes('page=') && a.textContent.trim().match(/^\\d+$/)) {
                        let pNum = parseInt(a.textContent.trim());
                        if (pNum > parseInt(new URLSearchParams(window.location.search).get('page') || '1')) {
                            hasNext = true;
                        }
                    }
                });

                return {hotels: unique, hasNext: hasNext};
            })())
        ''')

        if not data or not data.get("hotels"):
            break

        new_hotels = data["hotels"]
        all_hotels.extend(new_hotels)
        logger.info(f"Page {page_num}: found {len(new_hotels)} hotels (total: {len(all_hotels)})")

        if not data.get("hasNext"):
            break

        await page.sleep(2)

    # Deduplicate across pages
    seen = set()
    unique = []
    for h in all_hotels:
        if h["url"] not in seen:
            seen.add(h["url"])
            unique.append(h)

    return unique


async def extract_flight_data(page, pricebox_index):
    """
    Extract flight data from ovl-flightchoice popup.
    Proven approach from debug testing:
      1. Find SPAN.price-det[data-tui-tooltip-element] inside the pricebox
      2. scrollIntoView + click it
      3. Wait up to 24s for .ovl-flightchoice popup (AJAX takes ~6-8s)
      4. Parse structured <tr> rows with radio inputs (airline, times, etc.)
      5. Close popup via .close button
    """
    # Step 1: Click the tooltip element inside this pricebox
    clicked = await safe_eval(page, f'''
        JSON.stringify((() => {{
            let boxes = document.querySelectorAll('.pricebox');
            let box = boxes[{pricebox_index}];
            if (!box) return {{clicked: false, reason: 'no pricebox at index {pricebox_index}'}};

            let btn = box.querySelector('[data-tui-tooltip-element]');
            if (!btn) {{
                // Fallback: try any tooltip on page at this index
                let all = document.querySelectorAll('[data-tui-tooltip-element]');
                if (all.length > 0) btn = all[Math.min({pricebox_index}, all.length - 1)];
            }}
            if (!btn) return {{clicked: false, reason: 'no tooltip found', total: document.querySelectorAll('[data-tui-tooltip-element]').length}};

            btn.scrollIntoView({{block: 'center'}});
            btn.click();
            return {{clicked: true, target: btn.getAttribute('data-tui-tooltip-element')}};
        }})())
    ''')

    if not clicked or not clicked.get("clicked"):
        logger.info(f"    No tooltip for pricebox #{pricebox_index}: {clicked}")
        return None

    logger.info(f"    Clicked tooltip -> {clicked.get('target', '?')}")

    # Step 2: Wait for ovl-flightchoice popup (AJAX, typically 6-8s)
    flight_data = None
    for wait_i in range(12):
        await page.sleep(2)
        flight_data = await safe_eval(page, '''
            JSON.stringify((() => {
                let popup = document.querySelector('.ovl-flightchoice.popup')
                           || document.querySelector('.ovl-flightchoice')
                           || document.querySelector('[class*="ovl-flightchoice"]');
                if (!popup) {
                    let form = document.querySelector('form[action*="flightchoice"]');
                    if (form) popup = form.closest('[class*="ovl"]') || form;
                }
                if (!popup || popup.offsetHeight === 0) return null;

                // Parse structured flight rows from the popup tables
                // Popup has sections: .fc-cnt.dep (outbound) and .fc-cnt.ret (return)
                let outbound = [];
                let inbound = [];

                let sections = popup.querySelectorAll('.fc-cnt');
                for (let section of sections) {
                    let isDep = section.classList.contains('dep');
                    let target = isDep ? outbound : inbound;

                    let route = '';
                    let hdr = section.querySelector('.fc-hdr, .ic-flight');
                    if (hdr) route = hdr.textContent.trim().replace(/\\s+/g, ' ');

                    section.querySelectorAll('tr').forEach(row => {
                        let input = row.querySelector('input[type="radio"]');
                        if (!input) return;

                        let label = row.querySelector('label');
                        let airline = label ? label.textContent.trim() : '';
                        if (!airline) {
                            let carrier = input.getAttribute('data-tui-carrier');
                            if (carrier) airline = carrier.charAt(0).toUpperCase() + carrier.slice(1);
                        }

                        let tds = row.querySelectorAll('td');
                        let flightNo = tds.length > 1 ? tds[1].textContent.trim() : '';
                        let flightClass = tds.length > 2 ? tds[2].textContent.trim() : '';
                        let timeRange = tds.length > 3 ? tds[3].textContent.trim() : '';
                        let duration = tds.length > 4 ? tds[4].textContent.trim() : '';
                        let surcharge = tds.length > 5 ? tds[5].textContent.trim() : '';

                        let times = timeRange.match(/(\\d{1,2}:\\d{2})/g) || [];
                        let isActive = row.classList.contains('active') || input.checked;

                        target.push({
                            airline, flightNo, flightClass,
                            dep: times[0] || '', arr: times[1] || '',
                            duration, surcharge, isActive, route
                        });
                    });
                }

                // Flat fallback if no .fc-cnt sections found
                if (outbound.length === 0 && inbound.length === 0) {
                    popup.querySelectorAll('tr').forEach(row => {
                        let input = row.querySelector('input[type="radio"]');
                        if (!input) return;
                        let label = row.querySelector('label');
                        let tds = row.querySelectorAll('td');
                        let timeRange = tds.length > 3 ? tds[3].textContent.trim() : '';
                        let times = timeRange.match(/(\\d{1,2}:\\d{2})/g) || [];
                        outbound.push({
                            airline: label ? label.textContent.trim() : '',
                            flightNo: tds.length > 1 ? tds[1].textContent.trim() : '',
                            dep: times[0] || '', arr: times[1] || '',
                            isActive: row.classList.contains('active') || input.checked,
                        });
                    });
                }

                return {found: true, outbound, inbound};
            })())
        ''')

        if flight_data and flight_data.get("found"):
            n_out = len(flight_data.get("outbound", []))
            n_in = len(flight_data.get("inbound", []))
            logger.info(f"    Flight popup found: {n_out} outbound, {n_in} return flights")
            break

    # Step 3: Close the popup
    await safe_eval(page, '''
        (() => {
            let btn = document.querySelector('.ovl-flightchoice .close')
                   || document.querySelector('.ovl-flightchoice [data-tui-close-popup]');
            if (btn) { btn.click(); return; }
            document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', keyCode: 27}));
        })()
    ''')
    await page.sleep(1)

    return flight_data


def parse_flight_data(flight_data):
    """Pick active (cheapest) outbound flight -> {dep, arr, airline}."""
    if not flight_data or not flight_data.get("found"):
        return {}

    for f in flight_data.get("outbound", []):
        if f.get("isActive"):
            return {"dep": f.get("dep", ""), "arr": f.get("arr", ""), "airline": f.get("airline", "")}

    flights = flight_data.get("outbound", [])
    if flights:
        return {"dep": flights[0].get("dep", ""), "arr": flights[0].get("arr", ""), "airline": flights[0].get("airline", "")}

    return {}


async def scrape_hotel(browser, hotel):
    """
    Scrape a single hotel page. Extracts all .pricebox entries,
    then for each pricebox clicks each airport tab to get per-airport pricing.
    Also attempts to extract flight data from the ovl-flightchoice popup.
    """
    url = hotel["url"]
    logger.info(f"Scraping: {hotel['name']} — {url}")

    page = await browser.get(url)
    await page.sleep(5)

    # Wait for content
    for _ in range(10):
        content = await page.get_content()
        if len(content) > 5000:
            break
        await page.sleep(2)
    await page.sleep(3)

    # Accept cookies
    await accept_cookies(page)
    await page.sleep(2)

    # Click 'Prijzen & boeken' tab to load the pricing section
    try:
        tab = await page.find("Prijzen & boeken", best_match=True)
        if tab:
            await tab.click()
            await page.sleep(3)
    except Exception:
        pass

    # Try clicking "Alle prijzen" to load the full price grid with table.prices
    try:
        alle_btn = await page.find("Alle prijzen", best_match=True)
        if alle_btn:
            await alle_btn.click()
            logger.info("  Clicked 'Alle prijzen' to load price grid")
            await page.sleep(5)

            # Wait for table.prices to appear
            for _ in range(10):
                has_table = await safe_eval(page, '''
                    JSON.stringify({
                        tablePrices: document.querySelectorAll('table.prices').length,
                        tooltips: document.querySelectorAll('[data-tui-tooltip-element]').length,
                        pricegrid: document.querySelector('#pricegrid') ? document.querySelector('#pricegrid').innerHTML.length : 0
                    })
                ''')
                if has_table and (has_table.get("tablePrices", 0) > 0 or has_table.get("tooltips", 0) > 0):
                    logger.info(f"  Price grid loaded: {has_table}")
                    break
                if has_table and has_table.get("pricegrid", 0) > 100:
                    logger.info(f"  Pricegrid content loaded ({has_table.get('pricegrid')} chars)")
                    break
                await page.sleep(2)
    except Exception:
        pass

    # Extract ALL data from every .pricebox, iterating airport buttons
    packages_data = await safe_eval(page, '''
        JSON.stringify((() => {
            function parsePrice(text) {
                if (!text) return null;
                let cleaned = text.replace(/[^0-9,.]/g, '');
                if (!cleaned) return null;
                // Handle "858,00" or "1.234,56"
                if (cleaned.includes(',')) {
                    cleaned = cleaned.replace(/\\./g, '').replace(',', '.');
                }
                let val = parseFloat(cleaned);
                return (val && val > 10) ? val : null;
            }

            let hotelName = '';
            let h1 = document.querySelector('h1');
            if (h1) hotelName = h1.textContent.trim();

            // Room names from .hdr-room
            let roomNames = [];
            document.querySelectorAll('.hdr-room').forEach(el => {
                let firstLine = el.textContent.trim().split('\\n')[0].trim();
                if (firstLine) roomNames.push(firstLine);
            });

            // Extract all priceboxes
            let priceboxes = [];
            document.querySelectorAll('.pricebox').forEach((box, idx) => {
                let date = '';
                let dateEl = box.querySelector('.date, .dys-nghts');
                if (dateEl) date = dateEl.textContent.trim();

                let duration = '';
                let durEl = box.querySelector('.duration-day');
                if (durEl) duration = durEl.textContent.trim();

                let board = '';
                let boardEl = box.querySelector('.board');
                if (boardEl) board = boardEl.textContent.trim();

                // Airports: get all airport buttons
                let airportBtns = [];
                box.querySelectorAll('.airports button').forEach(btn => {
                    let text = btn.textContent.trim().replace(/\\n/g, ' ').replace(/\\s+/g, ' ');
                    let isActive = btn.classList.contains('active');
                    airportBtns.push({text, isActive, index: airportBtns.length});
                });

                // "Bekijk meer vertrekluchthavens" link
                let moreAirports = box.querySelector('.airports a, .airports [class*="meer"]');
                let hasMoreAirports = !!moreAirports;

                // Price details
                let priceDetails = [];
                box.querySelectorAll('.price-detail, .price-det').forEach(pd => {
                    let text = pd.innerText.trim();
                    if (text) priceDetails.push(text);
                });

                // Main price from pricelabel
                let mainPrice = null;
                let priceLabel = box.querySelector('.pricelabel, .price');
                if (priceLabel) mainPrice = parsePrice(priceLabel.textContent);

                // Detailed price from price-detail
                let detailedPrice = null;
                for (let pd of priceDetails) {
                    let m = pd.match(/Prijs per persoon\\s+(?:vanaf\\s+)?(\\d[\\d.,]*)/);
                    if (m) {
                        detailedPrice = parsePrice(m[1]);
                        break;
                    }
                }

                // Tourist tax
                let touristTax = null;
                for (let pd of priceDetails) {
                    if (pd.toLowerCase().includes('toeristenbelasting')) {
                        let m = pd.match(/toeristenbelasting[\\s:]*(\\d[\\d.,]*)/i);
                        if (m) touristTax = parsePrice(m[1]);
                    }
                }

                // Transfer info
                let transfer = '';
                let transferEl = box.querySelector('.transfer, [class*="transfer"]');
                if (transferEl) transfer = transferEl.textContent.trim();

                priceboxes.push({
                    index: idx,
                    date,
                    duration,
                    board,
                    airports: airportBtns,
                    hasMoreAirports,
                    mainPrice: detailedPrice || mainPrice,
                    touristTax,
                    priceDetails,
                    transfer,
                    roomName: roomNames[idx] || (roomNames[0] || 'N/A')
                });
            });

            return {hotelName, roomNames, priceboxes};
        })())
    ''')

    if not packages_data:
        logger.warning(f"  Could not extract data from {hotel['name']}")
        return []

    hotel_name = packages_data.get("hotelName") or hotel["name"]
    room_names = packages_data.get("roomNames", [])
    priceboxes = packages_data.get("priceboxes", [])

    logger.info(f"  Hotel: {hotel_name}")
    logger.info(f"  Rooms: {room_names}")
    logger.info(f"  Priceboxes: {len(priceboxes)}")

    packages = []

    for pb in priceboxes:
        logger.info(f"  Pricebox #{pb['index']}: {pb['board']} | {pb['date']} | {pb['duration']}")

        airport_buttons = pb.get("airports", [])
        if not airport_buttons:
            airport_buttons = [{"text": "Default", "index": 0, "isActive": True}]

        # If there's a "Bekijk meer vertrekluchthavens" expand it first
        if pb.get("hasMoreAirports"):
            await safe_eval(page, f'''
                (() => {{
                    let boxes = document.querySelectorAll('.pricebox');
                    let box = boxes[{pb["index"]}];
                    if (box) {{
                        let more = box.querySelector('.airports a, .airports [class*="meer"], .airports .more');
                        if (more) more.click();
                    }}
                }})()
            ''')
            await page.sleep(2)

            # Re-read airports after expanding
            expanded = await safe_eval(page, f'''
                JSON.stringify((() => {{
                    let boxes = document.querySelectorAll('.pricebox');
                    let box = boxes[{pb["index"]}];
                    if (!box) return [];
                    let btns = [];
                    box.querySelectorAll('.airports button').forEach((btn, i) => {{
                        btns.push({{text: btn.textContent.trim().replace(/\\n/g, ' ').replace(/\\s+/g, ' '), isActive: btn.classList.contains('active'), index: i}});
                    }});
                    return btns;
                }})())
            ''')
            if expanded:
                airport_buttons = expanded
                logger.info(f"    Expanded airports: {[a['text'] for a in airport_buttons]}")

        # Extract flight data ONCE per pricebox (before airport loop)
        flight_info = {}
        raw_flight = await extract_flight_data(page, pb["index"])
        if raw_flight:
            flight_info = parse_flight_data(raw_flight)
            if flight_info.get("dep"):
                logger.info(f"    Flight: {flight_info['airline']} {flight_info['dep']}->{flight_info['arr']}")

        for ap in airport_buttons:
            # Click this airport button
            ap_name = ap["text"].split("+")[0].strip()  # "Vanaf Rotterdam + 7,- p.p." -> "Vanaf Rotterdam"
            ap_extra_cost = 0
            if "+" in ap["text"]:
                import re
                m = re.search(r'\+\s*([\d.,]+)', ap["text"])
                if m:
                    cost_str = m.group(1).replace(".", "").replace(",", ".")
                    try:
                        ap_extra_cost = float(cost_str)
                    except ValueError:
                        pass

            if not ap.get("isActive"):
                await safe_eval(page, f'''
                    (() => {{
                        let boxes = document.querySelectorAll('.pricebox');
                        let box = boxes[{pb["index"]}];
                        if (box) {{
                            let btns = box.querySelectorAll('.airports button');
                            if (btns[{ap["index"]}]) btns[{ap["index"]}].click();
                        }}
                    }})()
                ''')
                await page.sleep(2)

            # Extract price after clicking airport
            price_data = await safe_eval(page, f'''
                JSON.stringify((() => {{
                    function parsePrice(text) {{
                        if (!text) return null;
                        let cleaned = text.replace(/[^0-9,.]/g, '');
                        if (!cleaned) return null;
                        if (cleaned.includes(',')) cleaned = cleaned.replace(/\\./g, '').replace(',', '.');
                        let val = parseFloat(cleaned);
                        return (val && val > 10) ? val : null;
                    }}
                    let boxes = document.querySelectorAll('.pricebox');
                    let box = boxes[{pb["index"]}];
                    if (!box) return {{}};

                    let mainPrice = null;
                    let priceDetails = box.querySelectorAll('.price-detail, .price-det');
                    for (let pd of priceDetails) {{
                        let text = pd.innerText;
                        let m = text.match(/Prijs per persoon\\s+(?:vanaf\\s+)?(\\d[\\d.,]*)/);
                        if (m) {{ mainPrice = parsePrice(m[1]); break; }}
                    }}
                    if (!mainPrice) {{
                        let pl = box.querySelector('.pricelabel, .price');
                        if (pl) mainPrice = parsePrice(pl.textContent);
                    }}

                    let touristTax = null;
                    for (let pd of priceDetails) {{
                        let text = pd.innerText.toLowerCase();
                        if (text.includes('toeristenbelasting')) {{
                            let m = text.match(/toeristenbelasting[\\s:]*(\\d[\\d.,]*)/i);
                            if (m) touristTax = parsePrice(m[1]);
                        }}
                    }}

                    return {{mainPrice, touristTax}};
                }})())
            ''')

            if not price_data:
                price_data = {}

            pkg = {
                "hotel_name": hotel_name,
                "hotel_url": url,
                "room_name": pb.get("roomName", "N/A"),
                "meal_plan": pb.get("board", "N/A"),
                "duration_days": 8,
                "duration_nights": 7,
                "departure_date": pb.get("date", ""),
                "departure_airport": ap_name,
                "airport_surcharge": ap_extra_cost,
                "flight_departure_time": flight_info.get("dep") or "N/A",
                "flight_arrival_time": flight_info.get("arr") or "N/A",
                "flight_airline": flight_info.get("airline") or "N/A",
                "final_price_per_person": price_data.get("mainPrice"),
                "tourist_tax": price_data.get("touristTax"),
                "currency": "EUR",
            }
            packages.append(pkg)
            logger.info(
                f"    {pb.get('board')} | {ap_name} | "
                f"€{price_data.get('mainPrice') or '?'} pp"
            )

    logger.info(f"  Total packages for {hotel_name}: {len(packages)}")
    return packages


async def main():
    logger.info("=" * 60)
    logger.info("TUI.nl Formentera Scraper (nodriver + NL proxy)")
    logger.info("=" * 60)

    browser = await uc.start(
        browser_args=[
            f"--proxy-server={LOCAL_PROXY}",
            "--lang=nl-NL",
            "--window-size=1920,1080",
        ]
    )

    try:
        # Verify proxy IP
        logger.info("Checking proxy IP...")
        page = await browser.get("https://httpbin.org/ip")
        await page.sleep(3)
        body = await page.query_selector("body")
        logger.info(f"Proxy IP: {body.text.strip() if body else 'unknown'}")

        # Load listing page
        logger.info(f"Loading {LISTING_URL}")
        page = await browser.get(LISTING_URL)

        if not await wait_for_page(page, timeout=30):
            return

        await page.sleep(5)
        await accept_cookies(page)
        await page.sleep(5)

        # Wait for hotel cards to render
        logger.info("Waiting for hotel cards (.sr-item-hdr) to render...")
        for _ in range(10):
            count = await safe_eval(page, "document.querySelectorAll('.sr-item-hdr').length")
            if count and count > 0:
                logger.info(f"Found {count} .sr-item-hdr elements")
                break
            await page.sleep(2)

        # Extract hotel links (handles pagination)
        hotels = await extract_hotel_links(page)

        if not hotels:
            logger.error("No hotels found!")
            page_text = await safe_eval(page, "JSON.stringify(document.body ? document.body.innerText.substring(0, 3000) : '')")
            logger.info(f"Page text: {page_text}")
            return

        logger.info(f"\nFound {len(hotels)} hotels:")
        for i, h in enumerate(hotels, 1):
            logger.info(f"  {i}. {h['name']} — {h['url']}")

        # Scrape each hotel
        all_packages = []
        for i, hotel in enumerate(hotels, 1):
            logger.info(f"\n{'—' * 50}")
            logger.info(f"Hotel {i}/{len(hotels)}: {hotel['name']}")
            logger.info(f"{'—' * 50}")

            packages = await scrape_hotel(browser, hotel)
            all_packages.extend(packages)
            logger.info(f"Cumulative: {len(all_packages)} packages")
            await page.sleep(2)

        # Save results
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        result = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "source_url": LISTING_URL,
            "total_packages": len(all_packages),
            "packages": all_packages,
        }
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        logger.info("\n" + "=" * 60)
        logger.info("SCRAPING COMPLETE")
        logger.info(f"  Hotels: {len(hotels)}")
        logger.info(f"  Packages: {len(all_packages)}")
        logger.info(f"  Output: {OUTPUT_FILE}")
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.info("Interrupted.")
    except Exception as e:
        logger.error(f"Fatal: {e}", exc_info=True)
    finally:
        browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
