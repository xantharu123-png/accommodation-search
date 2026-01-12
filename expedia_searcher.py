#!/usr/bin/env python3
"""
Expedia Scraper
Sucht Hotels auf Expedia.com (Expedia Group - wie Hotels.com)
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


class ExpediaSearcher:
    def __init__(self, config_path: str = None):
        """Initialize Expedia searcher"""
        if config_path:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        
        self.driver = None
        self.results = []
        
    def setup_driver(self):
        """Setup Chrome driver"""
        chrome_options = Options()
        
        if self.config.get('scraping_settings', {}).get('headless', True):
            chrome_options.add_argument('--headless=new')
        
        chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def build_search_url(self) -> str:
        """Build Expedia search URL for Swiss locale"""
        params = self.config['search_parameters']
        
        # Swiss Expedia (same company as Hotels.com)
        base_url = "https://www.expedia.ch/Hotel-Search"
        
        from datetime import datetime
        checkin = datetime.strptime(params['check_in'], '%Y-%m-%d')
        checkout = datetime.strptime(params['check_out'], '%Y-%m-%d')
        
        url_params = {
            'destination': params['location'],
            'startDate': checkin.strftime('%Y-%m-%d'),
            'endDate': checkout.strftime('%Y-%m-%d'),
            'rooms': '1',
            'adults': str(params['guests']),
            'locale': 'de_CH',
            'regionId': '6252001'  # Switzerland region
        }
        
        url = base_url + '?' + '&'.join([f"{k}={v}" for k, v in url_params.items()])
        
        filters = self.config.get('filters', {})
        if filters.get('max_price'):
            url += f"&price={filters['max_price']}"
        
        return url
    
    def handle_popups(self):
        """Handle popups"""
        try:
            cookie_btn = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            )
            cookie_btn.click()
            print("✓ Cookie-Banner akzeptiert")
            time.sleep(1)
        except:
            pass
    
    def extract_hotel_data(self, hotel_card) -> Optional[Dict]:
        """Extract hotel data"""
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
            }
            
            # Name
            try:
                name_elem = hotel_card.find_element(By.CSS_SELECTOR, "[data-stid='content-hotel-title']")
                data['name'] = name_elem.text.strip()
            except:
                pass
            
            # Price
            try:
                price_elem = hotel_card.find_element(By.CSS_SELECTOR, "[data-stid='price-display']")
                price_text = price_elem.text.strip()
                price_match = re.search(r'[\d\s]+', price_text.replace('.', '').replace(' ', ''))
                if price_match:
                    data['price_per_night'] = int(price_match.group(0))
            except:
                pass
            
            # Rating (10-point scale)
            try:
                rating_elem = hotel_card.find_element(By.CSS_SELECTOR, "[data-stid='review-rating']")
                rating_text = rating_elem.text.strip()
                rating_match = re.search(r'(\d+[,.]?\d*)', rating_text)
                if rating_match:
                    expedia_rating = float(rating_match.group(1).replace(',', '.'))
                    data['rating'] = round(expedia_rating / 2, 2)
            except:
                pass
            
            # Reviews
            try:
                reviews_elem = hotel_card.find_element(By.CSS_SELECTOR, "[data-stid='review-text']")
                reviews_text = reviews_elem.text.strip()
                reviews_match = re.search(r'(\d+)', reviews_text)
                if reviews_match:
                    data['num_reviews'] = int(reviews_match.group(1))
            except:
                pass
            
            # URL
            try:
                link = hotel_card.find_element(By.TAG_NAME, "a")
                data['url'] = link.get_attribute('href')
            except:
                pass
            
            # Images - SCRAPE MULTIPLE (5-20)!
            try:
                image_elements = hotel_card.find_elements(By.TAG_NAME, "img")
                
                image_urls = []
                for img in image_elements[:20]:
                    img_url = img.get_attribute('src')
                    if img_url and 'images' in img_url and img_url not in image_urls:
                        # Get high-res version
                        img_url = img_url.replace('t_70x70', 't_1000x1000')
                        img_url = img_url.replace('t_200x200', 't_1000x1000')
                        image_urls.append(img_url)
                
                if image_urls:
                    data['image_urls'] = image_urls
                    data['image_url'] = image_urls[0]
                else:
                    # Fallback
                    try:
                        img = hotel_card.find_element(By.TAG_NAME, "img")
                        data['image_url'] = img.get_attribute('src')
                    except:
                        pass
            except:
                pass
            
            return data
            
        except Exception as e:
            return None
    
    def search(self):
        """Perform search"""
        print("🏨 Starte Expedia Suche...")
        print("=" * 60)
        
        self.setup_driver()
        
        try:
            search_url = self.build_search_url()
            print(f"📍 Suche: {self.config['search_parameters']['location']}")
            print(f"🔗 URL: {search_url}\n")
            
            self.driver.get(search_url)
            time.sleep(8)  # Wait longer
            
            self.handle_popups()
            
            print("📜 Lade Ergebnisse...")
            time.sleep(5)
            
            # Scroll multiple times
            for i in range(5):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            # Find hotels - Try MULTIPLE selector strategies (same as Hotels.com)
            hotels = []
            
            # Strategy 1: Modern data-stid selectors
            selectors_strategy1 = [
                "div[data-stid='lodging-card-responsive']",
                "div[data-testid='property-card']",
            ]
            
            # Strategy 2: Class-based selectors  
            selectors_strategy2 = [
                "div[class*='uitk-card']",
                "div[class*='property-card']",
                "div[class*='hotel-card']",
            ]
            
            # Strategy 3: Semantic HTML
            selectors_strategy3 = [
                "article",
                "section[role='article']",
                "li[role='article']",
            ]
            
            # Strategy 4: Generic containers with links
            selectors_strategy4 = [
                "a[href*='Hotel-Information']",
                "a[href*='/h/']",
            ]
            
            print("🔍 Suche Hotels mit Schweizer Selectors...")
            
            # Try each strategy
            all_strategies = [
                ("Strategy 1 (data-stid)", selectors_strategy1),
                ("Strategy 2 (classes)", selectors_strategy2),
                ("Strategy 3 (semantic)", selectors_strategy3),
                ("Strategy 4 (links)", selectors_strategy4),
            ]
            
            for strategy_name, selectors in all_strategies:
                for selector in selectors:
                    try:
                        found = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if len(found) > 3:  # Need at least 4 elements
                            hotels = found
                            print(f"✓ {len(hotels)} Elemente gefunden ({strategy_name}: {selector})\n")
                            break
                    except Exception as e:
                        continue
                
                if hotels:
                    break
            
            # Fallback: Get ALL links and filter
            if not hotels:
                print("⚠ Kein Selector funktioniert! Versuche Fallback...")
                try:
                    # Get page HTML and check what's actually there
                    page_source = self.driver.page_source
                    
                    # Save for debugging
                    with open('/tmp/expedia_debug.html', 'w', encoding='utf-8') as f:
                        f.write(page_source)
                    print("📝 Debug HTML saved to /tmp/expedia_debug.html")
                    
                    # Check if we're blocked
                    if 'captcha' in page_source.lower() or 'blocked' in page_source.lower():
                        print("🚫 BLOCKED! Expedia hat uns erkannt!")
                        return
                    
                    # Try to find ANY hotel elements
                    all_divs = self.driver.find_elements(By.TAG_NAME, "div")
                    print(f"📊 Gefunden: {len(all_divs)} DIVs auf der Seite")
                    
                    # Filter DIVs that look like hotel cards
                    for div in all_divs:
                        try:
                            text = div.text
                            # Hotel cards usually have: name, price, rating
                            if 'CHF' in text and len(text) > 50 and len(text) < 1000:
                                hotels.append(div)
                                if len(hotels) >= 20:
                                    break
                        except:
                            continue
                    
                    if hotels:
                        print(f"✓ Fallback: {len(hotels)} Hotel-ähnliche Elemente gefunden\n")
                    
                except Exception as e:
                    print(f"❌ Fallback fehlgeschlagen: {e}")
            
            if not hotels:
                print("⚠ Keine Hotels gefunden!\n")
                return
            
            # Extract
            all_hotels = []
            max_results = min(len(hotels), self.config['output'].get('max_results', 50))
            
            for idx, hotel in enumerate(hotels[:max_results], 1):
                print(f"  [{idx}/{max_results}] ", end='', flush=True)
                
                data = self.extract_hotel_data(hotel)
                
                if data and data['name'] != "N/A":
                    all_hotels.append(data)
                    print(f"✓ {data['name'][:50]}")
                else:
                    print("❌")
                
                time.sleep(0.3)
            
            print(f"\n✓ {len(all_hotels)} Hotels extrahiert")
            
            # Filter
            self.results = self.filter_hotels(all_hotels)
            
            print(f"\n✅ {len(self.results)} passende Hotels!")
            
        finally:
            if self.driver:
                self.driver.quit()
    
    def filter_hotels(self, hotels: List[Dict]) -> List[Dict]:
        """Filter hotels"""
        filtered = []
        filters = self.config.get('filters', {})
        
        for hotel in hotels:
            if filters.get('max_price') and hotel['price_per_night'] > filters['max_price']:
                continue
            
            if hotel['rating'] and hotel['rating'] < filters.get('min_rating', 0):
                continue
            
            if hotel['num_reviews'] < filters.get('min_reviews', 0):
                continue
            
            filtered.append(hotel)
        
        return filtered
    
    def save_results(self):
        """Save results"""
        if not self.results:
            return
        
        # Create results directory
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_file = results_dir / f"expedia_results_{timestamp}.csv"
        html_file = results_dir / f"expedia_results_{timestamp}.html"
        
        df = pd.DataFrame(self.results)
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        print(f"💾 CSV gespeichert: {csv_file}")
        
        # Generate HTML
        self.generate_html_report(str(html_file))
        print(f"📄 HTML-Report gespeichert: {html_file}")
    
    def generate_html_report(self, filename: str):
        """Generate HTML report with image slider"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Expedia Suchergebnisse</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #0057B8; }}
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
        .rating {{ background: #0057B8; color: white; padding: 5px 10px; border-radius: 4px; }}
        a {{ color: #0057B8; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        
        /* Image Gallery Slider */
        .image-gallery {{ margin: 20px 0; }}
        .gallery-main {{ position: relative; max-width: 800px; margin: 0 auto; }}
        .main-image {{ width: 100%; height: auto; border-radius: 8px; display: block; }}
        .gallery-main button {{
            position: absolute; top: 50%; transform: translateY(-50%);
            background: rgba(0,0,0,0.5); color: white; border: none;
            font-size: 24px; padding: 10px 15px; cursor: pointer;
            border-radius: 5px; z-index: 10;
        }}
        .gallery-main button:hover {{ background: rgba(0,0,0,0.8); }}
        .gallery-main button:first-of-type {{ left: 10px; }}
        .gallery-main button:last-of-type {{ right: 10px; }}
        .image-counter {{
            position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%);
            background: rgba(0,0,0,0.5); color: white; padding: 5px 10px;
            border-radius: 5px; font-size: 12px;
        }}
        .gallery-thumbnails {{ display: flex; gap: 10px; margin-top: 10px; overflow-x: auto; padding: 10px 0; }}
        .thumbnail {{
            width: 80px; height: 60px; object-fit: cover; border-radius: 4px;
            cursor: pointer; border: 2px solid transparent; opacity: 0.6;
            transition: all 0.3s;
        }}
        .thumbnail:hover {{ opacity: 1; transform: scale(1.05); }}
        .thumbnail.active {{ opacity: 1; border-color: #0057B8; }}
    </style>
</head>
<body>
    <h1>🏨 Expedia Suchergebnisse</h1>
    
    <div class="summary">
        <h3>Suchparameter</h3>
        <p><strong>Ort:</strong> {self.config['search_parameters']['location']}</p>
        <p><strong>Check-in:</strong> {self.config['search_parameters']['check_in']}</p>
        <p><strong>Check-out:</strong> {self.config['search_parameters']['check_out']}</p>
        <p><strong>Gäste:</strong> {self.config['search_parameters']['guests']}</p>
        <p><strong>Gefundene Hotels:</strong> {len(self.results)}</p>
        <p><strong>Generiert:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</p>
    </div>
"""
        
        for idx, listing in enumerate(self.results, 1):
            image_html = ""
            image_urls = listing.get('image_urls', [])
            
            if len(image_urls) >= 5:
                image_html = f"""
        <div class="image-gallery">
            <div class="gallery-main">
                <img src="{image_urls[0]}" alt="{listing['name']}" class="main-image" id="mainImage{idx}">
                <button onclick="prevImage{idx}()">❮</button>
                <button onclick="nextImage{idx}()">❯</button>
                <div class="image-counter" id="imageCounter{idx}">1 / {len(image_urls[:20])}</div>
            </div>
            <div class="gallery-thumbnails">
"""
                for i, img_url in enumerate(image_urls[:20]):
                    active = "active" if i == 0 else ""
                    image_html += f'<img src="{img_url}" class="thumbnail {active}" onclick="switchImage{idx}({i})">'
                
                image_html += f"""
            </div>
        </div>
        <script>
        (function() {{
            let idx{idx} = 0;
            const imgs{idx} = {image_urls[:20]};
            const total{idx} = imgs{idx}.length;
            window.switchImage{idx} = function(i) {{
                idx{idx} = i;
                document.getElementById('mainImage{idx}').src = imgs{idx}[i];
                document.getElementById('imageCounter{idx}').textContent = (i + 1) + ' / ' + total{idx};
                document.querySelectorAll('#listing{idx} .thumbnail').forEach((t, j) => t.classList.toggle('active', j === i));
            }};
            window.nextImage{idx} = function() {{ switchImage{idx}((idx{idx} + 1) % total{idx}); }};
            window.prevImage{idx} = function() {{ switchImage{idx}((idx{idx} - 1 + total{idx}) % total{idx}); }};
            document.addEventListener('keydown', function(e) {{
                if (e.key === 'ArrowRight') {{ e.preventDefault(); nextImage{idx}(); }}
                else if (e.key === 'ArrowLeft') {{ e.preventDefault(); prevImage{idx}(); }}
            }});
        }})();
        </script>
"""
            elif listing.get('image_url') and listing['image_url'] != 'N/A':
                image_html = f'<img src="{listing["image_url"]}" style="width: 100%; max-width: 800px; border-radius: 8px; margin: 15px 0;">'
            
            html += f"""
    <div class="listing" id="listing{idx}">
        <h2>{idx}. {listing['name']}</h2>
        {image_html}
        <p><span class="price">CHF {listing['price_per_night']}</span> pro Nacht</p>
        <p><span class="rating">⭐ {listing['rating'] or 'N/A'}</span> ({listing['num_reviews']} Bewertungen)</p>
        <p><a href="{listing['url']}" target="_blank">🔗 Auf Expedia ansehen</a></p>
    </div>
"""
        
        html += "</body></html>"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)


if __name__ == "__main__":
    searcher = ExpediaSearcher("search_config_Leukerbad_2026-01-10.json")
    searcher.search()
    searcher.save_results()
