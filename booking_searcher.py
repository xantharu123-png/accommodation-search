#!/usr/bin/env python3
"""
Booking.com Scraper
Sucht Hotels & Apartments auf Booking.com
"""

import json
import time
import re
from datetime import datetime
from typing import List, Dict, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import pandas as pd


class BookingSearcher:
    def __init__(self, config_path: str = None):
        """Initialize the Booking.com searcher"""
        if config_path:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        
        self.driver = None
        self.results = []
        
    def setup_driver(self):
        """Setup Chrome driver with options"""
        chrome_options = Options()
        
        if self.config.get('scraping_settings', {}).get('headless', True):
            chrome_options.add_argument('--headless=new')
        
        chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--lang=de-CH')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def build_search_url(self) -> str:
        """Build Booking.com search URL"""
        params = self.config['search_parameters']
        
        # Base URL
        base_url = "https://www.booking.com/searchresults.de.html"
        
        # URL parameters
        url_params = {
            'ss': params['location'],
            'checkin': params['check_in'],
            'checkout': params['check_out'],
            'group_adults': params['guests'],
            'no_rooms': 1,
            'group_children': 0,
        }
        
        # Build URL
        url = base_url + '?' + '&'.join([f"{k}={v}" for k, v in url_params.items()])
        
        # Add filters
        filters = self.config.get('filters', {})
        
        # Price filter - CORRECT FORMAT for CHF
        if filters.get('max_price'):
            max_price = filters['max_price']
            url += f"&price=CHF-0-CHF-{max_price}"
        
        # Entire place (apartments/homes) - CORRECT IDs
        url += "&nflt=ht_id%3D201%3Bht_id%3D204%3Bht_id%3D220"  # Apartments, Holiday Homes, Chalets
        
        # Rating filter (Booking uses 1-10 scale)
        min_rating = filters.get('min_rating', 0)
        if min_rating > 0:
            # Convert 4.6/5 to 9.2/10
            booking_min_rating = int(min_rating * 2 * 10)  # 4.6 * 2 * 10 = 92
            url += f"&review_score={booking_min_rating}"
        
        return url
    
    def handle_popups(self):
        """Handle cookie banners and popups"""
        try:
            # Cookie banner - multiple selectors
            cookie_selectors = [
                "button[id*='onetrust-accept']",
                "button[data-testid='accept-cookies']",
                "#onetrust-accept-btn-handler",
                "button.fc-cta-consent",
            ]
            
            for selector in cookie_selectors:
                try:
                    cookie_btn = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    cookie_btn.click()
                    print("✓ Cookie-Banner akzeptiert")
                    time.sleep(1)
                    return
                except:
                    continue
        except:
            pass
    
    def extract_property_data(self, property_card) -> Optional[Dict]:
        """Extract data from a single property card"""
        try:
            data = {
                'name': 'N/A',
                'location': 'N/A',
                'price_per_night': 0,
                'rating': None,
                'num_reviews': 0,
                'url': 'N/A',
                'image_url': 'N/A',
                'image_urls': [],  # Multiple images!
                'distance_km': 0,
                'property_type': 'N/A',
            }
            
            # Name
            try:
                name_elem = property_card.find_element(By.CSS_SELECTOR, "[data-testid='title']")
                data['name'] = name_elem.text.strip()
            except:
                pass
            
            # Location/Distance
            try:
                location_elem = property_card.find_element(By.CSS_SELECTOR, "[data-testid='distance']")
                location_text = location_elem.text.strip()
                data['location'] = location_text
                
                # Extract distance in km
                km_match = re.search(r'(\d+[,.]?\d*)\s*km', location_text)
                if km_match:
                    data['distance_km'] = float(km_match.group(1).replace(',', '.'))
            except:
                pass
            
            # Price
            try:
                price_elem = property_card.find_element(By.CSS_SELECTOR, "[data-testid='price-and-discounted-price']")
                price_text = price_elem.text.strip()
                
                # Extract number from "CHF 250" or "250"
                price_match = re.search(r'[\d\s]+', price_text.replace('.', '').replace(' ', ''))
                if price_match:
                    data['price_per_night'] = int(price_match.group(0))
            except:
                pass
            
            # Rating (Booking uses 1-10 scale)
            try:
                rating_elem = property_card.find_element(By.CSS_SELECTOR, "[data-testid='review-score'] div")
                rating_text = rating_elem.text.strip()
                rating_match = re.search(r'(\d+[,.]?\d*)', rating_text)
                if rating_match:
                    # Convert 8.5/10 to 4.25/5 for consistency
                    booking_rating = float(rating_match.group(1).replace(',', '.'))
                    data['rating'] = round(booking_rating / 2, 2)  # 10-point to 5-point scale
            except:
                pass
            
            # Number of reviews
            try:
                reviews_elem = property_card.find_element(By.CSS_SELECTOR, "[data-testid='review-score'] div:nth-child(2)")
                reviews_text = reviews_elem.text.strip()
                reviews_match = re.search(r'(\d+)', reviews_text)
                if reviews_match:
                    data['num_reviews'] = int(reviews_match.group(1))
            except:
                pass
            
            # URL
            try:
                link_elem = property_card.find_element(By.CSS_SELECTOR, "a[data-testid='title-link']")
                data['url'] = link_elem.get_attribute('href')
            except:
                pass
            
            # Images - SCRAPE MULTIPLE (5-20)!
            try:
                # Find all images in the property card
                image_elements = property_card.find_elements(By.CSS_SELECTOR, "img[data-testid='image']")
                
                image_urls = []
                for img in image_elements[:20]:  # Max 20 images
                    img_url = img.get_attribute('src')
                    if img_url and img_url not in image_urls:
                        # Get high-res version (replace thumbnails)
                        img_url = img_url.replace('square60', 'max1024x768')
                        img_url = img_url.replace('square240', 'max1024x768')
                        image_urls.append(img_url)
                
                if image_urls:
                    data['image_urls'] = image_urls
                    data['image_url'] = image_urls[0]  # First as fallback
                else:
                    # Fallback to single image
                    try:
                        img_elem = property_card.find_element(By.CSS_SELECTOR, "img[data-testid='image']")
                        data['image_url'] = img_elem.get_attribute('src')
                    except:
                        pass
            except:
                pass
            
            return data
            
        except Exception as e:
            print(f"❌ Error extracting property: {e}")
            return None
    
    def search(self):
        """Perform the search"""
        print("🏨 Starte Booking.com Suche...")
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
            
            # Handle popups
            self.handle_popups()
            
            # Wait for results
            print("📜 Lade Suchergebnisse...")
            time.sleep(3)
            
            # Scroll to load more results
            for i in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            # Find property cards
            property_selectors = [
                "[data-testid='property-card']",
                "[data-testid='property-card-container']",
                "div[data-testid*='property']",
            ]
            
            properties = []
            for selector in property_selectors:
                try:
                    properties = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if len(properties) > 5:
                        print(f"✓ {len(properties)} Unterkünfte gefunden\n")
                        break
                except:
                    continue
            
            if not properties:
                print("⚠ Keine Unterkünfte gefunden!")
                return
            
            # Extract data
            print("🔍 Extrahiere Daten...")
            all_properties = []
            
            max_results = min(len(properties), self.config['output'].get('max_results', 50))
            
            for idx, prop in enumerate(properties[:max_results], 1):
                print(f"  [{idx}/{max_results}] ", end='', flush=True)
                
                data = self.extract_property_data(prop)
                
                if data and data['name'] != "N/A":
                    all_properties.append(data)
                    print(f"✓ {data['name'][:50]}")
                else:
                    print("❌")
                
                time.sleep(0.5)
            
            print(f"\n✓ {len(all_properties)} Unterkünfte extrahiert")
            
            # Filter properties
            print("\n🔍 Filtere Unterkünfte...")
            self.results = self.filter_properties(all_properties)
            
            print(f"\n✅ {len(self.results)} passende Unterkünfte gefunden!")
            
        finally:
            if self.driver:
                self.driver.quit()
    
    def filter_properties(self, properties: List[Dict]) -> List[Dict]:
        """Filter properties based on criteria"""
        filtered = []
        filters = self.config.get('filters', {})
        
        # Get radius in km
        radius_km = self.config.get('location_settings', {}).get('radius_km', 999)
        
        for idx, prop in enumerate(properties, 1):
            print(f"  [{idx}/{len(properties)}] ", end='', flush=True)
            
            # Price filter - CRITICAL: Filter in Python since URL filter doesn't work!
            max_price = filters.get('max_price', 999999)
            if prop['price_per_night'] > max_price:
                print(f"❌ Preis: CHF {prop['price_per_night']} > {max_price}")
                continue
            
            # Distance filter
            if prop['distance_km'] > radius_km:
                print(f"❌ Distanz: {prop['distance_km']} km > {radius_km} km")
                continue
            
            # Rating filter (convert to 5-point scale)
            min_rating = filters.get('min_rating', 0)
            if prop['rating'] and prop['rating'] < min_rating:
                print(f"❌ Rating: {prop['rating']} < {min_rating}")
                continue
            
            # Reviews filter
            min_reviews = filters.get('min_reviews', 0)
            if prop['num_reviews'] < min_reviews:
                print(f"❌ Reviews: {prop['num_reviews']} < {min_reviews}")
                continue
            
            print(f"✓ {prop['name'][:40]}")
            filtered.append(prop)
        
        return filtered
    
    def save_results(self):
        """Save results to CSV and HTML"""
        if not self.results:
            print("⚠ Keine Ergebnisse zum Speichern!")
            return
        
        # Create results directory
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        
        # Create DataFrame
        df = pd.DataFrame(self.results)
        
        # Generate filenames
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_file = results_dir / f"booking_results_{timestamp}.csv"
        html_file = results_dir / f"booking_results_{timestamp}.html"
        
        # Save CSV
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        print(f"💾 CSV gespeichert: {csv_file}")
        
        # Generate HTML report
        self.generate_html_report(str(html_file))
        print(f"📄 HTML-Report gespeichert: {html_file}")
    
    def generate_html_report(self, filename: str):
        """Generate HTML report with image slider"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Booking.com Suchergebnisse</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #003580; }}
        .summary {{
            background: white;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .listing {{ 
            background: white; 
            padding: 20px; 
            margin: 20px 0; 
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .price {{ color: #008009; font-weight: bold; font-size: 24px; }}
        .rating {{ background: #003580; color: white; padding: 5px 10px; border-radius: 4px; }}
        a {{ color: #003580; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        
        /* Image Gallery Slider */
        .image-gallery {{ margin: 20px 0; }}
        .gallery-main {{ 
            position: relative; 
            max-width: 800px; 
            margin: 0 auto;
        }}
        .main-image {{ 
            width: 100%; 
            height: auto; 
            border-radius: 8px; 
            display: block;
        }}
        .gallery-main button {{
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(0,0,0,0.5);
            color: white;
            border: none;
            font-size: 24px;
            padding: 10px 15px;
            cursor: pointer;
            border-radius: 5px;
            z-index: 10;
        }}
        .gallery-main button:hover {{ background: rgba(0,0,0,0.8); }}
        .gallery-main button:first-of-type {{ left: 10px; }}
        .gallery-main button:last-of-type {{ right: 10px; }}
        .image-counter {{
            position: absolute;
            bottom: 10px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.5);
            color: white;
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 12px;
        }}
        .gallery-thumbnails {{
            display: flex;
            gap: 10px;
            margin-top: 10px;
            overflow-x: auto;
            padding: 10px 0;
        }}
        .thumbnail {{
            width: 80px;
            height: 60px;
            object-fit: cover;
            border-radius: 4px;
            cursor: pointer;
            border: 2px solid transparent;
            opacity: 0.6;
            transition: all 0.3s;
        }}
        .thumbnail:hover {{ opacity: 1; transform: scale(1.05); }}
        .thumbnail.active {{ opacity: 1; border-color: #003580; }}
    </style>
</head>
<body>
    <h1>🏨 Booking.com Suchergebnisse</h1>
    
    <div class="summary">
        <h3>Suchparameter</h3>
        <p><strong>Ort:</strong> {self.config['search_parameters']['location']}</p>
        <p><strong>Check-in:</strong> {self.config['search_parameters']['check_in']}</p>
        <p><strong>Check-out:</strong> {self.config['search_parameters']['check_out']}</p>
        <p><strong>Gäste:</strong> {self.config['search_parameters']['guests']}</p>
        <p><strong>Gefundene Unterkünfte:</strong> {len(self.results)}</p>
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
                <img src="{image_urls[0]}" alt="{listing['name']}" class="main-image" id="mainImage{idx}">
                <button onclick="prevImage{idx}()">❮</button>
                <button onclick="nextImage{idx}()">❯</button>
                <div class="image-counter" id="imageCounter{idx}">1 / {len(image_urls[:20])}</div>
            </div>
            <div class="gallery-thumbnails">
"""
                for i, img_url in enumerate(image_urls[:20]):  # Max 20
                    active_class = "active" if i == 0 else ""
                    image_html += f"""
                <img src="{img_url}" alt="{listing['name']} {i+1}" 
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
            
            let gallery{idx} = document.getElementById('listing{idx}');
            let isInView{idx} = false;
            
            function checkVisibility{idx}() {{
                let rect = gallery{idx}.getBoundingClientRect();
                isInView{idx} = rect.top >= 0 && rect.bottom <= window.innerHeight;
            }}
            
            window.addEventListener('scroll', checkVisibility{idx});
            checkVisibility{idx}();
            
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
            elif listing.get('image_url') and listing['image_url'] != 'N/A':  # Single image
                image_html = f"""
        <div style="margin: 15px 0;">
            <img src="{listing['image_url']}" alt="{listing['name']}" style="width: 100%; max-width: 800px; border-radius: 8px;">
        </div>
"""
            
            html += f"""
    <div class="listing" id="listing{idx}">
        <h2>{idx}. {listing['name']}</h2>
        <p>📍 {listing['location']}</p>
        
        {image_html}
        
        <p><span class="price">CHF {listing['price_per_night']}</span> pro Nacht</p>
        <p><span class="rating">⭐ {listing['rating'] or 'N/A'}</span> ({listing['num_reviews']} Bewertungen)</p>
        <p><a href="{listing['url']}" target="_blank">🔗 Auf Booking.com ansehen</a></p>
    </div>
"""
        
        html += """
</body>
</html>
"""
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)


if __name__ == "__main__":
    # Test with config
    searcher = BookingSearcher("search_config_Leukerbad_2026-01-10.json")
    searcher.search()
    searcher.save_results()
