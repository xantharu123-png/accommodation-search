#!/usr/bin/env python3
"""
Google Hotels Scraper
Aggregiert Hotels von ALLEN Plattformen über Google Hotels (google.com/travel)
"""

import base64
import json
import os
import re
import tempfile
import time
from datetime import date
from typing import List, Dict, Optional
from urllib.parse import quote

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

from chrome_driver import create_driver


BASE_URL = "https://www.google.com"

# Organic result cards - the sponsored carousel at the top is NOT inside these
CARD_SELECTOR = 'div[jsname="mutHjb"]'

# Render Free has 0.1 CPU - Google Travel needs a while to render the list
RESULTS_WAIT_SECONDS = 60

# Prices arrive after the list. Read too early on Render, the cards had no price yet
# and the generic CHF pattern picked up the rating instead (CHF 45 for 4,5 stars).
PRICES_WAIT_SECONDS = 120

# Reads all cards in ONE WebDriver round trip. Uses semantic anchors (h2 = name,
# aria-labels for price/rating) instead of Google's obfuscated class names.
EXTRACT_CARDS_JS = r"""
let cards = [...document.querySelectorAll(arguments[0])];
if (!cards.length) {
    // Fallback if Google renames the jsname: largest block around each hotel name
    cards = [...document.querySelectorAll('h2')].map(h => {
        let e = h;
        while (e.parentElement && e.parentElement.querySelectorAll('h2').length === 1) e = e.parentElement;
        return e;
    }).filter(e => e.querySelector('a[href*="/travel/"]'));
}
const clean = s => (s || '').replace(/ /g, ' ').trim();
return cards.map(c => {
    const labels = [...c.querySelectorAll('[aria-label]')].map(e => clean(e.getAttribute('aria-label')));
    const priceLink = [...c.querySelectorAll('a[aria-label]')]
        .find(a => /^(Preise ab|Prices? (starting )?from)/i.test(clean(a.getAttribute('aria-label'))));
    const link = priceLink || c.querySelector('a[href*="/travel/"]');
    const images = [...c.querySelectorAll('img')]
        .map(i => i.getAttribute('src') || i.getAttribute('data-src') || '')
        .filter(src => src.startsWith('http'));
    const name = c.querySelector('h2');
    return {
        name: clean(name ? name.innerText : ''),
        labels: labels,
        price_text: clean(priceLink ? priceLink.textContent : ''),
        text: clean(c.innerText),
        url: link ? link.href : '',
        images: images
    };
});
"""

# Cheap check whether any hotel card already shows a price (polled while waiting for prices)
HAS_PRICES_JS = r"""
let links = [...document.querySelectorAll(arguments[0] + ' a[aria-label]')];
if (!links.length) links = [...document.querySelectorAll('a[aria-label]')];
return links.some(a => /^(Preise ab|Prices? (starting )?from)/i.test(a.getAttribute('aria-label').trim()));
"""

# Cheap check whether the list changed (polled while waiting for the next page)
CARD_NAMES_JS = r"""
return [...document.querySelectorAll(arguments[0])].map(c => {
    const h = c.querySelector('h2');
    return h ? h.innerText.replace(/ /g, ' ').trim() : '';
});
"""

# Month names as Google shows them in the date inputs ("Fr., 13. Nov.", "Fri, Nov 13")
MONTH_PREFIXES = {
    1: ('jan',), 2: ('feb',), 3: ('mär', 'mar', 'mrz'), 4: ('apr',),
    5: ('mai', 'may'), 6: ('jun',), 7: ('jul',), 8: ('aug',),
    9: ('sep',), 10: ('okt', 'oct'), 11: ('nov',), 12: ('dez', 'dec'),
}


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _pb_int(field: int, value: int) -> bytes:
    return _varint(field << 3) + _varint(value)


def _pb_bytes(field: int, payload: bytes) -> bytes:
    return _varint(field << 3 | 2) + _varint(len(payload)) + payload


def _pb_date(field: int, day: date) -> bytes:
    return _pb_bytes(field, _pb_int(1, day.year) + _pb_int(2, day.month) + _pb_int(3, day.day))


