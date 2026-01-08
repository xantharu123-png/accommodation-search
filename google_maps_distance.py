#!/usr/bin/env python3
"""
Google Maps Distance Calculator
Berechnet echte Fahrzeiten und Distanzen
"""

import requests
import time
from typing import Optional, Dict, List, Tuple
import os


class GoogleMapsDistance:
    """Calculate real driving/walking distances using Google Maps API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with Google Maps API key
        
        Get free API key at: https://console.cloud.google.com/
        - Enable "Distance Matrix API"
        - Create API Key
        - Set environment variable: GOOGLE_MAPS_API_KEY
        """
        self.api_key = api_key or os.getenv('GOOGLE_MAPS_API_KEY')
        
        if not self.api_key:
            print("⚠️ WARNUNG: Keine Google Maps API Key gefunden!")
            print("   Setup:")
            print("   1. Gehe zu: https://console.cloud.google.com/")
            print("   2. Enable 'Distance Matrix API'")
            print("   3. Erstelle API Key")
            print("   4. Setze: GOOGLE_MAPS_API_KEY=dein_key")
            print()
            print("   → Ohne API Key kann keine echte Distanz berechnet werden!")
            print()
    
    def get_distance(self, origin: str, destination: str, 
                    mode: str = 'driving') -> Optional[Dict]:
        """
        Berechnet echte Distanz zwischen zwei Orten
        
        Args:
            origin: Start-Adresse (z.B. "Leukerbad, Switzerland")
            destination: Ziel-Adresse (z.B. "Hotel XYZ, Leukerbad")
            mode: 'driving', 'walking', 'bicycling', 'transit'
            
        Returns:
            {
                'distance_km': 5.2,
                'distance_text': '5.2 km',
                'duration_min': 8,
                'duration_text': '8 mins',
                'mode': 'driving'
            }
        """
        if not self.api_key:
            return None
        
        try:
            url = "https://maps.googleapis.com/maps/api/distancematrix/json"
            
            params = {
                'origins': origin,
                'destinations': destination,
                'mode': mode,
                'key': self.api_key,
                'units': 'metric'
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data['status'] != 'OK':
                print(f"⚠️ Google Maps Error: {data.get('status')}")
                return None
            
            # Extract result
            element = data['rows'][0]['elements'][0]
            
            if element['status'] != 'OK':
                return None
            
            distance_m = element['distance']['value']
            distance_km = distance_m / 1000
            distance_text = element['distance']['text']
            
            duration_s = element['duration']['value']
            duration_min = duration_s / 60
            duration_text = element['duration']['text']
            
            return {
                'distance_km': round(distance_km, 1),
                'distance_text': distance_text,
                'duration_min': round(duration_min),
                'duration_text': duration_text,
                'mode': mode
            }
            
        except Exception as e:
            print(f"⚠️ Fehler bei Distanzberechnung: {e}")
            return None
    
    def get_distances_batch(self, origin: str, destinations: List[str],
                           mode: str = 'driving') -> List[Optional[Dict]]:
        """
        Berechnet Distanzen zu mehreren Zielen gleichzeitig
        
        Args:
            origin: Start-Adresse
            destinations: Liste von Ziel-Adressen (max 25)
            mode: Transport-Modus
            
        Returns:
            Liste von Distance-Dicts
        """
        if not self.api_key:
            return [None] * len(destinations)
        
        # Google Maps erlaubt max 25 destinations pro Request
        batch_size = 25
        results = []
        
        for i in range(0, len(destinations), batch_size):
            batch = destinations[i:i + batch_size]
            
            try:
                url = "https://maps.googleapis.com/maps/api/distancematrix/json"
                
                params = {
                    'origins': origin,
                    'destinations': '|'.join(batch),
                    'mode': mode,
                    'key': self.api_key,
                    'units': 'metric'
                }
                
                response = requests.get(url, params=params, timeout=15)
                data = response.json()
                
                if data['status'] != 'OK':
                    results.extend([None] * len(batch))
                    continue
                
                # Extract results
                for element in data['rows'][0]['elements']:
                    if element['status'] != 'OK':
                        results.append(None)
                        continue
                    
                    distance_m = element['distance']['value']
                    distance_km = distance_m / 1000
                    distance_text = element['distance']['text']
                    
                    duration_s = element['duration']['value']
                    duration_min = duration_s / 60
                    duration_text = element['duration']['text']
                    
                    results.append({
                        'distance_km': round(distance_km, 1),
                        'distance_text': distance_text,
                        'duration_min': round(duration_min),
                        'duration_text': duration_text,
                        'mode': mode
                    })
                
                # Rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                print(f"⚠️ Batch error: {e}")
                results.extend([None] * len(batch))
        
        return results
    
    def add_distances_to_listings(self, origin: str, listings: List[Dict],
                                  address_key: str = 'name') -> List[Dict]:
        """
        Fügt echte Distanzen zu Listings hinzu
        
        Args:
            origin: Such-Ort (z.B. "Leukerbad, Switzerland")
            listings: Liste von Listings
            address_key: Key für Adresse ('name', 'url', etc.)
            
        Returns:
            Listings mit 'real_distance_km' und 'real_duration_min'
        """
        if not self.api_key:
            print("⚠️ Keine API Key - echte Distanzen nicht verfügbar")
            return listings
        
        # Ensure origin has country format FIRST (before using it!)
        if ',' not in origin:
            full_origin = f"{origin}, Switzerland"
        else:
            full_origin = origin
        
        origin_city = origin.split(',')[0].strip().lower()
        
        print(f"🗺️ Berechne echte Distanzen mit Google Maps...")
        print(f"   Von: {full_origin}")
        print(f"   Zu: {len(listings)} Unterkünften\n")
        
        # Erstelle Ziel-Adressen
        destinations = []
        
        for listing in listings:
            # Get title (e.g. "Wohnung in Mase")
            title = listing.get(address_key, listing.get('name', ''))
            
            # Extract ONLY the city name from title
            # Pattern: "Wohnung in Mase" → "Mase"
            # Pattern: "Scheune in Sion" → "Sion"
            import re
            
            # Try multiple patterns for different languages
            city = None
            patterns = [
                r'\sin\s+([A-ZÄÖÜ][a-zäöüéèêâîôû\-]+(?:\s[A-ZÄÖÜ][a-zäöüéèêâîôû\-]+)*)',  # "in Crans-Montana"
                r'\sà\s+([A-ZÄÖÜ][a-zäöüéèêâîôû\-]+(?:\s[A-ZÄÖÜ][a-zäöüéèêâîôû\-]+)*)',   # "à Veysonnaz"
            ]
            
            for pattern in patterns:
                city_match = re.search(pattern, title)
                if city_match:
                    matched_city = city_match.group(1).strip()
                    # IMPORTANT: Exclude origin city (e.g. don't match "Leukerbad" if searching Leukerbad)
                    if matched_city.lower() != origin_city:
                        city = matched_city
                        break
            
            if city:
                # Use ONLY city name + country
                address = f"{city}, Switzerland"
            else:
                # Fallback: For listings in the origin city, use full origin
                address = full_origin
            
            destinations.append(address)
        
        # DEBUG: Print first few addresses
        print(f"   🔍 Beispiel-Adressen:")
        for i, addr in enumerate(destinations[:5]):
            print(f"      [{i+1}] {addr}")
        
        # Batch-Request
        distances = self.get_distances_batch(origin, destinations)
        
        # Füge zu Listings hinzu
        count_success = 0
        count_failed = 0
        for i, (listing, dist) in enumerate(zip(listings, distances)):
            if dist:
                listing['real_distance_km'] = dist['distance_km']
                listing['real_duration_min'] = dist['duration_min']
                listing['real_distance_text'] = dist['distance_text']
                listing['real_duration_text'] = dist['duration_text']
                count_success += 1
            else:
                count_failed += 1
                # Keep distance_km as 0 if calculation failed
                if 'real_distance_km' not in listing:
                    listing['real_distance_km'] = 0
                
            if (i + 1) % 10 == 0:
                print(f"   ✓ {i + 1}/{len(listings)} verarbeitet...")
        
        if count_failed > 0:
            print(f"   ⚠️ {count_failed} Distanzen konnten nicht berechnet werden (= 0 km gesetzt)")
        
        print(f"\n✅ {count_success}/{len(listings)} Distanzen berechnet!")
        return listings


def test_google_maps():
    """Test Google Maps Distance Calculator"""
    print("🧪 TEST: Google Maps Distance Calculator")
    print("=" * 60)
    
    calc = GoogleMapsDistance()
    
    if not calc.api_key:
        print("\n❌ Keine API Key gefunden!")
        print("   Setze GOOGLE_MAPS_API_KEY environment variable")
        return
    
    # Test 1: Einzelne Distanz
    print("\n📍 Test 1: Leukerbad → Leukerbad Therme")
    result = calc.get_distance(
        "Leukerbad, Switzerland",
        "Leukerbad Therme, Leukerbad",
        mode='walking'
    )
    
    if result:
        print(f"   ✓ Distanz: {result['distance_km']} km")
        print(f"   ✓ Dauer: {result['duration_min']} min")
    else:
        print("   ❌ Fehler")
    
    # Test 2: Batch
    print("\n📍 Test 2: Batch-Distanzen")
    destinations = [
        "Hotel Regina, Leukerbad",
        "Les Maisons, Leukerbad",
        "Grichting & Badnerhof, Leukerbad"
    ]
    
    results = calc.get_distances_batch(
        "Leukerbad, Switzerland",
        destinations,
        mode='driving'
    )
    
    for dest, res in zip(destinations, results):
        if res:
            print(f"   ✓ {dest}: {res['distance_km']} km ({res['duration_min']} min)")
    
    print("\n" + "=" * 60)
    print("✅ Tests abgeschlossen!")


if __name__ == "__main__":
    test_google_maps()
