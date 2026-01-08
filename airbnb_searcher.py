#!/usr/bin/env python3
"""
Airbnb Advanced Search Script
Sucht Airbnb-Unterkünfte mit erweiterten Filtern, die in der Web-UI nicht verfügbar sind
"""

import json
import time
import re
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import pandas as pd


class AirbnbSearcher:
    def __init__(self, config_path: str = "airbnb_search_config.json"):
        """Initialize the Airbnb searcher with config"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.driver = None
        self.results = []
        
    def setup_driver(self):
        """Setup Chrome driver with options"""
        chrome_options = Options()
        
        if self.config['scraping_settings']['headless']:
            chrome_options.add_argument('--headless=new')
        
        # User agent (optional)
        user_agent = self.config.get('scraping_settings', {}).get('user_agent')
        if user_agent:
            chrome_options.add_argument(f"user-agent={user_agent}")
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def build_search_url(self) -> str:
        """Build Airbnb search URL with parameters"""
        params = self.config['search_parameters']
        
        # Base URL
        base_url = "https://www.airbnb.ch/s/"
        
        # Location (URL-encoded)
        location = params['location'].replace(' ', '-').replace(',', '--')
        
        # Date parameters
        check_in = params['check_in']
        check_out = params['check_out']
        
        # Build URL
        url = f"{base_url}{location}/homes?"
        url += f"checkin={check_in}&checkout={check_out}"
        url += f"&adults={params['guests']}"
        
        if params.get('min_bedrooms', 0) > 0:
            url += f"&min_bedrooms={params['min_bedrooms']}"
        
        # Add price filter if specified
        max_price = self.config['filters'].get('max_price') or self.config['filters'].get('max_price_per_night_chf')
        if max_price:
            url += f"&price_max={max_price}"
        
        # 🏠 WICHTIG: Nur ganze Unterkünfte (keine Zimmer!)
        # Filtert: Wohnungen, Häuser, Villen, Gästehäuser etc.
        # Entfernt: Privatzimmer, geteilte Zimmer
        url += "&room_types%5B%5D=Entire%20home%2Fapt"
        
        # AMENITY CODES - Add REQUIRED amenities to URL!
        # This filters at SOURCE = much faster & more reliable!
        amenity_codes = {
            'private_pool': '7',        # Pool
            'private_whirlpool': '25',  # Hot tub / Whirlpool ← DISCOVERED!
            'private_sauna': '325',     # Sauna
            'fireplace': '27',          # Fireplace
            'parking': '9',             # Free parking
        }
        
        amenities = self.config.get('filters', {}).get('amenities', self.config.get('amenities', {}))
        has_required_amenities = False
        
        # Only add REQUIRED amenities to URL
        for amenity_key, code in amenity_codes.items():
            if amenity_key in amenities:
                # Handle both formats: {"pool": True} or {"pool": {"required": True}}
                amenity_value = amenities[amenity_key]
                is_required = False
                
                if isinstance(amenity_value, dict):
                    is_required = amenity_value.get('required', False)
                elif isinstance(amenity_value, bool):
                    is_required = amenity_value  # If True, treat as required
                
                if is_required:
                    url += f"&amenities%5B%5D={code}"
                    has_required_amenities = True
        
        if has_required_amenities:
            print("  💡 Pflicht-Ausstattung wird direkt in Airbnb gefiltert (schneller!)")
        
        return url
    
    def handle_cookie_banner(self):
        """Handle cookie consent banner"""
        try:
            print("🍪 Suche Cookie-Banner...")
            # Wait a bit for banner to appear
            time.sleep(2)
            
            # Try different cookie button selectors
            cookie_selectors = [
                # German buttons
                "//button[contains(., 'Alle akzeptieren')]",
                "//button[contains(., 'Alles akzeptieren')]",
                "//button[contains(., 'Akzeptieren')]",
                "//button[contains(., 'OK')]",
                # English buttons
                "//button[contains(., 'Accept all')]",
                "//button[contains(., 'Accept')]",
                "//button[contains(., 'OK')]",
                # By data attributes
                "//button[@data-testid='accept-btn']",
                "//button[@data-testid='main-cookies-banner-accept']",
                "//div[@role='dialog']//button[contains(@class, 'accept')]",
                # By aria-label
                "//button[contains(@aria-label, 'Accept')]",
                "//button[contains(@aria-label, 'Akzeptieren')]",
            ]
            
            for selector in cookie_selectors:
                try:
                    button = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    button.click()
                    print("✓ Cookie-Banner akzeptiert")
                    time.sleep(2)
                    return True
                except:
                    continue
            
            print("⚠ Kein Cookie-Banner gefunden oder bereits akzeptiert")
            return False
                    
        except Exception as e:
            print(f"⚠ Cookie-Banner Fehler: {e}")
            return False
    
    def extract_listing_data(self, listing_element) -> Optional[Dict]:
        """Extract data from a single listing element"""
        try:
            data = {}
            
            # Title
            try:
                title = listing_element.find_element(By.CSS_SELECTOR, "[data-testid='listing-card-title']").text
                data['title'] = title
            except:
                data['title'] = "N/A"
            
            # Subtitle (location details)
            try:
                subtitle = listing_element.find_element(By.CSS_SELECTOR, "[data-testid='listing-card-subtitle']").text
                data['subtitle'] = subtitle
                
                # Distance will be calculated by Google Maps later
                # For now, just set to 0 (unknown)
                data['distance_km'] = 0
                
            except:
                data['subtitle'] = "N/A"
                data['distance_km'] = 0
            
            # Price - try multiple selectors
            data['price_per_night'] = None
            try:
                # Method 1: Try to find price in any span containing "CHF"
                all_text = listing_element.text
                # Look for patterns like "CHF 150" or "CHF 1'500" or "150 CHF"
                price_patterns = [
                    r'CHF\s*(\d[\d\'\s]*\d|\d+)',  # CHF 150 or CHF 1'500
                    r'(\d[\d\'\s]*\d|\d+)\s*CHF',   # 150 CHF
                ]
                
                for pattern in price_patterns:
                    price_match = re.search(pattern, all_text.replace("'", ""))
                    if price_match:
                        price_str = price_match.group(1).replace("'", "").replace(" ", "")
                        data['price_per_night'] = int(price_str)
                        break
                
                # If still not found, try specific CSS selectors
                if data['price_per_night'] is None:
                    price_selectors = [
                        "span._tyxjp1",
                        "span[class*='price']",
                        "div[class*='price'] span",
                        "span._1y74zjx"
                    ]
                    for selector in price_selectors:
                        try:
                            price_element = listing_element.find_element(By.CSS_SELECTOR, selector)
                            price_text = price_element.text
                            price_match = re.search(r'(\d[\d\'\s]*\d|\d+)', price_text.replace("'", ""))
                            if price_match:
                                price_str = price_match.group(1).replace("'", "").replace(" ", "")
                                data['price_per_night'] = int(price_str)
                                break
                        except:
                            continue
            except Exception as e:
                print(f"\n⚠ Preis-Extraktion Fehler: {e}")
                data['price_per_night'] = None
            
            # Rating and Reviews - try multiple methods
            data['rating'] = None
            data['num_reviews'] = 0
            
            try:
                # Method 1: Look for rating pattern in all text
                all_text = listing_element.text
                
                # Find rating (format: "4.95" or "4,95")
                rating_patterns = [
                    r'(\d\.\d{1,2})\s*\(',  # "4.95 (123)"
                    r'★\s*(\d\.\d{1,2})',   # "★ 4.95"
                    r'⭐\s*(\d\.\d{1,2})',   # "⭐ 4.95"
                ]
                
                for pattern in rating_patterns:
                    rating_match = re.search(pattern, all_text)
                    if rating_match:
                        data['rating'] = float(rating_match.group(1))
                        break
                
                # Find number of reviews (format: "(123)" or "123 Bewertungen")
                review_patterns = [
                    r'\((\d+)\)',              # "(123)"
                    r'(\d+)\s*Bewertung',      # "123 Bewertungen"
                    r'(\d+)\s*review',         # "123 reviews"
                ]
                
                for pattern in review_patterns:
                    reviews_match = re.search(pattern, all_text)
                    if reviews_match:
                        data['num_reviews'] = int(reviews_match.group(1))
                        break
                
                # Method 2: Try CSS selectors as fallback
                if data['rating'] is None:
                    rating_selectors = [
                        "span.r4a59j5",
                        "span[class*='rating']",
                        "div[aria-label*='Rating']",
                    ]
                    for selector in rating_selectors:
                        try:
                            elem = listing_element.find_element(By.CSS_SELECTOR, selector)
                            rating_match = re.search(r'(\d\.\d{1,2})', elem.text)
                            if rating_match:
                                data['rating'] = float(rating_match.group(1))
                                break
                        except:
                            continue
                
                if data['num_reviews'] == 0:
                    review_selectors = [
                        "span.s1cjsi4j",
                        "span[class*='review']",
                    ]
                    for selector in review_selectors:
                        try:
                            elem = listing_element.find_element(By.CSS_SELECTOR, selector)
                            reviews_match = re.search(r'(\d+)', elem.text)
                            if reviews_match:
                                data['num_reviews'] = int(reviews_match.group(1))
                                break
                        except:
                            continue
                            
            except Exception as e:
                pass  # Keep defaults
            
            # Superhost badge
            try:
                listing_element.find_element(By.XPATH, ".//span[contains(text(), 'Superhost')]")
                data['is_superhost'] = True
            except:
                data['is_superhost'] = False
            
            # URL
            try:
                link = listing_element.find_element(By.CSS_SELECTOR, "a[href*='/rooms/']")
                data['url'] = link.get_attribute('href')
            except:
                data['url'] = None
            
            # Image URL (main image)
            try:
                img = listing_element.find_element(By.CSS_SELECTOR, "img[data-original-uri], img[src*='jpg']")
                img_url = img.get_attribute('src') or img.get_attribute('data-original-uri')
                data['image_url'] = img_url
                data['image_urls'] = [img_url] if img_url else []
            except:
                data['image_url'] = None
                data['image_urls'] = []
            
            return data
            
        except Exception as e:
            print(f"⚠ Fehler beim Extrahieren der Listing-Daten: {e}")
            return None
    
    def get_listing_details(self, url: str) -> Dict:
        """Get detailed information from listing page including amenities"""
        details = {
            'amenities': [],
            'description': '',
            'has_private_pool': False,
            'has_private_whirlpool': False,
            'has_private_sauna': False,
            'has_fireplace': False,
            'has_parking': False,
            'image_urls': []  # ALWAYS initialize!
        }
        
        try:
            # Open listing in new tab
            self.driver.execute_script(f"window.open('{url}', '_blank');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            
            time.sleep(self.config['scraping_settings']['wait_time_seconds'])
            
            # 📸 Get image gallery (5-20 images)
            try:
                # Find all images in the gallery - ONLY real photos, not icons!
                image_elements = self.driver.find_elements(By.CSS_SELECTOR, "img[src*='pictures']")
                
                image_urls = []
                for img in image_elements[:25]:  # Check more, filter later
                    img_url = img.get_attribute('src')
                    
                    # FILTER OUT property type icons and platform assets
                    if img_url and 'pictures' in img_url:
                        # Skip Airbnb platform assets (house icons, etc.)
                        if 'airbnb-platform-assets' in img_url or 'AirbnbPlatformAssets' in img_url:
                            continue
                        
                        # Skip if it's a tiny icon (property type illustration)
                        # Real photos have dimensions in URL like im_w_720, im_w_480, etc.
                        # Icons often have im_w_200 or smaller
                        if 'im_w_' in img_url:
                            # Extract width from URL
                            import re
                            width_match = re.search(r'im_w_(\d+)', img_url)
                            if width_match:
                                width = int(width_match.group(1))
                                if width < 400:  # Skip small images (icons)
                                    continue
                        
                        if img_url not in image_urls:
                            # Get high-res version
                            img_url = img_url.replace('im_w_720', 'im_w_1200').replace('im_w_480', 'im_w_1200')
                            image_urls.append(img_url)
                
                # Store images - even if less than 5!
                if len(image_urls) > 0:
                    details['image_urls'] = image_urls[:20]  # Max 20
                    print(f"📸 {len(details['image_urls'])} Bilder gefunden")
                else:
                    details['image_urls'] = []  # Explicitly empty!
            except Exception as e:
                pass
            
            # 💬 Get reviews (last 30)
            try:
                # Scroll to reviews section
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(1)
                
                # Find review elements
                review_elements = self.driver.find_elements(By.CSS_SELECTOR, "[data-review-id], .r1bctolv")
                
                reviews = []
                for review in review_elements[:30]:  # Max 30 reviews
                    try:
                        review_text = review.text
                        if review_text and len(review_text) > 20:  # Filter short reviews
                            reviews.append(review_text)
                    except:
                        continue
                
                if len(reviews) >= 3:  # Only if we have at least 3 reviews
                    details['reviews'] = reviews[:30]
                    print(f"💬 {len(details['reviews'])} Reviews gefunden")
            except Exception as e:
                pass
            
            # Get description
            try:
                description = self.driver.find_element(By.CSS_SELECTOR, "[data-section-id='DESCRIPTION_DEFAULT']").text
                details['description'] = description
            except:
                pass
            
            # Get amenities
            try:
                # Click "Alle Ausstattungsmerkmale anzeigen" button if exists
                show_all_btn = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Alle') and contains(text(), 'Ausstattung')]")
                show_all_btn.click()
                time.sleep(2)
            except:
                pass
            
            # Extract all amenity text
            try:
                amenity_elements = self.driver.find_elements(By.CSS_SELECTOR, "[data-section-id='AMENITIES_DEFAULT'] div")
                amenities_text = " ".join([elem.text.lower() for elem in amenity_elements])
                details['amenities'] = amenities_text
                
                # Check for specific amenities
                amenity_config = self.config.get('filters', {}).get('amenities', self.config.get('amenities', {}))
                
                # Private Pool
                if 'private_pool' in amenity_config:
                    amenity = amenity_config['private_pool']
                    if isinstance(amenity, dict) and 'search_terms' in amenity:
                        for term in amenity['search_terms']:
                            if term.lower() in amenities_text or term.lower() in details['description'].lower():
                                details['has_private_pool'] = True
                                break
                
                # Private Whirlpool
                if 'private_whirlpool' in amenity_config:
                    amenity = amenity_config['private_whirlpool']
                    if isinstance(amenity, dict) and 'search_terms' in amenity:
                        for term in amenity['search_terms']:
                            if term.lower() in amenities_text or term.lower() in details['description'].lower():
                                details['has_private_whirlpool'] = True
                                break
                
                # Private Sauna
                if 'private_sauna' in amenity_config:
                    amenity = amenity_config['private_sauna']
                    if isinstance(amenity, dict) and 'search_terms' in amenity:
                        for term in amenity['search_terms']:
                            if term.lower() in amenities_text or term.lower() in details['description'].lower():
                                details['has_private_sauna'] = True
                                break
                
                # Fireplace
                if 'fireplace' in amenity_config:
                    amenity = amenity_config['fireplace']
                    if isinstance(amenity, dict) and 'search_terms' in amenity:
                        for term in amenity['search_terms']:
                            if term.lower() in amenities_text or term.lower() in details['description'].lower():
                                details['has_fireplace'] = True
                                break
                
                # Parking
                if 'parking' in amenity_config:
                    amenity = amenity_config['parking']
                    if isinstance(amenity, dict) and 'search_terms' in amenity:
                        for term in amenity['search_terms']:
                            if term.lower() in amenities_text or term.lower() in details['description'].lower():
                                details['has_parking'] = True
                                break
                
            except Exception as e:
                print(f"⚠ Fehler beim Extrahieren der Ausstattung: {e}")
            
            # Close tab and switch back
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
            
        except Exception as e:
            print(f"⚠ Fehler beim Laden der Detail-Seite: {e}")
            # Make sure we're back on main window
            if len(self.driver.window_handles) > 1:
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
        
        return details
    
    def filter_results(self, listing: Dict, debug: bool = False) -> tuple[bool, str]:
        """Apply filters to a listing"""
        filters = self.config['filters']
        amenities = filters.get('amenities', self.config.get('amenities', {}))
        params = self.config['search_parameters']
        
        # Distance filter (using Google Maps real distance)
        max_distance = params.get('search_radius_km', 999)
        
        # Prefer real_distance_km (from Google Maps) over distance_km (from Airbnb)
        current_distance = listing.get('real_distance_km', listing.get('distance_km', 0))
        
        if current_distance > max_distance:
            if debug:
                city_name = listing.get('subtitle', listing.get('title', 'Unknown'))[:50]
                return False, f"Entfernung: {city_name} = {current_distance} km > {max_distance} km"
            return False, "distance"
        
        # Price filter
        if listing['price_per_night'] is not None:
            max_price = filters.get('max_price') or filters.get('max_price_per_night_chf', 999999)
            if listing['price_per_night'] > max_price:
                if debug:
                    return False, f"Preis: CHF {listing['price_per_night']} > {max_price}"
                return False, "price"
        else:
            if debug:
                return False, "Preis nicht gefunden"
            return False, "no_price"
        
        # Rating filter
        if listing['rating'] is not None:
            if listing['rating'] < filters['min_rating']:
                if debug:
                    return False, f"Rating: {listing['rating']} < {filters['min_rating']}"
                return False, "rating"
        else:
            if debug:
                return False, "Rating nicht gefunden"
            return False, "no_rating"
        
        # Number of reviews filter
        min_reviews = filters.get('min_reviews') or filters.get('min_number_of_reviews', 0)
        if listing['num_reviews'] < min_reviews:
            if debug:
                return False, f"Reviews: {listing['num_reviews']} < {min_reviews}"
            return False, "reviews"
        
        # Superhost filter
        superhost_only = filters.get('superhost_only', False)
        if superhost_only and not listing['is_superhost']:
            if debug:
                return False, "Kein Superhost"
            return False, "superhost"
        
        # Amenity filters (if required)
        if amenities.get('private_pool', {}).get('required', False) and not listing.get('has_private_pool', False):
            return False, "pool"
        
        if amenities.get('private_whirlpool', {}).get('required', False) and not listing.get('has_private_whirlpool', False):
            return False, "whirlpool"
        
        if amenities.get('private_sauna', {}).get('required', False) and not listing.get('has_private_sauna', False):
            return False, "sauna"
        
        if amenities.get('fireplace', {}).get('required', False) and not listing.get('has_fireplace', False):
            return False, "fireplace"
        
        if amenities.get('parking', {}).get('required', False) and not listing.get('has_parking', False):
            return False, "parking"
        
        return True, "passed"
    
    def search(self):
        """Perform the search and collect results"""
        print("🏠 Starte Airbnb-Suche...")
        print("=" * 60)
        
        self.setup_driver()
        
        try:
            # Build and open search URL
            search_url = self.build_search_url()
            print(f"📍 Suche: {self.config['search_parameters']['location']}")
            print(f"📅 Zeitraum: {self.config['search_parameters']['check_in']} - {self.config['search_parameters']['check_out']}")
            print(f"🔗 URL: {search_url}\n")
            
            self.driver.get(search_url)
            time.sleep(5)
            
            # Handle cookie banner
            self.handle_cookie_banner()
            
            # Wait for listings to load
            wait = WebDriverWait(self.driver, 15)
            
            # Variables for pagination
            current_page = 1
            max_pages = self.config['output'].get('max_pages', 5)  # Default to 5 if not set
            all_listings = []
            
            print(f"📄 Lade bis zu {max_pages} Seiten...\n")
            
            # Calculate nights for total price conversion
            from datetime import datetime
            check_in = datetime.strptime(self.config['search_parameters']['check_in'], '%Y-%m-%d')
            check_out = datetime.strptime(self.config['search_parameters']['check_out'], '%Y-%m-%d')
            num_nights = (check_out - check_in).days
            print(f"🌙 Aufenthalt: {num_nights} Nächte\n")
            
            filter_reasons = {}
            
            while current_page <= max_pages:
                print(f"📃 Seite {current_page}/{max_pages}...")
                
                try:
                    # Wait for listings to load
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[itemprop='itemListElement']")))
                    time.sleep(3)
                    
                    # Scroll to load all listings on current page
                    for i in range(2):
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1)
                    
                    # Find all listings on current page
                    listings = self.driver.find_elements(By.CSS_SELECTOR, "[itemprop='itemListElement']")
                    print(f"  ✓ {len(listings)} Listings gefunden")
                    
                    # IMPORTANT: Extract data IMMEDIATELY before elements become stale
                    print(f"  🔍 Extrahiere Daten von {len(listings)} Listings...")
                    page_results = []
                    
                    for listing in listings:
                        try:
                            data = self.extract_listing_data(listing)
                            if data and data.get('url'):
                                # Convert total price to per night if needed
                                if data['price_per_night'] and num_nights > 0:
                                    # Get max price from either key
                                    max_price = self.config['filters'].get('max_price') or self.config['filters'].get('max_price_per_night_chf', 999999)
                                    # If price seems too high, it's likely the total price
                                    if data['price_per_night'] > max_price * 2:
                                        data['total_price'] = data['price_per_night']
                                        data['price_per_night'] = round(data['price_per_night'] / num_nights)
                                
                                page_results.append(data)
                        except Exception as e:
                            continue
                    
                    print(f"  ✓ {len(page_results)} Listings erfolgreich extrahiert")
                    all_listings.extend(page_results)
                    
                    # Try to find and click "Next" button
                    if current_page < max_pages:
                        try:
                            # Look for next button
                            next_button_selectors = [
                                "//a[@aria-label='Weiter']",
                                "//a[@aria-label='Next']",
                                "//a[contains(@aria-label, 'nächste')]",
                                "//button[contains(@aria-label, 'Next')]",
                                "//nav//a[contains(., 'Weiter')]",
                            ]
                            
                            next_button = None
                            for selector in next_button_selectors:
                                try:
                                    next_button = self.driver.find_element(By.XPATH, selector)
                                    if next_button:
                                        break
                                except:
                                    continue
                            
                            if next_button:
                                # Scroll to button
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                                time.sleep(1)
                                next_button.click()
                                print(f"  → Gehe zu Seite {current_page + 1}...")
                                time.sleep(4)  # Wait for next page to load
                                current_page += 1
                            else:
                                print("  ⚠ Keine weitere Seite gefunden")
                                break
                                
                        except Exception as e:
                            print(f"  ⚠ Keine weitere Seite: {e}")
                            break
                    else:
                        break
                        
                except Exception as e:
                    print(f"  ❌ Fehler beim Laden der Seite: {e}")
                    break
            
            print(f"\n✓ Total {len(all_listings)} Listings von {current_page} Seite(n) extrahiert\n")
            
            # 🗺️ Calculate REAL distances with Google Maps
            print("🗺️ Berechne echte Distanzen mit Google Maps...")
            try:
                from google_maps_distance import GoogleMapsDistance
                
                maps = GoogleMapsDistance()
                if maps.api_key:
                    # Get search origin from config
                    origin = self.config['search_parameters']['location']
                    
                    # Ensure origin has country for Google Maps
                    if ',' not in origin:
                        origin = f"{origin}, Switzerland"
                    
                    # Calculate distances for all listings
                    # Use 'title' as address (subtitle is often empty)
                    all_listings = maps.add_distances_to_listings(origin, all_listings, address_key='title')
                    
                    print(f"✅ Distanzen berechnet!\n")
                    
                    # 🎯 WICHTIG: Sortiere nach Distanz und nehme nur die nächsten!
                    # Filter out listings without real_distance_km first
                    listings_with_distance = [l for l in all_listings if 'real_distance_km' in l]
                    listings_without_distance = [l for l in all_listings if 'real_distance_km' not in l]
                    
                    # Sort by distance (closest first)
                    listings_with_distance.sort(key=lambda x: x['real_distance_km'])
                    
                    # Combine: closest first, then others
                    all_listings = listings_with_distance + listings_without_distance
                    
                    print(f"📍 Sortiert nach Distanz (nächste zuerst)\n")
                else:
                    print("⚠️ Google Maps API Key nicht gefunden!")
                    print("   → Setze GOOGLE_MAPS_API_KEY environment variable")
                    print("   → Siehe: GOOGLE_MAPS_API_SETUP.md\n")
                    print("   Fahre ohne Distanz-Filterung fort...\n")
            except ImportError:
                print("⚠️ google_maps_distance.py nicht gefunden!")
                print("   Fahre ohne Distanz-Filterung fort...\n")
            except Exception as e:
                print(f"⚠️ Google Maps Fehler: {e}")
                print("   Fahre ohne Distanz-Filterung fort...\n")
            
            # Now filter the extracted data
            print("🔍 Filtere Listings...")
            for idx, data in enumerate(all_listings[:self.config['output']['max_results']], 1):
                # DEBUG: Show distance for non-Leukerbad
                if 'leukerbad' not in data.get('title', '').lower():
                    dist = data.get('real_distance_km', data.get('distance_km', 'NONE'))
                    print(f"  [{idx}/{min(len(all_listings), self.config['output']['max_results'])}] 🗺️ {data.get('title', 'NO TITLE')[:30]} = {dist} km ", end='')
                else:
                    print(f"  [{idx}/{min(len(all_listings), self.config['output']['max_results'])}] ", end='')
                
                # Apply basic filters first
                passed, reason = self.filter_results(data, debug=True)
                if not passed:
                    print(f"❌ {reason}")
                    filter_reasons[reason] = filter_reasons.get(reason, 0) + 1
                    continue
                
                # Get detailed info including amenities
                print(f"Lade Details... ", end='')
                details = self.get_listing_details(data['url'])
                data.update(details)
                
                # 🤖 AI Review Analysis (if reviews available)
                if data.get('reviews') and len(data['reviews']) >= 3:
                    try:
                        from review_analyzer import ReviewAnalyzer
                        
                        # Initialize analyzer (only once)
                        if not hasattr(self, 'review_analyzer'):
                            self.review_analyzer = ReviewAnalyzer()
                        
                        if self.review_analyzer.api_key:
                            print(f"🤖 Analysiere Reviews... ", end='')
                            analysis = self.review_analyzer.analyze_reviews(
                                data['reviews'], 
                                data['title']
                            )
                            data['review_analysis'] = analysis
                            print(f"✓ ", end='')
                    except ImportError:
                        pass
                    except Exception as e:
                        print(f"⚠️ Review-Analyse Fehler: {e} ", end='')
                
                # Apply amenity filters
                passed, reason = self.filter_results(data, debug=True)
                if not passed:
                    print(f"❌ {reason}")
                    filter_reasons[reason] = filter_reasons.get(reason, 0) + 1
                    continue
                
                self.results.append(data)
                print(f"✓ {data['title'][:50]}...")
            
            print(f"\n✅ {len(self.results)} passende Listings gefunden!")
            
            # Print filter summary
            if filter_reasons:
                print("\n📊 Filter-Statistik:")
                for reason, count in sorted(filter_reasons.items(), key=lambda x: x[1], reverse=True):
                    print(f"  • {reason}: {count}x")
            
        except Exception as e:
            print(f"\n❌ Fehler beim Suchen: {e}")
        
        finally:
            if self.driver:
                self.driver.quit()
    
    def save_results(self):
        """Save results to CSV and HTML"""
        if not self.results:
            print("⚠ Keine Ergebnisse zum Speichern")
            return
        
        # Create results directory if it doesn't exist
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save to CSV
        if self.config['output']['save_to_csv']:
            df = pd.DataFrame(self.results)
            csv_path = results_dir / f"airbnb_results_{timestamp}.csv"
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"💾 CSV gespeichert: {csv_path}")
        
        # Save to HTML
        if self.config['output']['save_to_html']:
            html_path = results_dir / f"airbnb_results_{timestamp}.html"
            self.generate_html_report(str(html_path))
            print(f"📄 HTML-Report gespeichert: {html_path}")
    
    def generate_html_report(self, output_path: str):
        """Generate HTML report with results"""
        html = f"""
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Airbnb Suchergebnisse</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f7f7f7;
        }}
        h1 {{
            color: #FF5A5F;
            text-align: center;
        }}
        .summary {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .listing {{
            background: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .listing h2 {{
            color: #484848;
            margin-top: 0;
        }}
        .price {{
            font-size: 24px;
            color: #FF5A5F;
            font-weight: bold;
        }}
        .rating {{
            display: inline-block;
            background: #008489;
            color: white;
            padding: 5px 10px;
            border-radius: 4px;
            font-weight: bold;
        }}
        .badge {{
            display: inline-block;
            background: #00A699;
            color: white;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 12px;
            margin-right: 5px;
        }}
        .amenity {{
            display: inline-block;
            background: #f0f0f0;
            padding: 5px 10px;
            border-radius: 4px;
            margin: 5px 5px 5px 0;
            font-size: 14px;
        }}
        .amenity.yes {{
            background: #d4edda;
            color: #155724;
        }}
        a {{
            color: #FF5A5F;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .image-gallery {{
            margin: 20px 0;
        }}
        .gallery-main {{
            width: 100%;
            max-height: 500px;
            overflow: hidden;
            border-radius: 12px;
            margin-bottom: 10px;
            background: #f0f0f0;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .main-image {{
            width: 100%;
            max-height: 500px;
            object-fit: contain;
            transition: transform 0.3s ease;
        }}
        .main-image:hover {{
            transform: scale(1.02);
        }}
        .gallery-thumbnails {{
            display: flex;
            gap: 10px;
            overflow-x: auto;
            padding: 5px 0;
        }}
        .thumbnail {{
            width: 100px;
            height: 100px;
            object-fit: cover;
            border-radius: 8px;
            cursor: pointer;
            opacity: 0.6;
            transition: all 0.3s ease;
            border: 2px solid transparent;
            flex-shrink: 0;
        }}
        .thumbnail:hover {{
            opacity: 1;
            transform: scale(1.05);
        }}
        .thumbnail.active {{
            opacity: 1;
            border-color: #FF5A5F;
        }}
    </style>
</head>
<body>
    <h1>🏠 Airbnb Suchergebnisse</h1>
    
    <div class="summary">
        <h3>Suchparameter</h3>
        <p><strong>Ort:</strong> {self.config['search_parameters']['location']}</p>
        <p><strong>Check-in:</strong> {self.config['search_parameters']['check_in']}</p>
        <p><strong>Check-out:</strong> {self.config['search_parameters']['check_out']}</p>
        <p><strong>Gäste:</strong> {self.config['search_parameters']['guests']}</p>
        <p><strong>Gefundene Listings:</strong> {len(self.results)}</p>
        <p><strong>Generiert:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</p>
    </div>
"""
        
        for idx, listing in enumerate(self.results, 1):
            # Generate image gallery HTML if multiple images exist
            image_html = ""
            image_urls = listing.get('image_urls', [])
            
            if len(image_urls) >= 5:  # Multi-image gallery
                image_html = f"""
        <div class="image-gallery">
            <div class="gallery-main" style="position: relative;">
                <img src="{image_urls[0]}" alt="{listing['title']}" class="main-image" id="mainImage{idx}">
                <button onclick="prevImage{idx}()" style="position: absolute; left: 10px; top: 50%; transform: translateY(-50%); background: rgba(0,0,0,0.5); color: white; border: none; font-size: 24px; padding: 10px 15px; cursor: pointer; border-radius: 5px;">❮</button>
                <button onclick="nextImage{idx}()" style="position: absolute; right: 10px; top: 50%; transform: translateY(-50%); background: rgba(0,0,0,0.5); color: white; border: none; font-size: 24px; padding: 10px 15px; cursor: pointer; border-radius: 5px;">❯</button>
                <div style="position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.5); color: white; padding: 5px 10px; border-radius: 5px; font-size: 12px;" id="imageCounter{idx}">1 / {len(image_urls[:20])}</div>
            </div>
            <div class="gallery-thumbnails">
"""
                for i, img_url in enumerate(image_urls[:20]):  # Max 20
                    active_class = "active" if i == 0 else ""
                    image_html += f"""
                <img src="{img_url}" alt="{listing['title']} {i+1}" 
                     class="thumbnail {active_class}" 
                     onclick="switchImage{idx}({i})">
"""
                
                image_html += f"""
            </div>
        </div>
        <script>
        (function() {{
            let currentIndex{idx} = 0;
            const images{idx} = {image_urls[:20]};
            const totalImages{idx} = images{idx}.length;
            
            window.switchImage{idx} = function(index) {{
                currentIndex{idx} = index;
                document.getElementById('mainImage{idx}').src = images{idx}[index];
                document.getElementById('imageCounter{idx}').textContent = (index + 1) + ' / ' + totalImages{idx};
                
                // Update active thumbnail
                document.querySelectorAll('#listing{idx} .thumbnail').forEach((t, i) => {{
                    t.classList.toggle('active', i === index);
                }});
            }};
            
            window.nextImage{idx} = function() {{
                currentIndex{idx} = (currentIndex{idx} + 1) % totalImages{idx};
                switchImage{idx}(currentIndex{idx});
            }};
            
            window.prevImage{idx} = function() {{
                currentIndex{idx} = (currentIndex{idx} - 1 + totalImages{idx}) % totalImages{idx};
                switchImage{idx}(currentIndex{idx});
            }};
            
            // Keyboard navigation (arrow keys) - only when gallery is in view
            let gallery{idx} = document.getElementById('listing{idx}');
            let isInView{idx} = false;
            
            // Detect if gallery is in viewport
            function checkVisibility{idx}() {{
                let rect = gallery{idx}.getBoundingClientRect();
                isInView{idx} = rect.top >= 0 && rect.bottom <= window.innerHeight;
            }}
            
            window.addEventListener('scroll', checkVisibility{idx});
            checkVisibility{idx}();
            
            // Focus gallery on click
            gallery{idx}.addEventListener('click', function() {{
                isInView{idx} = true;
            }});
            
            document.addEventListener('keydown', function(e) {{
                if (!isInView{idx}) return;
                
                if (e.key === 'ArrowRight') {{
                    e.preventDefault();
                    nextImage{idx}();
                }} else if (e.key === 'ArrowLeft') {{
                    e.preventDefault();
                    prevImage{idx}();
                }}
            }});
        }})();
        </script>
"""
            elif listing.get('image_url'):  # Single image fallback
                image_html = f"""
        <div style="margin: 15px 0;">
            <img src="{listing['image_url']}" alt="{listing['title']}" style="width: 100%; max-width: 600px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        </div>
"""
            
            html += f"""
    <div class="listing" id="listing{idx}">
        <h2>{idx}. {listing['title']}</h2>
        <p>{listing['subtitle']}</p>
        
        {image_html}
        
        <div style="margin: 15px 0;">
            <span class="price">CHF {listing['price_per_night']}</span> pro Nacht
        </div>
        
        <div style="margin: 15px 0;">
"""
            if listing['rating']:
                html += f'<span class="rating">⭐ {listing["rating"]}</span> '
            
            html += f'<span>({listing["num_reviews"]} Bewertungen)</span> '
            
            if listing['is_superhost']:
                html += '<span class="badge">SUPERHOST</span>'
            
            html += """
        </div>
        
        <div style="margin: 15px 0;">
            <strong>Ausstattung:</strong><br>
"""
            
            amenities_html = []
            if listing.get('has_private_pool'):
                amenities_html.append('<span class="amenity yes">🏊 Privater Pool</span>')
            if listing.get('has_private_whirlpool'):
                amenities_html.append('<span class="amenity yes">🛁 Whirlpool</span>')
            if listing.get('has_private_sauna'):
                amenities_html.append('<span class="amenity yes">🧖 Sauna</span>')
            if listing.get('has_fireplace'):
                amenities_html.append('<span class="amenity yes">🔥 Kamin</span>')
            if listing.get('has_parking'):
                amenities_html.append('<span class="amenity yes">🅿️ Parkplatz</span>')
            
            if amenities_html:
                html += "\n            ".join(amenities_html)
            else:
                html += '<span class="amenity">Keine speziellen Ausstattungsmerkmale gefunden</span>'
            
            html += f"""
        </div>
"""
            
            # 🤖 AI Review Analysis
            if listing.get('review_analysis'):
                analysis = listing['review_analysis']
                sentiment_emoji = {
                    'excellent': '😍',
                    'good': '😊',
                    'mixed': '😐',
                    'poor': '😞',
                    'unknown': '❓'
                }.get(analysis.get('rating_sentiment', 'unknown'), '❓')
                
                html += f"""
        <div style="margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #FF5A5F;">
            <h4 style="margin-top: 0;">🤖 KI-Review-Analyse ({len(listing.get('reviews', []))} Reviews)</h4>
            
            <div style="margin: 10px 0;">
                <strong style="color: #155724;">✅ POSITIV:</strong>
                <ul style="margin: 5px 0;">
"""
                
                for point in analysis.get('positive', [])[:5]:  # Max 5 points
                    html += f"                    <li>{point}</li>\n"
                
                html += """
                </ul>
            </div>
            
            <div style="margin: 10px 0;">
                <strong style="color: #721c24;">⚠️ NEGATIV:</strong>
                <ul style="margin: 5px 0;">
"""
                
                for point in analysis.get('negative', [])[:5]:  # Max 5 points
                    html += f"                    <li>{point}</li>\n"
                
                html += f"""
                </ul>
            </div>
            
            <div style="margin: 10px 0; padding: 10px; background: white; border-radius: 6px;">
                <strong>📝 ZUSAMMENFASSUNG:</strong>
                <p style="margin: 5px 0;">{analysis.get('summary', 'Keine Zusammenfassung verfügbar')}</p>
            </div>
            
            <div style="margin: 10px 0;">
                <strong>Sentiment:</strong> <span style="font-size: 20px;">{sentiment_emoji} {analysis.get('rating_sentiment', 'unknown').upper()}</span>
            </div>
        </div>
"""
            
            html += f"""
        <p><a href="{listing['url']}" target="_blank">🔗 Listing auf Airbnb öffnen</a></p>
    </div>
"""
        
        html += """
</body>
</html>
"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)


def main():
    """Main execution function"""
    searcher = AirbnbSearcher()
    searcher.search()
    searcher.save_results()
    
    print("\n" + "=" * 60)
    print("✅ Fertig!")


if __name__ == "__main__":
    main()