def build_ts_param(check_in: date, check_out: date, adults: int, currency: str = 'CHF') -> str:
    """Encode dates + guests like Google Travel does in its `ts` URL parameter.

    Plain parameters (checkin=, dates=, ibp=htl;dates=...) are ignored by Google.
    `ts` is a base64 protobuf - decoded from a search where the dates were picked
    in the UI (2026-10-25):
      1: 1
      2: { 1: {1: 3} (one per adult), 2: 0 }                     # travellers
      3: { 2: { 2: { 1: check-in, 2: check-out, 3: nights },     # stay
                6: { 1: 1 } } }                                  # rooms
      5: { 1: { 7: "CHF" } }                                     # currency
    The place comes from `q`, so the place id (field 3.1) is left out.
    """
    nights = (check_out - check_in).days
    travellers = b''.join(_pb_bytes(1, _pb_int(1, 3)) for _ in range(max(1, adults))) + _pb_int(2, 0)
    stay = _pb_bytes(2, _pb_date(1, check_in) + _pb_date(2, check_out) + _pb_int(3, nights))
    stay += _pb_bytes(6, _pb_int(1, 1))
    ts = (_pb_int(1, 1)
          + _pb_bytes(2, travellers)
          + _pb_bytes(3, _pb_bytes(2, stay))
          + _pb_bytes(5, _pb_bytes(1, _pb_bytes(7, currency.encode()))))
    return base64.urlsafe_b64encode(ts).decode().rstrip('=')


def parse_number(text: str) -> int:
    """'1.433' / "1'250" / '1,250' -> int"""
    return int(re.sub(r"[^\d]", "", text))


