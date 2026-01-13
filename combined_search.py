#!/usr/bin/env python3
"""
Combined Accommodation Search
Sucht auf ALLEN Plattformen: Airbnb, Booking.com, Hotels.com
"""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path


class CombinedAccommodationSearch:
    def __init__(self, config_path: str):
        """Initialize combined search"""
        self.config_path = config_path
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.all_results = {
            'airbnb': [],
            'booking': [],
            'google_hotels': [],
        }
    
    def run(self):
        """Run all searches"""
        print("\n🔍 Starte Combined Search auf ALLEN Plattformen...")
        print("=" * 60)
        print("Plattformen:")
        print("  1. 🏠 Airbnb")
        print("  2. 🏨 Booking.com")
        print("  3. 🌐 Google Hotels (Alle Hotel-Plattformen!)")
        print("=" * 60)
        print()
        
        # 1. Airbnb
        print("\n" + "=" * 60)
        print("1/4 🏠 AIRBNB")
        print("=" * 60)
        try:
            from airbnb_searcher import AirbnbSearcher
            airbnb = AirbnbSearcher(self.config_path)
            airbnb.search()
            self.all_results['airbnb'] = airbnb.results
            print(f"✅ Airbnb: {len(airbnb.results)} Listings")
        except Exception as e:
            print(f"❌ Airbnb Fehler: {e}")
        
        # 2. Booking.com
        print("\n" + "=" * 60)
        print("2/4 🏨 BOOKING.COM")
        print("=" * 60)
        try:
            from booking_searcher import BookingSearcher
            booking = BookingSearcher(self.config_path)
            booking.search()
            self.all_results['booking'] = booking.results
            print(f"✅ Booking.com: {len(booking.results)} Properties")
        except Exception as e:
            print(f"❌ Booking.com Fehler: {e}")
        
        # 3. Google Hotels (replaces Hotels.com + Expedia)
        print("\n" + "=" * 60)
        print("3/3 🌐 GOOGLE HOTELS")
        print("=" * 60)
        try:
            from google_hotels_searcher import GoogleHotelsSearcher
            google_hotels = GoogleHotelsSearcher(self.config_path)
            google_hotels.search()
            self.all_results['google_hotels'] = google_hotels.results
            print(f"✅ Google Hotels: {len(google_hotels.results)} Hotels")
        except Exception as e:
            print(f"❌ Google Hotels Fehler: {e}")
        
        # Generate comparison report
        self.generate_comparison_report()
    
    def generate_comparison_report(self):
        """Generate comprehensive comparison report"""
        print("\n" + "=" * 60)
        print("📊 ERSTELLE VERGLEICHSREPORT...")
        print("=" * 60)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Combine all results
        combined_data = []
        
        # Airbnb
        for listing in self.all_results['airbnb']:
            combined_data.append({
                'platform': 'Airbnb',
                'name': listing.get('title', 'N/A'),
                'location': listing.get('subtitle', 'N/A'),
                'price': listing.get('price_per_night', 0),
                'rating': listing.get('rating', 0),
                'reviews': listing.get('num_reviews', 0),
                'url': listing.get('url', ''),
                'distance_km': listing.get('real_distance_km', 0),
                'image_url': listing.get('image_url', ''),
                'image_urls': listing.get('image_urls', []),  # ✅ FIX: Multi-images
                'bedrooms': listing.get('bedrooms', 'N/A'),  # ✅ FIX: Bedrooms
                'max_guests': listing.get('max_guests', 'N/A'),  # ✅ FIX: Guests
            })
        
        # Booking.com
        for listing in self.all_results['booking']:
            combined_data.append({
                'platform': 'Booking.com',
                'name': listing.get('name', 'N/A'),
                'location': listing.get('location', 'N/A'),
                'price': listing.get('price_per_night', 0),
                'rating': listing.get('rating', 0),
                'reviews': listing.get('num_reviews', 0),
                'url': listing.get('url', ''),
                'distance_km': listing.get('distance_km', 0),
                'image_url': listing.get('image_url', ''),
                'image_urls': listing.get('image_urls', []),  # ✅ FIX: Multi-images
                'bedrooms': 'N/A',  # Booking doesn't have this
                'max_guests': 'N/A',  # Booking doesn't have this
            })
        
        # Google Hotels (replaces Hotels.com + Expedia)
        for listing in self.all_results['google_hotels']:
            combined_data.append({
                'platform': 'Google Hotels',
                'name': listing.get('name', 'N/A'),
                'location': listing.get('location', 'N/A'),
                'price': listing.get('price_per_night', 0),
                'rating': listing.get('rating', 0),
                'reviews': listing.get('num_reviews', 0),
                'url': listing.get('url', ''),
                'distance_km': listing.get('distance_km', 0),
                'image_url': listing.get('image_url', ''),
                'image_urls': listing.get('image_urls', []),
                'bedrooms': 'N/A',
                'max_guests': 'N/A',
            })
        
        if not combined_data:
            print("⚠ Keine Ergebnisse gefunden!")
            return
        
        # Create results directory
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        
        # Create DataFrame
        df = pd.DataFrame(combined_data)
        
        # Sort by price
        df = df.sort_values('price')
        
        # Save CSV
        csv_file = results_dir / f"combined_results_{timestamp}.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        print(f"💾 CSV gespeichert: {csv_file}")
        
        # Generate HTML
        html_file = results_dir / f"combined_results_{timestamp}.html"
        self.generate_html_report(df, str(html_file))
        
        # Print summary
        print("\n📊 ZUSAMMENFASSUNG:")
        print("=" * 60)
        print(f"🏠 Airbnb:      {len(self.all_results['airbnb'])} Listings")
        print(f"🏨 Booking.com: {len(self.all_results['booking'])} Properties")
        print(f"🏨 Hotels.com:  {len(self.all_results['hotelscom'])} Hotels")
        print(f"🏨 Expedia:     {len(self.all_results['expedia'])} Hotels")
        print(f"━━ TOTAL:       {len(combined_data)} Unterkünfte")
        print()
        print(f"💰 Günstigste:  CHF {df['price'].min()}")
        print(f"💰 Teuerste:    CHF {df['price'].max()}")
        print(f"💰 Durchschnitt: CHF {df['price'].mean():.0f}")
    
    def generate_html_report(self, df: pd.DataFrame, filename: str):
        """Generate beautiful HTML comparison report with image sliders"""
        html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Vergleichsreport - Alle Plattformen</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 20px; 
            background: #f5f5f5; 
        }
        h1 { color: #FF5A5F; text-align: center; }
        .summary {
            background: white;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        /* Card Style */
        .listing {
            background: white;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        /* Platform Badges */
        .platform-badge {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 4px;
            color: white;
            font-weight: bold;
            font-size: 12px;
            margin-right: 10px;
        }
        .airbnb { background: #FF5A5F; }
        .booking { background: #003580; }
        .hotelscom { background: #D32F2F; }
        .expedia { background: #0057B8; }
        
        .price { font-size: 24px; font-weight: bold; color: #008009; }
        .rating { 
            background: #FF8C00; 
            color: white; 
            padding: 5px 10px; 
            border-radius: 4px; 
            display: inline-block;
        }
        a { color: #FF5A5F; text-decoration: none; }
        a:hover { text-decoration: underline; }
        
        /* Image Gallery Slider */
        .image-gallery { margin: 20px 0; }
        .gallery-main { position: relative; max-width: 800px; margin: 0 auto; }
        .main-image { width: 100%; height: auto; border-radius: 8px; display: block; }
        .gallery-main button {
            position: absolute; top: 50%; transform: translateY(-50%);
            background: rgba(0,0,0,0.5); color: white; border: none;
            font-size: 24px; padding: 10px 15px; cursor: pointer;
            border-radius: 5px; z-index: 10;
        }
        .gallery-main button:hover { background: rgba(0,0,0,0.8); }
        .gallery-main button:first-of-type { left: 10px; }
        .gallery-main button:last-of-type { right: 10px; }
        .image-counter {
            position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%);
            background: rgba(0,0,0,0.5); color: white; padding: 5px 10px;
            border-radius: 5px; font-size: 12px;
        }
        .gallery-thumbnails { display: flex; gap: 10px; margin-top: 10px; overflow-x: auto; padding: 10px 0; }
        .thumbnail {
            width: 80px; height: 60px; object-fit: cover; border-radius: 4px;
            cursor: pointer; border: 2px solid transparent; opacity: 0.6;
            transition: all 0.3s;
        }
        .thumbnail:hover { opacity: 1; transform: scale(1.05); }
        .thumbnail.active { opacity: 1; border-color: #FF5A5F; }
    </style>
</head>
<body>
    <h1>🏠 Unterkunfts-Vergleichsreport</h1>
    
    <div class="summary">
        <h2>📊 Zusammenfassung</h2>
"""
        
        html += f"""
        <p><strong>Zeitraum:</strong> {self.config['search_parameters']['check_in']} - {self.config['search_parameters']['check_out']}</p>
        <p><strong>Ort:</strong> {self.config['search_parameters']['location']}</p>
        <p><strong>Gefunden:</strong> {len(df)} Unterkünfte</p>
        <p><strong>Airbnb:</strong> {len(self.all_results['airbnb'])} | 
           <strong>Booking.com:</strong> {len(self.all_results['booking'])} | 
           <strong>Hotels.com:</strong> {len(self.all_results['hotelscom'])} | 
           <strong>Expedia:</strong> {len(self.all_results['expedia'])}</p>
        <p><strong>Preisspanne:</strong> CHF {df['price'].min()} - CHF {df['price'].max()}</p>
    </div>
"""
        
        # Generate listing cards with image sliders
        for idx, (_, row) in enumerate(df.iterrows(), 1):
            # Platform badge
            platform = row['platform'].lower().replace('.', '').replace('com', '')
            platform_class = platform
            platform_name = row['platform']
            
            # Get all image URLs for this listing
            result = self._find_result_by_name(row['name'], row['platform'])
            image_urls = []
            if result:
                if 'image_urls' in result and result['image_urls']:
                    image_urls = result['image_urls'][:20]  # Max 20
                elif 'image_url' in result and result['image_url'] != 'N/A':
                    image_urls = [result['image_url']]
            
            html += f"""
    <div class="listing" id="listing{idx}">
        <span class="platform-badge {platform_class}">{platform_name}</span>
        <h2>{idx}. {row['name']}</h2>
        <p>📍 {row.get('location', 'N/A')}</p>
"""
            
            # Image gallery with slider
            if len(image_urls) >= 5:
                html += f"""
        <div class="image-gallery">
            <div class="gallery-main">
                <img src="{image_urls[0]}" alt="{row['name']}" class="main-image" id="mainImage{idx}">
                <button onclick="prevImage{idx}()">❮</button>
                <button onclick="nextImage{idx}()">❯</button>
                <div class="image-counter" id="imageCounter{idx}">1 / {len(image_urls)}</div>
            </div>
            <div class="gallery-thumbnails">
"""
                for i, img_url in enumerate(image_urls):
                    active = "active" if i == 0 else ""
                    html += f'<img src="{img_url}" class="thumbnail {active}" onclick="switchImage{idx}({i})" alt="{row["name"]} {i+1}">\n'
                
                html += f"""
            </div>
        </div>
        <script>
        (function() {{
            let idx{idx} = 0;
            const imgs{idx} = {image_urls};
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
                let rect = document.getElementById('listing{idx}').getBoundingClientRect();
                let isVisible = rect.top < window.innerHeight && rect.bottom > 0;
                if (!isVisible) return;
                if (e.key === 'ArrowRight') {{ e.preventDefault(); nextImage{idx}(); }}
                else if (e.key === 'ArrowLeft') {{ e.preventDefault(); prevImage{idx}(); }}
            }});
        }})();
        </script>
"""
            elif len(image_urls) == 1:
                html += f"""
        <div style="margin: 15px 0;">
            <img src="{image_urls[0]}" alt="{row['name']}" style="width: 100%; max-width: 800px; border-radius: 8px;">
        </div>
"""
            
            html += f"""
        <p><span class="price">CHF {row['price']}</span> pro Nacht</p>
        <p><span class="rating">⭐ {row.get('rating', 'N/A')}</span> ({row.get('reviews', 0)} Bewertungen)</p>
        <p>📏 Distanz: {row.get('distance_km', 'N/A')} km</p>
"""
            # Add bedrooms/guests for Airbnb
            if row.get('bedrooms') != 'N/A' or row.get('max_guests') != 'N/A':
                bedrooms_text = row.get('bedrooms', 'N/A')
                guests_text = row.get('max_guests', 'N/A')
                html += f"""        <p>🛏️ {bedrooms_text} Schlafzimmer | 👥 {guests_text} Gäste</p>
"""
            
            html += f"""        <p><a href="{row['url']}" target="_blank">🔗 Ansehen auf {platform_name}</a></p>
    </div>
"""
        
        html += """
</body>
</html>
"""
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)
    
    def _find_result_by_name(self, name: str, platform: str):
        """Find original result to get image_urls"""
        platform_key = platform.lower().replace('.', '').replace('com', '')
        if platform_key == 'booking':
            results = self.all_results['booking']
        elif platform_key == 'airbnb':
            results = self.all_results['airbnb']
        elif platform_key == 'hotels':
            results = self.all_results['hotelscom']
        elif platform_key == 'expedia':
            results = self.all_results['expedia']
        else:
            return None
        
        for result in results:
            if result.get('name') == name or result.get('title') == name:
                return result
        return None


if __name__ == "__main__":
    search = CombinedAccommodationSearch("search_config_Leukerbad_2026-01-10.json")
    search.run()
