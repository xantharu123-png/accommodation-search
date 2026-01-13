#!/usr/bin/env python3
"""
Google Hotels Scraper
Aggregiert Hotels von ALLEN Plattformen über Google Hotels
"""

import json
import time
import re
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class GoogleHotelsSearcher:
    def __init__(self, config_path: str = None):
        """Initialize Google Hotels searcher"""
        if config_path:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        
        self.driver = None
        self.results = []
        
    def setup_driver(self):
        """Setup Chrome driver with anti-detection"""
        chrome_options = Options()
        
        if self.config.get('scraping_settings', {}).get('headless', True):
            chrome_options.add_argument('--headless=new')
        
        # Essential args for Docker/Railway
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-setuid-sandbox')
        
        # Anti-detection
        chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Remove webdriver flag
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Set window size
        self.driver.set_window_size(1920, 1080)
        
    def build_search_url(self) -> str:
        """Build Google Hotels search URL"""
        params = self.config['search_parameters']
        
        location = params['location']
        check_in = params['check_in']
        check_out = params['check_out']
        guests = params['guests']
        
        # Google Hotels URL format
        base_url = "https://www.google.com/travel/hotels"
        
        # Build query
        url = f"{base_url}/{quote(location)}"
        url += f"?q=hotels%20in%20{quote(location)}"
        url += f"&g2lb=2502548%2C2503771%2C2503781%2C4258168%2C4270442%2C4284970%2C4291517%2C4306835%2C4597339%2C4757164%2C4814050%2C4874190%2C4893075%2C4924070%2C4965990%2C4990494%2C72302247%2C72317059%2C72406588%2C72414906%2C72421566%2C72462234%2C72470440%2C72470899%2C72471280%2C72472051%2C72473841%2C72481459%2C72485658%2C72494250%2C72513513%2C72536387%2C72538597%2C72549171%2C72570850%2C72586335%2C72597757%2C72602734%2C72616120%2C72619927%2C72628719%2C72647020"
        url += f"&hl=de&gl=ch"
        url += f"&cs=1"
        url += f"&ssta=1"
        url += f"&ts=CAESCgoCCAMKAggDEAAaLAoSCQC8TtcRRCpAEZyqjzpUIkZAEhIJi_rYYhxEKkARf9Y7N-kiRkAYATICEAAqCwoHKAE6A0NIRhAA"
        url += f"&rp=ogHEBUxldWtlcmJhZA"
        url += f"&ap=MABoAQ"
        url += f"&ictx=111"
        
        # Add dates
        url += f"&sa=X"
        url += f"&ved=0CAAQ5JsGahcKEwjQ"
        
        return url
    
    def handle_cookie_banner(self):
        """Handle Google cookie consent"""
        try:
            # Wait for cookie banner
            time.sleep(2)
            
            # Try different cookie accept buttons
            cookie_selectors = [
                "button[aria-label*='Accept']",
                "button[aria-label*='Akzeptieren']",
                "button[aria-label*='Alle akzeptieren']",
                "//button[contains(text(), 'Accept')]",
                "//button[contains(text(), 'Akzeptieren')]",
            ]
            
            for selector in cookie_selectors:
                try:
                    if selector.startswith("//"):
                        btn = self.driver.find_element(By.XPATH, selector)
                    else:
                        btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    btn.click()
                    print("✓ Cookie-Banner akzeptiert")
                    time.sleep(1)
                    return
                except:
                    continue
                    
        except Exception as e:
            print("⚠ Kein Cookie-Banner gefunden")
    
    def extract_hotel_data(self, hotel_element) -> Optional[Dict]:
        """Extract hotel data from Google Hotels card"""
        try:
            data = {
                'name': 'N/A',
                'location': 'N/A',
                'price_per_night': 0,
                'rating': None,
                'num_reviews': 0,
                'url': 'N/A',
                'image_url': 'N/A',
                'image_urls': [],
                'distance_km': 0,
                'source': 'Google Hotels',
            }
            
            # Get all text for parsing
            try:
                card_text = hotel_element.text
            except:
                return None
            
            # Name - usually in h2 or h3
            try:
                name_selectors = [
                    "h2",
                    "h3",
                    "[role='heading']",
                    "div[class*='hotel-name']",
                ]
                
                for selector in name_selectors:
                    try:
                        name_elem = hotel_element.find_element(By.CSS_SELECTOR, selector)
                        name_text = name_elem.text.strip()
                        if name_text and len(name_text) > 3:
                            data['name'] = name_text
                            break
                    except:
                        continue
            except:
                pass
            
            # Price - look for CHF or $ with numbers
            try:
                price_patterns = [
                    r'CHF\s*(\d[\d\s\']*)',
                    r'Fr\.\s*(\d[\d\s\']*)',
                    r'\$\s*(\d[\d\s,]*)',
                    r'€\s*(\d[\d\s,]*)',
                ]
                
                for pattern in price_patterns:
                    price_match = re.search(pattern, card_text.replace('.', '').replace(' ', ''))
                    if price_match:
                        price_str = price_match.group(1).replace("'", "").replace(",", "").replace(" ", "")
                        price = int(price_str)
                        
                        # Google usually shows per-night prices
                        data['price_per_night'] = price
                        break
            except:
                pass
            
            # Rating - Google uses 5-star scale
            try:
                # Look for patterns like "4.5" or "4,5"
                rating_patterns = [
                    r'(\d[.,]\d)\s*(?:von|out of|★)',
                    r'(\d[.,]\d)\s*\(',
                    r'★\s*(\d[.,]\d)',
                ]
                
                for pattern in rating_patterns:
                    rating_match = re.search(pattern, card_text)
                    if rating_match:
                        rating_str = rating_match.group(1).replace(',', '.')
                        data['rating'] = float(rating_str)
                        break
            except:
                pass
            
            # Reviews count
            try:
                review_patterns = [
                    r'\((\d[\d,]*)\s*(?:Bewertungen|reviews)',
                    r'(\d[\d,]*)\s*(?:Bewertungen|reviews)',
                ]
                
                for pattern in review_patterns:
                    reviews_match = re.search(pattern, card_text.replace('.', ''))
                    if reviews_match:
                        reviews_str = reviews_match.group(1).replace(',', '').replace('.', '')
                        data['num_reviews'] = int(reviews_str)
                        break
            except:
                pass
            
            # URL - try to get link
            try:
                link_elem = hotel_element.find_element(By.TAG_NAME, "a")
                href = link_elem.get_attribute('href')
                if href:
                    data['url'] = href
            except:
                pass
            
            # Image
            try:
                img_elem = hotel_element.find_element(By.TAG_NAME, "img")
                img_src = img_elem.get_attribute('src')
                if img_src and 'http' in img_src:
                    data['image_url'] = img_src
                    data['image_urls'] = [img_src]
            except:
                pass
            
            # Distance (if available)
            try:
                distance_patterns = [
                    r'(\d+[.,]?\d*)\s*km',
                    r'(\d+[.,]?\d*)\s*Kilometer',
                ]
                
                for pattern in distance_patterns:
                    dist_match = re.search(pattern, card_text)
                    if dist_match:
                        dist_str = dist_match.group(1).replace(',', '.')
                        data['distance_km'] = float(dist_str)
                        break
            except:
                pass
            
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
            # Build simpler URL
            params = self.config['search_parameters']
            location = params['location']
            check_in = params['check_in']
            check_out = params['check_out']
            guests = params['guests']
            
            # Simple Google search for hotels
            search_query = f"hotels in {location}"
            google_url = f"https://www.google.com/search?q={quote(search_query)}&ibp=htl;dates={check_in.replace('-', '')},{check_out.replace('-', '')};guests={guests}"
            
            print(f"📍 Suche: {location}")
            print(f"🔗 URL: {google_url}\n")
            
            self.driver.get(google_url)
            time.sleep(5)
            
            # Handle cookie banner
            self.handle_cookie_banner()
            
            print("📜 Lade Hotel-Ergebnisse...")
            time.sleep(3)
            
            # Scroll to load results
            for i in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            # Find hotel cards - Google Hotels uses various selectors
            hotels = []
            
            selectors = [
                "div[class*='hotel']",
                "div[data-h]",
                "div[jsname]",
                "div[class*='card']",
                "li[class*='hotel']",
                "div[role='listitem']",
            ]
            
            print("🔍 Suche Google Hotels Cards...")
            
            for selector in selectors:
                try:
                    found = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    # Filter elements that look like hotel cards (have price + name)
                    potential_hotels = []
                    for elem in found:
                        try:
                            text = elem.text
                            if ('CHF' in text or 'Fr.' in text or '$' in text) and len(text) > 100:
                                potential_hotels.append(elem)
                        except:
                            continue
                    
                    if len(potential_hotels) > 3:
                        hotels = potential_hotels
                        print(f"✓ {len(hotels)} Hotel-Cards gefunden (Selector: {selector})\n")
                        break
                except:
                    continue
            
            # Fallback: Get all divs with hotel-like content
            if not hotels:
                print("⚠ Kein Standard-Selector funktioniert, versuche Fallback...")
                try:
                    all_divs = self.driver.find_elements(By.TAG_NAME, "div")
                    print(f"📊 Analysiere {len(all_divs)} DIVs...")
                    
                    for div in all_divs:
                        try:
                            text = div.text
                            # Hotel cards have: price, name, rating
                            if ('CHF' in text or 'Fr.' in text or '$' in text) and \
                               len(text) > 100 and len(text) < 800 and \
                               ('★' in text or 'star' in text.lower() or 'stern' in text.lower()):
                                hotels.append(div)
                                if len(hotels) >= 30:
                                    break
                        except:
                            continue
                    
                    if hotels:
                        print(f"✓ Fallback: {len(hotels)} Hotel-ähnliche Cards gefunden\n")
                except Exception as e:
                    print(f"❌ Fallback fehlgeschlagen: {e}")
            
            if not hotels:
                print("⚠ Keine Hotels gefunden!\n")
                # Save debug HTML
                try:
                    with open('/tmp/google_hotels_debug.html', 'w', encoding='utf-8') as f:
                        f.write(self.driver.page_source)
                    print("📝 Debug HTML saved to /tmp/google_hotels_debug.html")
                except:
                    pass
                return
            
            # Extract data
            all_hotels = []
            max_results = min(len(hotels), self.config['output'].get('max_results', 50))
            
            print(f"📊 Extrahiere Daten von {max_results} Hotels...")
            for idx, hotel in enumerate(hotels[:max_results], 1):
                print(f"  [{idx}/{max_results}] ", end='', flush=True)
                
                data = self.extract_hotel_data(hotel)
                
                if data and data['name'] != "N/A" and data['price_per_night'] > 0:
                    all_hotels.append(data)
                    print(f"✓ {data['name'][:50]} - CHF {data['price_per_night']}")
                else:
                    print("❌")
                
                time.sleep(0.2)
            
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
        
        for hotel in hotels:
            # Price filter
            max_price = filters.get('max_price', filters.get('max_price_per_night_chf', 999999))
            if hotel['price_per_night'] > max_price:
                continue
            
            # Rating filter (Google Hotels uses 10-point scale same as Booking)
            min_rating = filters.get('min_rating_hotels', filters.get('min_rating', 0))
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