class GoogleHotelsSearcher:
    def __init__(self, config_path: str = None):
        """Initialize Google Hotels searcher"""
        if config_path:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)

        self.driver = None
        self.results = []

    def setup_driver(self):
        """Setup Chrome driver (shared start in chrome_driver.py)"""
        chrome_options = Options()

        if self.config.get('scraping_settings', {}).get('headless', True):
            chrome_options.add_argument('--headless=new')

        # Docker/Render stability options
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--window-size=1280,900')
        chrome_options.add_argument('--lang=de-CH')

        # Images are not needed - their URLs are still in the HTML
        chrome_options.add_experimental_option("prefs", {
            "profile.managed_default_content_settings.images": 2,
        })

        # Anti-detection (keep minimal)
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])

        self.driver = create_driver(chrome_options)

        # Google serves a reduced result list to "HeadlessChrome" or outdated user agents,
        # so use the real browser version without the headless marker
        user_agent = self.driver.execute_script("return navigator.userAgent").replace('HeadlessChrome', 'Chrome')
        self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            'userAgent': user_agent,
            'acceptLanguage': 'de-CH,de',
        })

    def build_search_url(self) -> str:
        """Build Google Travel hotel search URL with dates and guests"""
        params = self.config['search_parameters']

        check_in = date.fromisoformat(params['check_in'])
        check_out = date.fromisoformat(params['check_out'])
        ts = build_ts_param(check_in, check_out, int(params.get('guests', 2)))

        query = f"hotels in {params['location']}"
        return f"{BASE_URL}/travel/search?q={quote(query)}&hl=de&gl=ch&curr=CHF&ts={ts}"

    def handle_cookie_banner(self):
        """Handle Google cookie consent (consent.google.com redirect or dialog)"""
        # Reject first (no tracking needed), accept only as fallback
        consent_buttons = [
            "//button[normalize-space()='Alle ablehnen']",
            "//button[normalize-space()='Reject all']",
            "//button[normalize-space()='Alle akzeptieren']",
            "//button[normalize-space()='Accept all']",
        ]

        for xpath in consent_buttons:
            buttons = [b for b in self.driver.find_elements(By.XPATH, xpath) if b.is_displayed()]
            if buttons:
                label = buttons[0].text
                try:
                    buttons[0].click()
                except Exception as e:
                    print(f"⚠ Cookie-Banner Klick fehlgeschlagen: {e}")
                    continue
                print(f"✓ Cookie-Banner geschlossen ({label})")
                time.sleep(2)
                return

        print("⚠ Kein Cookie-Banner gefunden")

    def wait_for_cards(self, timeout: int = RESULTS_WAIT_SECONDS) -> bool:
        """Wait until Google rendered the hotel list"""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, CARD_SELECTOR)
                or len(d.find_elements(By.TAG_NAME, 'h2')) > 3
            )
            return True
        except TimeoutException:
            return False

    def wait_for_prices(self, timeout: int = PRICES_WAIT_SECONDS) -> bool:
        """Wait until Google loaded the prices into the hotel list"""
        try:
            WebDriverWait(self.driver, timeout, poll_frequency=2).until(
                lambda d: d.execute_script(HAS_PRICES_JS, CARD_SELECTOR)
            )
            return True
        except TimeoutException:
            return False

    def get_date_inputs(self) -> List[str]:
        """Values of the check-in/check-out inputs in the search bar, e.g. 'Fr., 13. Nov.'"""
        return self.driver.execute_script(
            "return [...document.querySelectorAll("
            "'input[placeholder=\"Check-in\"], input[placeholder=\"Check-out\"]')].map(i => i.value);"
        )

    @staticmethod
    def shows_date(value: str, day: date) -> bool:
        """Does an input value like 'Fr., 13. Nov.' or 'Fri, Nov 13' show this date?"""
        value = value.lower()
        days = [int(d) for d in re.findall(r'\b(\d{1,2})\b', value)]
        return day.day in days and any(m in value for m in MONTH_PREFIXES[day.month])

    def dates_applied(self, check_in: date, check_out: date) -> bool:
        values = self.get_date_inputs()
        return (len(values) >= 2
                and self.shows_date(values[0], check_in)
                and self.shows_date(values[1], check_out))

    def set_dates_in_ui(self, check_in: date, check_out: date) -> bool:
        """Fallback if Google ignores `ts`: pick the dates in the date picker.

        The picker's day cells carry data-iso="YYYY-MM-DD" for the next ~12 months.
        """
        try:
            inputs = [i for i in self.driver.find_elements(By.CSS_SELECTOR, "input[placeholder='Check-in']")
                      if i.is_displayed()]
            inputs[0].click()

            for day in (check_in, check_out):
                cell = WebDriverWait(self.driver, 10).until(
                    lambda d: d.find_element(By.CSS_SELECTOR, f"[data-iso='{day.isoformat()}']")
                )
                # JS click also works for months that are not scrolled into view
                self.driver.execute_script("arguments[0].click();", cell)
                time.sleep(1)

            done = [b for b in self.driver.find_elements(
                        By.XPATH, "//button[normalize-space()='Fertig' or normalize-space()='Done']")
                    if b.is_displayed()]
            if done:
                done[0].click()

            time.sleep(3)
            self.wait_for_cards()
            return self.dates_applied(check_in, check_out)
        except Exception as e:
            print(f"⚠ Datum im Kalender setzen fehlgeschlagen: {e}")
            return False

    def go_to_next_page(self, current_names: List[str]) -> bool:
        """Click Google's 'Weiter' (next page) button and wait for new cards"""
        # The image carousels also have 'Weiter' buttons, but only as aria-label without text
        buttons = [b for b in self.driver.find_elements(
                       By.XPATH, "//button[normalize-space()='Weiter' or normalize-space()='Next']")
                   if b.is_displayed()]
        if not buttons:
            return False

        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", buttons[0])
        buttons[0].click()

        try:
            WebDriverWait(self.driver, RESULTS_WAIT_SECONDS).until(
                lambda d: d.execute_script(CARD_NAMES_JS, CARD_SELECTOR)[:3] != current_names[:3]
            )
            return True
        except TimeoutException:
            return False

    def extract_hotel_data(self, card: Dict) -> Optional[Dict]:
        """Extract hotel data from the raw Google Hotels card (see EXTRACT_CARDS_JS)"""
        try:
            data = {
                'name': card['name'] or 'N/A',
                'location': 'N/A',
                'price_per_night': 0,
                'rating': None,
                'num_reviews': 0,
                'url': card['url'] or 'N/A',
                'image_url': 'N/A',
                'image_urls': [],
                'distance_km': 0,
                'source': 'Google Hotels',
            }

            labels = card['labels']
            card_text = card['text']

            # Price per night - Google shows the nightly price ("Preise ab CHF 146 für ...");
            # the total is only in the hidden text ("CHF 292 Gesamtpreis 2 Übernachtungen")
            price_patterns = [
                r'(?:Preise ab|Prices? (?:starting )?from)\s*(?:CHF|Fr\.)\s*(\d[\d\'’.,]*)',
                r'(?:CHF|Fr\.)[^\S\n]*(\d[\d\'’.,]*)',  # same line only - the next line can be the rating
            ]
            for text in labels + [card_text]:
                match = re.search(price_patterns[0], text, re.IGNORECASE)
                if match:
                    data['price_per_night'] = parse_number(match.group(1))
                    break

            if not data['price_per_night']:
                total = re.search(r'(?:CHF|Fr\.)\s*(\d[\d\'’.,]*)\s*(?:Gesamtpreis|total)', card['price_text'], re.IGNORECASE)
                nights = re.search(r'(\d+)\s*(?:Übernachtung|night)', card['price_text'], re.IGNORECASE)
                if total and nights and int(nights.group(1)) > 0:
                    data['price_per_night'] = round(parse_number(total.group(1)) / int(nights.group(1)))
                else:
                    match = re.search(price_patterns[1], card_text)
                    if match:
                        data['price_per_night'] = parse_number(match.group(1))

            # Rating (0-5) + number of reviews: "4,4 von 5 Sternen aus 1.090 Rezensionen"
            for label in labels:
                match = re.search(
                    r'(\d(?:[.,]\d)?)\s*(?:von|out of)\s*5\b.*?(?:aus|from)\s*(\d[\d\'’.,]*)\s*(?:Rezension|Bewertung|review)',
                    label, re.IGNORECASE)
                if match:
                    rating_val = float(match.group(1).replace(',', '.'))
                    if 0 < rating_val <= 5.0:
                        data['rating'] = rating_val
                        data['num_reviews'] = parse_number(match.group(2))
                    break

            # Images (first ones of the photo carousel)
            if card['images']:
                data['image_url'] = card['images'][0]
                data['image_urls'] = card['images'][:5]

            # Distance (if available)
            dist_match = re.search(r'(\d+[.,]?\d*)\s*(?:km|Kilometer)\b', card_text)
            if dist_match:
                data['distance_km'] = float(dist_match.group(1).replace(',', '.'))

            # Ensure compatibility with app.py HTML report (uses 'title' not 'name')
            data['title'] = data['name']
            data['platform'] = 'Google Hotels'

            return data

        except Exception as e:
            print(f"⚠ Extraction error: {e}")
            return None

    def search(self):
        """Perform Google Hotels search"""
        print("🌐 Starte Google Hotels Suche...")
        print("=" * 60)

        self.setup_driver()

        try:
            params = self.config['search_parameters']
            check_in = date.fromisoformat(params['check_in'])
            check_out = date.fromisoformat(params['check_out'])
            google_url = self.build_search_url()

            print(f"📍 Suche: {params['location']} ({check_in} - {check_out}, {params.get('guests', 2)} Gäste)")
            print(f"🔗 URL: {google_url}\n")

            self.driver.get(google_url)

            # Fresh profile → Google redirects to consent.google.com first, then back
            self.handle_cookie_banner()

            print("📜 Lade Hotel-Ergebnisse...")
            if not self.wait_for_cards():
                print("⚠ Keine Hotels gefunden!\n")
                debug_path = os.path.join(tempfile.gettempdir(), 'google_hotels_debug.html')
                try:
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write(self.driver.page_source)
                    print(f"📝 Debug HTML saved to {debug_path}")
                except Exception:
                    pass
                return

            # Check that Google really uses our dates (otherwise prices are for "tomorrow")
            if self.dates_applied(check_in, check_out):
                print(f"✓ Reisedaten gesetzt: {' - '.join(self.get_date_inputs()[:2])}")
            else:
                print(f"⚠ Google ignoriert Reisedaten ({self.get_date_inputs()[:2]}), setze sie im Kalender...")
                if not self.set_dates_in_ui(check_in, check_out):
                    print("❌ Reisedaten konnten nicht gesetzt werden - Preise wären falsch")
                    return
                print(f"✓ Reisedaten gesetzt: {' - '.join(self.get_date_inputs()[:2])}")

            # Collect hotels page by page (20 per page)
            all_hotels = []
            seen_names = set()
            max_results = self.config['output'].get('max_results', 50)
            max_pages = self.config['output'].get('max_pages', 3)
            ad_keywords = ['top 10', 'entdecken', 'geheimtipp', 'günstig', 'buchen sie',
                           'best deal', 'official site', 'offizielle', 'jetzt buchen',
                           'angebote', 'unsere top', 'vergleichen', 'gesponsert', 'sponsored']

            for page in range(1, max_pages + 1):
                if not self.wait_for_prices():
                    print(f"⚠ Keine Preise nach {PRICES_WAIT_SECONDS}s")
                cards = self.driver.execute_script(EXTRACT_CARDS_JS, CARD_SELECTOR)
                print(f"🔍 Seite {page}: {len(cards)} Hotel-Cards gefunden")

                for card in cards:
                    if len(all_hotels) >= max_results:
                        break

                    data = self.extract_hotel_data(card)

                    if not data or data['name'] == "N/A" or data['name'] in seen_names:
                        continue
                    seen_names.add(data['name'])

                    if data['price_per_night'] <= 0:
                        print(f"  ❌ {data['name'][:50]} - kein Preis (ausgebucht?)")
                        continue

                    # Filter out Google Ads / sponsored results
                    name_lower = data['name'].lower()
                    is_ad = any(kw in name_lower for kw in ad_keywords)

                    if is_ad:
                        print(f"  ⚠️ Werbung übersprungen: {data['name'][:50]}")
                    else:
                        all_hotels.append(data)
                        print(f"  ✓ {data['name'][:50]} - CHF {data['price_per_night']}/Nacht - ⭐ {data['rating']}")

                if len(all_hotels) >= max_results or page == max_pages:
                    break
                if not self.go_to_next_page([c['name'] for c in cards]):
                    break

            print(f"\n✓ {len(all_hotels)} Hotels extrahiert")

            # Apply filters
            self.results = self.filter_hotels(all_hotels)

            print(f"\n✅ {len(self.results)} passende Hotels!")

        except Exception as e:
            print(f"\n❌ Fehler: {e}")
            import traceback
            traceback.print_exc()

        finally:
            if self.driver:
                self.driver.quit()

    def filter_hotels(self, hotels: List[Dict]) -> List[Dict]:
        """Apply filters to hotel results"""
        filtered = []
        filters = self.config.get('filters', {})

        # Frontend sends the hotel rating on the 10-point scale (like Booking),
        # Google rates 0-5 → compare on Google's scale
        min_rating = filters.get('min_rating_hotels', filters.get('min_rating', 0))
        if min_rating > 5:
            min_rating = min_rating / 2

        for hotel in hotels:
            # Price filter
            max_price = filters.get('max_price', filters.get('max_price_per_night_chf', 999999))
            if hotel['price_per_night'] > max_price:
                continue

            # Rating filter
            if hotel['rating'] and hotel['rating'] < min_rating:
                continue

            # Reviews filter
            min_reviews = filters.get('min_reviews', filters.get('min_number_of_reviews', 0))
            if hotel['num_reviews'] < min_reviews:
                continue

            filtered.append(hotel)

        return filtered


def main():
    """Test Google Hotels scraper"""
    import sys

    config_file = sys.argv[1] if len(sys.argv) > 1 else "config.json"

    searcher = GoogleHotelsSearcher(config_file)
    searcher.search()

    print(f"\n📊 RESULTS: {len(searcher.results)} hotels")
    for i, hotel in enumerate(searcher.results[:5], 1):
        print(f"{i}. {hotel['name']} - CHF {hotel['price_per_night']}/night - ⭐ {hotel['rating']}")


if __name__ == "__main__":
    main()
