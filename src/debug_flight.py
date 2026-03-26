"""
Debug script: investigate how to trigger the flight choice popup on a TUI hotel page.
Tries multiple approaches to find table.prices and data-tui-tooltip-element.
"""
import asyncio
import json
import nodriver as uc

LOCAL_PROXY = "http://127.0.0.1:18080"
TEST_HOTEL = "https://www.tui.nl/riu-palace-la-mola-50914921/"


async def safe_eval(page, js_code):
    try:
        result = await page.evaluate(js_code)
        if isinstance(result, str):
            return json.loads(result)
        return result
    except Exception as e:
        print(f"  JS error: {e}")
        return None


async def main():
    browser = await uc.start(
        browser_args=[
            f"--proxy-server={LOCAL_PROXY}",
            "--lang=nl-NL",
            "--window-size=1920,1080",
        ]
    )

    try:
        page = await browser.get(TEST_HOTEL)
        await page.sleep(8)

        # Accept cookies
        try:
            btn = await page.find("Accepteer cookies", best_match=True)
            if btn:
                await btn.click()
                await page.sleep(2)
        except:
            pass

        print("\n=== Step 1: Click 'Prijzen & boeken' ===")
        try:
            tab = await page.find("Prijzen & boeken", best_match=True)
            if tab:
                await tab.click()
                await page.sleep(3)
                print("  Clicked 'Prijzen & boeken'")
        except:
            pass

        # Check what's on page now
        info = await safe_eval(page, '''
            JSON.stringify({
                tablePrices: document.querySelectorAll('table.prices').length,
                tooltips: document.querySelectorAll('[data-tui-tooltip-element]').length,
                pricegrid: document.querySelector('#pricegrid') ? document.querySelector('#pricegrid').innerHTML.substring(0, 500) : 'NOT FOUND',
                priceboxes: document.querySelectorAll('.pricebox').length,
                allTables: document.querySelectorAll('table').length,
                allButtons: document.querySelectorAll('button').length,
            })
        ''')
        print(f"  After Prijzen & boeken: {json.dumps(info, indent=2)}")

        print("\n=== Step 2: Click 'Alle prijzen' ===")
        try:
            btn = await page.find("Alle prijzen", best_match=True)
            if btn:
                await btn.click()
                await page.sleep(5)
                print("  Clicked 'Alle prijzen'")
        except Exception as e:
            print(f"  No 'Alle prijzen': {e}")

        # Wait and check
        for i in range(5):
            await page.sleep(3)
            info = await safe_eval(page, '''
                JSON.stringify({
                    tablePrices: document.querySelectorAll('table.prices').length,
                    tooltips: document.querySelectorAll('[data-tui-tooltip-element]').length,
                    pricegridLen: document.querySelector('#pricegrid') ? document.querySelector('#pricegrid').innerHTML.length : 0,
                    allTables: document.querySelectorAll('table').length,
                })
            ''')
            print(f"  Wait {(i+1)*3}s: {info}")
            if info and (info.get('tablePrices', 0) > 0 or info.get('tooltips', 0) > 0):
                break

        print("\n=== Step 3: Try clicking on pricebox price to open detail ===")
        # Maybe clicking the price itself opens flight options
        click_result = await safe_eval(page, '''
            JSON.stringify((() => {
                let pb = document.querySelector('.pricebox');
                if (!pb) return {error: 'no pricebox'};

                // Find any clickable price-like element
                let clickable = pb.querySelector('.pricelabel a, .price a, a.price, .price-detail a, .cta, a[href*="boek"], button[class*="book"], .ontdek, a[class*="ontdek"]');
                if (clickable) {
                    return {found: clickable.tagName + '.' + clickable.className, href: clickable.href || '', text: clickable.textContent.trim().substring(0, 80)};
                }

                // Just list all <a> and <button> inside pricebox
                let elements = [];
                pb.querySelectorAll('a, button').forEach(el => {
                    elements.push({tag: el.tagName, class: el.className, href: el.href || '', text: el.textContent.trim().substring(0, 60)});
                });
                return {clickableElements: elements};
            })())
        ''')
        print(f"  Pricebox clickables: {json.dumps(click_result, indent=2)}")

        # Try clicking the "Ontdek" or booking link
        print("\n=== Step 4: Navigate to booking page via Ontdek/Book link ===")
        booking_url = await safe_eval(page, '''
            JSON.stringify((() => {
                // Find first booking/ontdek link on the page near pricing
                let links = document.querySelectorAll('a');
                for (let a of links) {
                    let text = a.textContent.trim().toLowerCase();
                    let href = a.href || '';
                    if ((text.includes('ontdek') || text.includes('boek') || text.includes('selecteer') || href.includes('/book')) && href.includes('tui.nl')) {
                        return {href: href, text: a.textContent.trim().substring(0, 80)};
                    }
                }
                // Look for any CTA button
                let ctas = document.querySelectorAll('.cta, [class*="cta"], [class*="book"]');
                for (let c of ctas) {
                    let a = c.closest('a') || c.querySelector('a');
                    if (a && a.href) return {href: a.href, text: a.textContent.trim().substring(0, 80)};
                }
                return null;
            })())
        ''')
        print(f"  Booking link: {booking_url}")

        if booking_url and booking_url.get("href"):
            print(f"\n=== Step 5: Navigate to booking URL ===")
            await page.evaluate(f'window.location.href = "{booking_url["href"]}"')
            await page.sleep(8)

            # Check for table.prices and tooltips on booking page
            for i in range(5):
                await page.sleep(3)
                info = await safe_eval(page, '''
                    JSON.stringify({
                        url: window.location.href,
                        title: document.title,
                        tablePrices: document.querySelectorAll('table.prices').length,
                        tooltips: document.querySelectorAll('[data-tui-tooltip-element]').length,
                        flightchoice: document.querySelectorAll('.ovl-flightchoice, [class*="flightchoice"]').length,
                        allTables: document.querySelectorAll('table').length,
                        pricegridLen: document.querySelector('#pricegrid') ? document.querySelector('#pricegrid').innerHTML.length : 0,
                        bodyLen: document.body ? document.body.innerHTML.length : 0,
                    })
                ''')
                print(f"  Booking page wait {(i+1)*3}s: {info}")
                if info and (info.get('tablePrices', 0) > 0 or info.get('tooltips', 0) > 0):
                    break

            # Dump HTML snippet around any table
            if info and info.get('allTables', 0) > 0:
                tables = await safe_eval(page, '''
                    JSON.stringify((() => {
                        let result = [];
                        document.querySelectorAll('table').forEach((t, i) => {
                            result.push({
                                index: i,
                                className: t.className,
                                id: t.id,
                                parentClass: t.parentElement ? t.parentElement.className : '',
                                outerHTML: t.outerHTML.substring(0, 500)
                            });
                        });
                        return result;
                    })())
                ''')
                print(f"\n  Tables on booking page:")
                if tables:
                    for t in tables[:5]:
                        print(f"    Table {t['index']}: class='{t['className']}' id='{t['id']}' parent='{t['parentClass']}'")
                        print(f"      HTML: {t['outerHTML'][:200]}")

        # Alternative: Try scrolling down to trigger lazy-loaded price grid
        print("\n=== Step 6: Scroll to bottom and check for lazy-loaded elements ===")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.sleep(5)
        info = await safe_eval(page, '''
            JSON.stringify({
                tablePrices: document.querySelectorAll('table.prices').length,
                tooltips: document.querySelectorAll('[data-tui-tooltip-element]').length,
                pricegridLen: document.querySelector('#pricegrid') ? document.querySelector('#pricegrid').innerHTML.length : 0,
            })
        ''')
        print(f"  After scroll: {info}")

        # Try clicking directly on a price amount
        print("\n=== Step 7: Click directly on price amount text ===")
        await page.evaluate("window.scrollTo(0, 0)")
        await page.sleep(1)
        # Navigate back to hotel page
        await page.evaluate(f'window.location.href = "{TEST_HOTEL}"')
        await page.sleep(8)
        try:
            tab = await page.find("Prijzen & boeken", best_match=True)
            if tab:
                await tab.click()
                await page.sleep(3)
        except:
            pass

        # Click on the price number itself
        price_click = await safe_eval(page, '''
            JSON.stringify((() => {
                let priceEls = document.querySelectorAll('.pricelabel, .price, .price-detail');
                for (let el of priceEls) {
                    // Find a span or element with a number
                    let spans = el.querySelectorAll('span, strong, b');
                    for (let s of spans) {
                        if (s.textContent.match(/\\d{3,}/)) {
                            s.click();
                            return {clicked: true, text: s.textContent.trim().substring(0, 50)};
                        }
                    }
                    if (el.textContent.match(/\\d{3,}/)) {
                        el.click();
                        return {clicked: true, text: el.textContent.trim().substring(0, 50)};
                    }
                }
                return {clicked: false};
            })())
        ''')
        print(f"  Price click: {price_click}")
        await page.sleep(3)

        # Check for popup
        popup_check = await safe_eval(page, '''
            JSON.stringify({
                tablePrices: document.querySelectorAll('table.prices').length,
                tooltips: document.querySelectorAll('[data-tui-tooltip-element]').length,
                flightchoice: document.querySelectorAll('.ovl-flightchoice, [class*="flightchoice"], [class*="flight"]').length,
                overlays: document.querySelectorAll('.popup, .overlay, [class*="overlay"], [class*="popup"], [class*="modal"]').length,
            })
        ''')
        print(f"  After price click: {popup_check}")

        # Final: dump all unique class names that contain 'price' or 'flight'
        print("\n=== Step 8: All price/flight related classes on page ===")
        classes = await safe_eval(page, '''
            JSON.stringify((() => {
                let allClasses = new Set();
                document.querySelectorAll('*').forEach(el => {
                    el.classList.forEach(c => {
                        if (c.toLowerCase().match(/price|flight|tooltip|popup|overlay|modal|book|grid/)) {
                            allClasses.add(c);
                        }
                    });
                });
                return Array.from(allClasses).sort();
            })())
        ''')
        print(f"  Matching classes: {classes}")

        # Also check data attributes
        data_attrs = await safe_eval(page, '''
            JSON.stringify((() => {
                let attrs = new Set();
                document.querySelectorAll('*').forEach(el => {
                    for (let a of el.attributes) {
                        if (a.name.startsWith('data-tui')) {
                            attrs.add(a.name + '=' + a.value.substring(0, 30));
                        }
                    }
                });
                return Array.from(attrs).sort();
            })())
        ''')
        print(f"  data-tui-* attributes: {data_attrs}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
