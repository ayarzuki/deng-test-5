"""
TUI.nl HTTP Scraper (Fallback)
==============================
This scraper uses the exact curl headers and cookies provided by the user
to bypass bot protections by mimicking a real browser session.

Usage:
    python src/http_scraper.py
"""

import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from utils import logger, random_delay, safe_text, safe_attribute

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "tui_formentera_packages.json")
LISTING_URL = "https://www.tui.nl/reizen/spanje/formentera/"

# The exact headers and cookies provided by the user
HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-US,en;q=0.9,id;q=0.8,zh-CN;q=0.7,zh;q=0.6',
    'cache-control': 'max-age=0',
    'priority': 'u=0, i',
    'referer': 'https://www.tui.nl/reizen/spanje/formentera/',
    'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'cookie': 'sessionid=18/03/2026-d-7689208570501; 5j2wu=392616bd573837a09face15be862f137; dtCookie=v_4_srv_3_sn_0377683AD473FF60ACEF90C02AA83E47_perc_100000_ol_0_mul_1; tui-persistence=!mIs+viD+SFE0EAMO7v9hQZ6FB9p8ggZRJTi1znnjG4YDw9JUPYT2XjIbBIwHepnI3Ur7AeFxIAvZ1Jw=; ASP.NET_SessionId=lykt2ob5bjms4qjouaj0nha3; TUICPR=F9mwd0iXrN59sr_jU7PY2eF7qsLMl34qNqHeM8uWPu4VXYJA2DaeqcdNAmP1ZhbcekX4H5ffom0scvsuLj8EvQ==; _UserOptions_=; FirstPageSeen=; popup-11032026=shown; PIM-SESSION-ID=hfQ1C4fnjD4qHADX; gig_bootstrap_3_2a2E-f6RXOVzzgC24sReKDz4N8luhuZcrGKAxp5v7W6T3SZEPpsxOhV3C5TXsV3G=login_ver4; _gid=GA1.2.2023572621.1773822221; _gcl_au=1.1.1739741535.1773822221; CookiesAccepted=yes; ab.storage.deviceId.fc34d72a-11c5-4373-b3b6-983f769918c6=%7B%22g%22%3A%225f8ce947-3244-0c67-bd6b-896aa8a58dbc%22%2C%22c%22%3A1773822231165%2C%22l%22%3A1773822231165%7D; check=true; ack=GMPe5d9da21-c991-42dd-9eea-f8c679da17ef; _twpid=tw.1773822265493.899494268214316722; _scid=F4Zb2ecAxMwMBFUEK9w_yx6bF170SdUp; _tt_enable_cookie=1; _ttp=01KM00QM8ZQNPDYE5WCE8M9CHM_.tt.1; _ScCbts=%5B%5D; _pin_unauth=dWlkPU5ETXhNalExTUdFdE5XTm1aQzAwTVROaUxXRXpOR0l0Wm1FMU1qRXpaVEpqWVRjMQ; _fbp=fb.1.1773822269773.33079497916893767; _sctr=1%7C1773766800000; QuantumMetricEnabled=true; QuantumMetricUserID=6c4fa76356ce59cc9db4bdf77fc88e97; AMCVS_41E27DA552A6473A0A490D4D%40AdobeOrg=1; s_cc=true; P_1008=1008D_v2; kndctr_41E27DA552A6473A0A490D4D_AdobeOrg_cluster=irl1; sessionid=18/03/2026-d-9692023317083; _TravelParty=P|1996-03-20:n:119b1558-6749-489f-9611-634f637de299#P|1996-03-20:n:9af7b1e1-430f-4dec-b0ed-c6bac669e331#IOR|y#TSIOR|y#TPC|y; s_sq=%5B%5BB%5D%5D; mboxEdgeCluster=38; QuantumMetricSessionID=57d1298d504e96c32df2a2305cde122b; bm_ss=ab8e18ef4e; AMCV_41E27DA552A6473A0A490D4D%40AdobeOrg=-1712354808%7CMCIDTS%7C20531%7CvVersion%7C4.3.0%7CMCMID%7C08463219388062873560923360322998490866%7CMCAID%7CNONE%7CMCOPTOUT-1773844764s%7CNONE%7CMCAAMLH-1774442364%7C3%7CMCAAMB-1774442364%7Cj8Odv6LonN4r3an7LhD3WZrU1bUpAkFkkiY1ncBR96t2PTI; s_inv=7952; bm_mi=01BD1C5A5BACCEE1E8B02BF2F179E98D~YAAQNz7VjMBxwuacAQAAZyb5AB8RQKuS5XKrS6mL81Vs8IPxu504cueJBv4QCNjlW0PcQDnLXveMmk+owtlWwuh5LL/5rRF3tgiPE+dtHPv47N02YbTAx5Fs0n68Rp13Ipy7WyFpS47bluxp0sJUbLmNLd3cpva1IO8EG7rfT4tjm50U8Dm3BBqImxBvBYyOOZu8i8PHiXuco+tRW41SaM30LFXWPstavIk62wQj1bD4HPyYnJhwpn/WhE9EhdLPhnkG85n76UhYXay/CgtFZ8otlG2osHG13P8X9kisdjtF2PIfuTPjGeQXXHdrCXBvGf4+smFiKRUnWJAnmJV+zpbVK/BFpjFhiP6s0WnrOA==~1; _dc_gtm_UA-3046343-1=1; ak_bmsc=AC642DD202FD2D0B970318FC7FDA6421~000000000000000000000000000000~YAAQNz7VjFFzwuacAQAAZzf5AB9PU6lc37y3sH164CxuWpqgWsfrixoXwdMwU1B0ve88q+2rVdLIANG2INSrXi+adskqxehG+IhpaSEPvCO6cIarGUIWUqNFlW5ULNCfPPCOBSKfIMKAD016kBpe7DE5sPmfnhKf0KbBzOuoITFs/XBVgm56HK+LcrrrN05E52YOhh95Pq/MhP3YE5ZYjqY6y9S0Rh1r7oNV/CjVJbskro+ZZMkiwpQv3QowKAgk7C804TIaF3q6Jl5MheTxC+41Kzfe/Kt92GMoHZaKDURlvIt68ErkNdnQjqHgKwiThCU7ZVTx6Oi/w47kt+Vat+VOnnNFNgZv3ao5xau+2nEeXWmoxZ3LNaRwSrEXTA7kT9hD81/lIo1hNc8cU5gg49FLR1ZyaOezOqDmSsjSR4gxixjmIvU4+AaLhhjFSKIBr3s1jrJ0mZ2SGrBCpt7DCJXOTxwlSiS3pWcDoOwMoTupz/6d35LIQgsXeL9u5Uf+VUlE+ND9f6pbwCJ0cW6N/uRfHA==; __gads=ID=05bbbf9a656302ae:T=1773822318:RT=1773837833:S=ALNI_MZx3LMjm0ahWgFyc7MqkacTVoO5yQ; __gpi=UID=00001222f6b6d6ba:T=1773822318:RT=1773837833:S=ALNI_MaJxj30Vs2J1nvgtcm_EWq6TwXIoQ; __eoi=ID=06e53812192024b5:T=1773822318:RT=1773837833:S=AA-AfjbgjsqVsJTyF6cax-jjbwhP; FCCDCF=%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%22368f2735-d553-4856-97bf-4b243cfd546c%5C%22%2C%5B1773822317%2C565000000%5D%5D%22%5D%5D%5D; gpv_Page_URL=%2Freizen%2Fspanje%2Fformentera%2F; s_nr30=1773837839457-Repeat; s_tslv=1773837839473; FCNEC=%5B%5B%22AKsRol-uJAtTMBkW2Y6OwnD-2XN8cKd-KUsPBGKY7ZScvg0YGLlvkx40P8gdjEcUCizcXP6v6R6SKv651SM66aatcWT9zeNMBU1SpnVqn05uZ_AmyRP_qdSTlEmRBkUH3DK3tFLW-vrqErtGrzqnxhYyANIXj0JNSw%3D%3D%22%5D%5D; bm_so=3AEA0B66E092D183E172027119E0B492E09A7D3058395F30B13D2E15D0B800F8~YAAQNz7VjAx8wuacAQAAwJf5AAd2MlYu+OOpaYMddIED7NfCe5yZunX8FY5nQPhqrEi3VfmSlR+ZXWe9qx2GpE9GLkCcvoINt4RDO2eOXEcu3CVDeqjfKKp37H2IaSHClJYECPIpXTLCkvleCOFlW7Ghyq8BmxhRU4oFVpNJUwI+5xjhDMdZ7D+0/RKgyaDVCE0Fsw8FnIH6sE86X44LxceB4kGtyI0mu5i5lViZBEy0bblZW1ipAYKetmgKNTBf4hD3Z8Jmhwi6xVTZc8Gac5e7lRcYE4TjcmBKirL5sp22ptQUlEE4mIdmt8wx7jQRKlyvUfhJrZbIGIqG0v1sMwd1zSrQcip9HpnGySCOATlUKrCSSXRSGaHZC55fdsqjlJ5Ht6+2UecDXr+0GO4hDtXq6dNPjXUE9W8G25URdi3fy+pFsFaYXwzDO79yyZGgK5OS1Ooqjj0IsYo=; bm_lso=3AEA0B66E092D183E172027119E0B492E09A7D3058395F30B13D2E15D0B800F8~YAAQNz7VjAx8wuacAQAAwJf5AAd2MlYu+OOpaYMddIED7NfCe5yZunX8FY5nQPhqrEi3VfmSlR+ZXWe9qx2GpE9GLkCcvoINt4RDO2eOXEcu3CVDeqjfKKp37H2IaSHClJYECPIpXTLCkvleCOFlW7Ghyq8BmxhRU4oFVpNJUwI+5xjhDMdZ7D+0/RKgyaDVCE0Fsw8FnIH6sE86X44LxceB4kGtyI0mu5i5lViZBEy0bblZW1ipAYKetmgKNTBf4hD3Z8Jmhwi6xVTZc8Gac5e7lRcYE4TjcmBKirL5sp22ptQUlEE4mIdmt8wx7jQRKlyvUfhJrZbIGIqG0v1sMwd1zSrQcip9HpnGySCOATlUKrCSSXRSGaHZC55fdsqjlJ5Ht6+2UecDXr+0GO4hDtXq6dNPjXUE9W8G25URdi3fy+pFsFaYXwzDO79yyZGgK5OS1Ooqjj0IsYo=~1773837867006; mbox=PC#cc56ea07095546fba2b992af911f292c.38_0#1837082670|session#de2da273d9794017b872085803b5e8a4#1773839730; uniqueEventId=1773838544556_177383805479565; bm_s=YAAQNz7VjMiEwuacAQAARO75AAV2NX3iwtLwKhaFJKxk4ZwNxNp2YXhfE/dZT6AE7fTtgJgtnng+o2GvJN22Q15UAWuIQ+q267KZd94oKiZZ/xWundyZ6ZFhKj/dwviT41WN9u9R6uvz2/UciR0C3EzKJn2C7fhq8FXQTry0Ms/qoeelCGlqBijZO7YElaxmo+Ox3Jbi+LFgSbEaE2w/OqScwQKIku+fIEuwyK5zl0QiV3ws/eSpVcVXk8ds7BigTqkSzE3X4lVIXUGgk4UzpkHYCid4MBgfAdsu0alNEBrhrOkvcEjGTv4BCn3Q6ArWAKLHfp5QLooXGesuFh1gX4EiIG2MYEf2zRBo5nBYYEXMJwhjIhOiA7KJ/Id+Gt1/ToglCu/ggF5v9oXKEMBPhI40I6ioZu7TCYF6uuqrJl/rCQsKGKwGdRb07YjhjRShTzYKnt2zFh0TMqAHyFGEU699nbwuKrQ4jaFkTG6ocUHkYClKJfavRgrpaEYcbWLZWLlYvrR6yvx3qKNCnjTKscmD+b00++/7P6VVMBvmw/OmjWDOVm+2NoKh80FmvEo8gvlhb1GDQPrESivdPV0X40eN8jQxv/XReP2lW5dKHBQVIc3HWuIzJusTfq7kgeDtjo25v+hhraocGpohg+cq3tC5mzTorvHkILBhYT3eE7LvTfpbiOP6HzwDsvetPPY0yMgajfv2E4KpqmpAgjXFZ16UVohnus6DZFAQxjxGTc8zIPhYdGMuq76V2arOAvvOjoAb6nEvvGC0OwN7gazAlvDaNO97kSd3TSB2Ld1VayNZryx+7InR55inLeVJsUyy6o+QGu3o8P7y8O3ROOPsdefGpmKGQWkthzqtBi1oIoxRbufRHjSj0SNXIdJNB6BXRJGJCSfwKcrzo99OPNMB9C4fNz5augVGOZb5WBsLL2odhm5YoOpVrA==; bm_sv=1F979CF88A960CB41A2432CFFED64BBF~YAAQNz7VjMmEwuacAQAARO75AB+OFbns8h3SAQNE+eOGPIYwK3xJVDbBFhzxCMg4zyhS2lCzUiwa5pKzrtQDNIHflg6rGu6fQyxH/a2NBRy64BpEa38yJO/rA9oyyIoJ+JqAHwI26zrs1Iau6GFKkQ5FtO4FeJs4REGXYLkCgvI/BL4mMQFc7LPecIyR/LQ5YrYOcCAjp127K0P5/sM5On7qqNiupfvYfJi/Hmzvt9AqKRNwlp7J+mzrwj/0Of7Rmg==~1; _rdt_uuid=1773822266253.844db034-aeef-4927-a35f-21931b79bb92; ab.storage.sessionId.fc34d72a-11c5-4373-b3b6-983f769918c6=%7B%22g%22%3A%22328a9546-9a88-fce2-878f-df3f9347ee92%22%2C%22e%22%3A1773839675231%2C%22c%22%3A1773837556198%2C%22l%22%3A1773837875231%7D; _scid_r=JQZb2ecAxMwMBFUEK9w_yx6bF170SdUp5sRMHg; utag_main=_sn:3$_e:9%3Bexp-session$_s:0%3Bexp-session$_t:1773839675747%3Bexp-session$ses_id:1773837547864%3Bexp-session$_n:5%3Bexp-session$vapi_domain:tui.nl$v_id:019d000bdcc90013ab6ef8c74a7e0506f001e06700980-tui-nl$dc_visit:1$dc_event:34%3Bexp-session$dc_region:ap-east-1%3Bexp-session; _uetsid=e1054fc022a311f199e0bf7576173e53|1yymghz|2|g4g|0|2268; _uetvid=e105942022a311f18a7f4b3fe122d969|1bsfg5s|1773837840092|2|1|bat.bing.com/p/conversions/c/v; _ga=GA1.2.768633427.1773822220; cto_bundle=K7zuNV9EVHZrRkc4cjdGVWV0SGE4UzdLZWRqY20lMkZLdkw1RzZnaFVXT1VTcjFiSmwlMkJlalpOaXhpdlRlV1F2QmQ4TU5jSVJpZ253THdFNGJZV3dXWkEzaEFhTDhUSyUyQlMydDl4N2VpJTJGSmdMNDZyMFMlMkJMb293TGNCTG04cVJTR3RvRUt4eTJxbThaZHNCS2hCTXRidlVnUkxUJTJCNXclM0QlM0Q; _ga_MGQBZFB2LL=GS2.1.s1773837555$o4$g1$t1773837878$j16$l0$h0; ttcsid_CR1JHIRC77U9OU7LOO80=1773837560873::YhMJQkO3C7ac2Cr4zIy2.3.1773837881490.1; ttcsid=1773837560877::y9jcYITAt-jKqShFQXxu.3.1773837881491.0'
}

