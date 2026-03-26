# TUI.nl Formentera Travel Package Scraper

Scrapes all travel package options from [tui.nl/reizen/spanje/formentera/](https://www.tui.nl/reizen/spanje/formentera/) for Formentera, Spain hotels.

## Architecture

TUI.nl is protected by **Akamai Bot Manager**, which blocks standard HTTP requests and Selenium-based browsers. This scraper bypasses it using a two-layer approach:

1. **Local forwarding proxy** (`local_proxy.py`) — A lightweight TCP proxy running on `localhost:18080` that forwards all traffic to an IPRoyal residential proxy with NL geolocation credentials from `.env`. This gives Chrome a Dutch IP without needing a browser extension for proxy auth.

2. **nodriver (undetected Chrome)** (`proxy_scraper.py`) — An undetected Chrome browser that passes Akamai's JavaScript challenge and TLS fingerprinting, then extracts data from the fully rendered DOM.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the local forwarding proxy (runs in background)
python src/local_proxy.py &

# 3. Run the scraper
python src/proxy_scraper.py
```

Results are saved to `output/tui_formentera_packages.json`.

### Legacy Scrapers

The repository also contains earlier scraper attempts that may be useful as reference or fallback:

```bash
# Selenium-based scraper (blocked by Akamai without proxy)
python src/scraper.py [--headless] [--max-hotels N]

# HTTP scraper using copied browser session headers/cookies
python src/http_scraper.py
```

## .env Configuration

The `.env` file contains IPRoyal residential proxy credentials used by `local_proxy.py`:

```
hostname:
geo.iproyal.com

port:
12321

username:
<your_username>

password:
<your_password>

password_geolocation:
<your_password>_country-nl

scheme:
http
```

The `password_geolocation` field appends `_country-nl` to the base password to route traffic through a Dutch IP, which is required for accessing TUI.nl.

## Output

Results are saved to `output/tui_formentera_packages.json` with the following fields per package:

| Field | Description |
|---|---|
| `hotel_name` | Name of the hotel |
| `hotel_url` | Direct URL to the hotel page |
| `room_name` | Room type for this offer row |
| `meal_plan` | Meal plan / verzorging (e.g. Halfpension, All Inclusive, Logies ontbijt) |
| `duration_days` | Duration in days (8) |
| `duration_nights` | Duration in nights (7) |
| `departure_date` | Departure date shown on the offer |
| `departure_airport` | Departure airport name (e.g. Eindhoven, Rotterdam, Amsterdam, Dusseldorf) |
| `airport_surcharge` | Extra cost per person for this airport vs. the cheapest option |
| `flight_departure_time` | Outbound flight departure time (if shown) |
| `flight_arrival_time` | Outbound flight arrival time (if shown) |
| `flight_airline` | Airline name (if shown) |
| `final_price_per_person` | Final price per person in EUR |
| `tourist_tax` | Tourist tax amount (if shown) |
| `currency` | Currency (EUR) |

## Project Structure

```
├── .env                             # Proxy credentials (not committed)
├── requirements.txt                 # Python dependencies
├── README.md
├── src/
│   ├── proxy_scraper.py             # Main scraper (nodriver + local proxy)
│   ├── local_proxy.py               # Local TCP proxy forwarding to IPRoyal NL
│   ├── scraper.py                   # Legacy Selenium-based scraper
│   ├── http_scraper.py              # Legacy HTTP scraper with copied cookies
│   ├── listing_page.py              # Legacy listing page extraction (Selenium)
│   ├── hotel_page.py                # Legacy hotel page extraction (Selenium)
│   └── utils.py                     # Helpers (logging, delay, retry)
└── output/
    └── tui_formentera_packages.json # Scraper output
```

## How It Works

### Listing Page
1. Opens `https://www.tui.nl/reizen/spanje/formentera/` via nodriver with the NL proxy
2. Waits for Akamai Bot Manager JS challenge to resolve (~3-6s)
3. Accepts the cookie consent banner
4. Extracts hotel links using the `.sr-item-hdr` CSS class on hotel card headers
5. Handles pagination (page 1, page 2, etc.)

### Hotel Pages
For each hotel, the scraper:
1. Navigates to the hotel detail URL
2. Clicks "Prijzen & boeken" to load the pricing section
3. Reads all `.pricebox` elements (each represents a room/offer row)
4. For each pricebox, extracts:
   - **Meal plan** from `.board`
   - **Room name** from `.hdr-room`
   - **Departure date** and **duration** from `.date` and `.duration-day`
   - **Price** from `.price-detail` (parsing "Prijs per persoon vanaf X")
5. Iterates airport tabs (`.airports button`) — clicking each one and reading the updated price
6. Expands "Bekijk meer vertrekluchthavens" if available to reveal additional airports

## Assumptions

- **Duration**: Fixed at 8 days / 7 nights as specified
- **Cheapest selection**: Each pricebox row on TUI represents a specific room type; the scraper captures all visible rows
- **Browser**: Requires Google Chrome installed on the system
- **Language**: The scraper expects the Dutch (NL) version of the TUI website
- **Proxy**: Requires a working IPRoyal residential proxy account with NL geolocation

## Limitations

- **Flight details**: TUI does not show flight times or airline on the hotel pricing page; these only appear in the booking flow
- **Tourist tax**: Not displayed at the pricing overview level
- **Availability**: Some hotels show "Bekijk beschikbaarheid" instead of pricing when no dates are available — these return minimal data
- **Dynamic selectors**: TUI.nl may change its CSS classes (`.sr-item-hdr`, `.pricebox`, `.board`, `.airports`, `.price-detail`) at any time
- **Anti-bot protection**: While nodriver with a residential NL proxy currently bypasses Akamai, this may stop working if Akamai updates its detection
- **Rate**: A full scrape of all 11 hotels takes ~7 minutes due to polite delays between requests

## Scraping Etiquette

- 2-5 second delays between page loads
- Sequential requests (no parallel browser sessions)
- Residential proxy for realistic traffic patterns
- Respects page load times before extracting data