def parse_html_for_hotels(html_content):
    """Fallback parser that reads SSR data blocks or raw HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    hotels = []
    
    # Try looking for SSR data (Next.js / Nuxt etc.)
    scripts = soup.find_all("script")
    for s in scripts:
        if s.string and ("__INITIAL_STATE__" in s.string or "window.pageData" in s.string or "__NEXT_DATA__" in s.get("id", "")):
            logger.info("Found SSR JSON Blob! You can expand the scraper to parse this JSON directly.")
            # In a full implementation, you'd json.loads() this and extract pricing.
            # Due to the scope, we'll continue with HTML extraction below to get the basic cards.

    # Try HTML selectors
    card_selectors = [
        "a[data-testid='accommodation-card']",
        "article a[href*='/reizen/']",
        ".search-result-card a",
        "a[href*='formentera'][href*='hotel']",
    ]

    for selector in card_selectors:
        cards = soup.select(selector)
        if cards:
            logger.info(f"Found {len(cards)} hotel cards using selector {selector}")
            for card in cards:
                href = card.get('href')
                name = card.text.strip()[:100]
                if href and href not in [h['hotel_url'] for h in hotels]:
                    hotels.append({
                        "hotel_name": name,
                        "hotel_url": href if href.startswith("http") else f"https://www.tui.nl{href}",
                        "room_name": "Check details online",
                        "meal_plan": "Check details online",
                        "departure_airport": "Check details online",
                        "duration_days": 8,
                        "duration_nights": 7,
                        "flight_departure_time": "N/A",
                        "flight_arrival_time": "N/A",
                        "flight_airline": "N/A",
                        "final_price_per_person": None,
                        "tourist_tax": None,
                        "currency": "EUR"
                    })
            break
            
    return hotels

def scrape_with_requests():
    logger.info("=" * 60)
    logger.info("Starting HTTP Scraper with Custom Cookies")
    logger.info("=" * 60)
    
    try:
        response = requests.get(LISTING_URL, headers=HEADERS)
        
        if response.status_code == 403:
            logger.error("403 Access Denied. The WAF (Web Application Firewall) blocked the request. "
                         "This usually means the IP address is flagged, or the requested blocked on TLS fingerprinting. "
                         "Try running this script locally from your own computer where the IP is trusted.")
            return

        logger.info(f"Successful fetch! Status Code: {response.status_code}")
        
        hotels = parse_html_for_hotels(response.text)
        
        if not hotels:
            logger.error("No hotels found in the fetched HTML.")
            return
            
        logger.info(f"Successfully extracted {len(hotels)} basic hotel links.")
        for h in hotels:
            logger.info(f" - {h['hotel_name']} ({h['hotel_url']})")
        
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "source_url": LISTING_URL,
                "total_packages": len(hotels),
                "packages": hotels
            }, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Saved results to {OUTPUT_FILE}")
        
    except Exception as e:
        logger.error(f"Error during HTTP fetch: {e}")

if __name__ == "__main__":
    scrape_with_requests()
