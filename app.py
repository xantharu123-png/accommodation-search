#!/usr/bin/env python3
"""
Accommodation Search Web API
FastAPI backend for multi-platform accommodation search
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import json
import os
from datetime import datetime
from pathlib import Path
import uuid

# Import database
from database import Database

app = FastAPI(title="Accommodation Search API", version="1.0.0")

# Initialize database
db = Database()

# CORS - allow frontend to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store search results temporarily
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

# Cleanup old HTML files on startup
@app.on_event("startup")
async def startup_cleanup():
    """Delete old search result HTML files on startup"""
    try:
        for html_file in RESULTS_DIR.glob("search_results_*.html"):
            html_file.unlink()
            print(f"🗑️ Deleted old HTML: {html_file.name}")
        print("✅ Startup cleanup complete!")
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

# In-memory storage for search status (use Redis in production)
search_status = {}


class SearchParams(BaseModel):
    location: str
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    guests: int = 2
    min_bedrooms: int = 1
    max_price: int = 300
    # Platform-specific ratings (different scales!)
    min_rating_airbnb: float = 4.0  # 0-5 scale
    min_rating_booking: float = 8.0  # 0-10 scale
    min_rating_hotels: float = 8.0   # 0-10 scale
    min_rating_expedia: float = 8.0  # 0-10 scale
    # Backward compatibility
    min_rating: Optional[float] = None  # Deprecated, use platform-specific
    min_reviews: int = 3
    search_radius_km: int = 5
    platforms: List[str] = ["airbnb", "booking", "hotelscom", "expedia"]
    amenities: Optional[dict] = None  # Optional amenities filter


class SearchResponse(BaseModel):
    search_id: str
    status: str  # "queued", "running", "completed", "failed"
    message: str


class SearchStatus(BaseModel):
    search_id: str
    status: str
    progress: str
    results_count: int
    html_report_url: Optional[str] = None
    csv_file_url: Optional[str] = None
    error: Optional[str] = None


class FavoriteAdd(BaseModel):
    list_name: str
    location: str
    listing_data: dict


class FavoriteResponse(BaseModel):
    id: int
    list_name: str
    location: str
    listing_data: dict
    created_at: str
    updated_at: str


class ListNameUpdate(BaseModel):
    old_name: str
    new_name: str


class AnalyzeRequest(BaseModel):
    favorite_ids: List[int]


def run_search(search_id: str, params: SearchParams):
    """Run accommodation search in background"""
    try:
        search_status[search_id] = {
            "status": "running",
            "progress": "Initialisiere Suche...",
            "results_count": 0
        }
        
        # Create config with platform-specific ratings
        config = {
            "search_parameters": {
                "location": params.location,
                "check_in": params.check_in,
                "check_out": params.check_out,
                "guests": params.guests,
                "min_bedrooms": params.min_bedrooms,
                "search_radius_km": params.search_radius_km
            },
            "filters": {
                "max_price_per_night_chf": params.max_price,
                # Platform-specific ratings (each platform uses its own)
                "min_rating_airbnb": params.min_rating_airbnb,  # 0-5 scale
                "min_rating_booking": params.min_rating_booking,  # 0-10 scale
                "min_rating_hotels": params.min_rating_hotels,    # 0-10 scale
                "min_rating_expedia": params.min_rating_expedia,  # 0-10 scale
                # Backward compatibility - use Airbnb scale as default
                "min_rating": params.min_rating or params.min_rating_airbnb,
                "min_number_of_reviews": params.min_reviews,
                "superhost_only": False,
                "instant_book_only": False,
                "max_price": params.max_price,
                "min_reviews": params.min_reviews
            },
            "amenities": params.amenities or {
                "private_pool": {"required": False},
                "private_whirlpool": {"required": False},
                "private_sauna": {"required": False},
                "fireplace": {"required": False},
                "parking": {"required": False}
            },
            "location_settings": {
                "radius_km": params.search_radius_km,
                "use_exact_location": False
            },
            "output": {
                "max_results": 50,
                "max_pages": 3,  # Reduced for Railway memory limits
                "save_to_csv": True,
                "save_to_html": True
            },
            "scraping_settings": {
                "headless": True,
                "wait_time_seconds": 3
            }
        }
        
        # Save config
        config_path = RESULTS_DIR / f"config_{search_id}.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        search_status[search_id]["progress"] = "Starte Combined Search..."
        
        # Run search based on platforms
        all_results = []
        
        if "all" in params.platforms or len(params.platforms) == 0:
            # Run combined search
            from combined_search import CombinedAccommodationSearch
            searcher = CombinedAccommodationSearch(str(config_path))
            searcher.run()
            
            # Collect results
            for platform, results in searcher.all_results.items():
                all_results.extend(results)
        else:
            # Run individual platforms
            if "airbnb" in params.platforms:
                search_status[search_id]["progress"] = "Suche auf Airbnb..."
                from airbnb_searcher import AirbnbSearcher
                airbnb = AirbnbSearcher(str(config_path))
                airbnb.search()
                all_results.extend(airbnb.results)
            
            if "booking" in params.platforms:
                search_status[search_id]["progress"] = "Suche auf Booking.com..."
                from booking_searcher import BookingSearcher
                booking = BookingSearcher(str(config_path))
                booking.search()
                all_results.extend(booking.results)
            
            if "hotelscom" in params.platforms:
                search_status[search_id]["progress"] = "Suche auf Hotels.com..."
                from hotelscom_searcher import HotelscomSearcher
                hotelscom = HotelscomSearcher(str(config_path))
                hotelscom.search()
                all_results.extend(hotelscom.results)
            
            if "expedia" in params.platforms:
                search_status[search_id]["progress"] = "Suche auf Expedia..."
                from expedia_searcher import ExpediaSearcher
                expedia = ExpediaSearcher(str(config_path))
                expedia.search()
                all_results.extend(expedia.results)
        
        # Find generated HTML report (any platform)
        html_files = list(RESULTS_DIR.glob("*results*.html"))
        
        # If no HTML file exists, create one from results
        if not html_files and all_results:
            import pandas as pd
            from datetime import datetime as dt
            from review_analyzer import ReviewAnalyzer
            
            # Initialize AI Review Analyzer
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            analyzer = ReviewAnalyzer(api_key=api_key)
            
            # Create HTML report with search-specific filename
            html_filename = f"search_results_{search_id}.html"
            html_path = RESULTS_DIR / html_filename
            
            # Convert results to HTML
            df = pd.DataFrame(all_results)
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Suchergebnisse - {len(all_results)} Unterkünfte</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #667eea; }}
        .top-nav {{ text-align: center; margin-bottom: 20px; }}
        .top-nav a {{ 
            display: inline-block;
            padding: 12px 24px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            margin: 0 10px;
        }}
        .top-nav a:hover {{ background: #5568d3; }}
        .listing {{ background: white; padding: 20px; margin: 20px 0; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); position: relative; }}
        .listing h3 {{ margin: 0 0 10px 0; color: #333; }}
        .price {{ color: #4CAF50; font-size: 24px; font-weight: bold; }}
        .rating {{ color: #ff9800; font-weight: bold; }}
        .platform {{ background: #667eea; color: white; padding: 5px 10px; border-radius: 5px; display: inline-block; }}
        img {{ max-width: 300px; border-radius: 8px; margin: 10px 10px 10px 0; }}
        .favorite-btn {{
            position: absolute;
            top: 20px;
            right: 20px;
            padding: 10px 20px;
            background: #ff9800;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 16px;
        }}
        .favorite-btn:hover {{ background: #f57c00; }}
        .favorite-btn.added {{ background: #4CAF50; }}
    </style>
</head>
<body>
    <div class="top-nav">
        <a href="https://preeminent-bublanina-07acfe.netlify.app/favorites.html" target="_blank">⭐ Meine Favoriten ansehen</a>
    </div>
    <h1>🏠 {len(all_results)} Unterkünfte gefunden</h1>
    <p>Suche für: {params.location} | {params.check_in} - {params.check_out}</p>
"""
            
            for i, listing in enumerate(all_results[:50], 1):
                # Fix platform if missing
                platform = listing.get('platform', 'Unknown').title()
                if platform == 'Unknown' and listing.get('url'):
                    # Try to detect platform from URL
                    url = listing.get('url', '').lower()
                    if 'airbnb' in url:
                        platform = 'Airbnb'
                        listing['platform'] = 'Airbnb'  # Update the listing data too!
                    elif 'booking' in url:
                        platform = 'Booking.com'
                        listing['platform'] = 'Booking.com'
                    elif 'hotels.com' in url:
                        platform = 'Hotels.com'
                        listing['platform'] = 'Hotels.com'
                    elif 'expedia' in url:
                        platform = 'Expedia'
                        listing['platform'] = 'Expedia'
                
                html_content += f"""
    <div class="listing" data-listing-index="{i}">
        <button class="favorite-btn" onclick="addToFavorites({i})">⭐ Zu Favoriten</button>
        <h3>{i}. {listing.get('title', 'Unterkunft')}</h3>
        <p><span class="platform">{platform}</span></p>
        <p class="price">{listing.get('price_per_night', 'N/A')} CHF / Nacht</p>
        <p class="rating">⭐ {listing.get('rating', 'N/A')} ({listing.get('num_reviews', 0)} Bewertungen)</p>
        <p>📍 {listing.get('location', 'N/A')}</p>
        <p>🛏️ {listing.get('bedrooms', 'N/A')} Schlafzimmer | 👥 {listing.get('max_guests', 'N/A')} Gäste</p>
"""
                if listing.get('image_urls'):
                    for img_url in listing['image_urls'][:10]:  # Show up to 10 images
                        html_content += f'<img src="{img_url}" />'
                
                # AI Review Analysis
                if listing.get('reviews') and len(listing['reviews']) > 0:
                    print(f"   🤖 AI analysiert Reviews für {listing.get('title', 'Listing')}...")
                    analysis = analyzer.analyze_reviews(
                        reviews=listing['reviews'],
                        listing_title=listing.get('title', '')
                    )
                    html_content += analyzer.format_analysis_html(analysis)
                
                html_content += f"""
        <p><a href="{listing.get('url', '#')}" target="_blank">🔗 Listing ansehen</a></p>
    </div>
"""
            
            html_content += """
</body>
<script>
const API_BASE_URL = 'https://accommodation-search-production.up.railway.app';
const SEARCH_LOCATION = '""" + params.location + """';

// Store all listings data
const allListings = """ + json.dumps([{
    'title': l.get('title', 'N/A'),
    'price_per_night': l.get('price_per_night', 'N/A'),
    'rating': l.get('rating', 'N/A'),
    'num_reviews': l.get('num_reviews', 0),
    'location': l.get('location', 'N/A'),
    'url': l.get('url', '#'),
    'platform': l.get('platform', 'Unknown'),
    'image_urls': l.get('image_urls', [])[:3],
    'bedrooms': l.get('bedrooms', 'N/A'),
    'max_guests': l.get('max_guests', 'N/A'),
    'reviews': l.get('reviews', [])[:5]  # Save some reviews for AI
} for l in all_results[:50]]) + """;

async function addToFavorites(index) {
    const listing = allListings[index - 1];
    const btn = document.querySelector(`[data-listing-index="${index}"] .favorite-btn`);
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/favorites`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                list_name: SEARCH_LOCATION,
                location: SEARCH_LOCATION,
                listing_data: listing
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            btn.textContent = '✅ Gespeichert!';
            btn.classList.add('added');
            btn.disabled = true;
        }
        
    } catch (error) {
        console.error('Error adding to favorites:', error);
        alert('❌ Fehler beim Speichern');
    }
}
</script>
</html>
"""
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            html_files = [html_path]
        
        # Set HTML URL - use search-specific file if exists
        html_url = None
        search_specific_html = RESULTS_DIR / f"search_results_{search_id}.html"
        
        if search_specific_html.exists():
            html_url = f"/results/search_results_{search_id}.html"
        elif html_files:
            # Fallback to most recent
            latest_html = max(html_files, key=os.path.getctime)
            html_url = f"/results/{latest_html.name}"
        
        # Update status
        search_status[search_id] = {
            "status": "completed",
            "progress": "Fertig!",
            "results_count": len(all_results),
            "html_report_url": html_url,
            "csv_file_url": None  # Add CSV if needed
        }
        
    except Exception as e:
        search_status[search_id] = {
            "status": "failed",
            "progress": "Fehler",
            "results_count": 0,
            "error": str(e)
        }


@app.get("/")
async def root():
    """API info"""
    return {
        "name": "Accommodation Search API",
        "version": "1.0.0",
        "endpoints": {
            "search": "POST /api/search",
            "status": "GET /api/search/{search_id}",
            "results": "GET /results/{filename}"
        }
    }


@app.post("/api/search", response_model=SearchResponse)
async def start_search(params: SearchParams, background_tasks: BackgroundTasks):
    """Start a new accommodation search"""
    
    # Generate unique search ID
    search_id = str(uuid.uuid4())[:8]
    
    # Initialize status
    search_status[search_id] = {
        "status": "queued",
        "progress": "In Warteschlange...",
        "results_count": 0
    }
    
    # Add to background tasks
    background_tasks.add_task(run_search, search_id, params)
    
    return SearchResponse(
        search_id=search_id,
        status="queued",
        message=f"Suche gestartet! Verwende /api/search/{search_id} um Status zu prüfen."
    )


@app.get("/api/search/{search_id}", response_model=SearchStatus)
async def get_search_status(search_id: str):
    """Get status of a search"""
    
    if search_id not in search_status:
        raise HTTPException(status_code=404, detail="Search ID nicht gefunden")
    
    status = search_status[search_id]
    
    return SearchStatus(
        search_id=search_id,
        status=status.get("status", "unknown"),
        progress=status.get("progress", ""),
        results_count=status.get("results_count", 0),
        html_report_url=status.get("html_report_url"),
        csv_file_url=status.get("csv_file_url"),
        error=status.get("error")
    )


@app.get("/results/{filename}")
async def get_results_file(filename: str):
    """Serve result files (HTML/CSV)"""
    file_path = RESULTS_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File nicht gefunden")
    
    # Security: ensure file is in results directory
    if not str(file_path.resolve()).startswith(str(RESULTS_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    
    # For HTML: display inline (don't download)
    # For CSV: download
    if filename.endswith(".html"):
        return FileResponse(
            path=file_path,
            media_type="text/html",
            headers={"Content-Disposition": "inline"}  # ← DISPLAY, NOT DOWNLOAD!
        )
    else:
        return FileResponse(
            path=file_path,
            media_type="text/csv",
            filename=filename
        )


@app.get("/results/{filename}")
async def get_result_file(filename: str):
    """Download result file"""
    
    file_path = RESULTS_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File nicht gefunden")
    
    return FileResponse(
        path=file_path,
        media_type="text/html" if filename.endswith(".html") else "text/csv",
        filename=filename
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ========================================
# FAVORITES ENDPOINTS
# ========================================

@app.post("/api/favorites")
async def add_to_favorites(favorite: FavoriteAdd):
    """Add a listing to favorites"""
    try:
        favorite_id = db.add_favorite(
            list_name=favorite.list_name,
            location=favorite.location,
            listing_data=favorite.listing_data
        )
        
        return {
            "success": True,
            "favorite_id": favorite_id,
            "message": "✅ Zu Favoriten hinzugefügt!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/favorites")
async def get_favorites(list_name: Optional[str] = None):
    """Get all favorites or favorites for a specific list"""
    try:
        if list_name:
            favorites = db.get_favorites_by_list(list_name)
        else:
            favorites = db.get_all_favorites()
        
        return {
            "success": True,
            "count": len(favorites),
            "favorites": favorites
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/favorites/lists")
async def get_favorite_lists():
    """Get all favorite list names"""
    try:
        list_names = db.get_all_list_names()
        
        return {
            "success": True,
            "count": len(list_names),
            "lists": list_names
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/favorites/lists/rename")
async def rename_list(update: ListNameUpdate):
    """Rename a favorites list"""
    try:
        success = db.update_list_name(update.old_name, update.new_name)
        
        if success:
            return {
                "success": True,
                "message": f"✅ Liste umbenannt: {update.old_name} → {update.new_name}"
            }
        else:
            raise HTTPException(status_code=404, detail="Liste nicht gefunden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/favorites/{favorite_id}")
async def delete_favorite(favorite_id: int):
    """Delete a favorite"""
    try:
        success = db.delete_favorite(favorite_id)
        
        if success:
            return {
                "success": True,
                "message": "✅ Favorit gelöscht"
            }
        else:
            raise HTTPException(status_code=404, detail="Favorit nicht gefunden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/favorites/analyze")
async def analyze_favorites(request: AnalyzeRequest):
    """Run AI analysis on selected favorites"""
    try:
        from review_analyzer import ReviewAnalyzer
        
        # Initialize AI
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        analyzer = ReviewAnalyzer(api_key=api_key)
        
        results = []
        
        for favorite_id in request.favorite_ids:
            # Get favorite
            all_favs = db.get_all_favorites()
            favorite = next((f for f in all_favs if f['id'] == favorite_id), None)
            
            if not favorite:
                continue
            
            listing_data = favorite['listing_data']
            
            # Check if analysis already exists
            existing_analysis = db.get_analysis(favorite_id)
            
            if existing_analysis:
                # Use cached analysis
                results.append({
                    "favorite_id": favorite_id,
                    "title": listing_data.get('title', 'N/A'),
                    "analysis": existing_analysis['analysis_result'],
                    "cached": True
                })
            else:
                # Run new analysis
                reviews = listing_data.get('reviews', [])
                
                if reviews:
                    print(f"   🤖 AI analysiert: {listing_data.get('title', 'Listing')}...")
                    analysis = analyzer.analyze_reviews(
                        reviews=reviews,
                        listing_title=listing_data.get('title', '')
                    )
                    
                    # Save analysis
                    db.save_analysis(favorite_id, analysis)
                    
                    results.append({
                        "favorite_id": favorite_id,
                        "title": listing_data.get('title', 'N/A'),
                        "analysis": analysis,
                        "cached": False
                    })
                else:
                    results.append({
                        "favorite_id": favorite_id,
                        "title": listing_data.get('title', 'N/A'),
                        "analysis": {
                            "summary": "Keine Reviews verfügbar"
                        },
                        "cached": False
                    })
        
        return {
            "success": True,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    import os
    
    # Railway provides PORT via environment variable
    port = int(os.environ.get("PORT", 8000))
    
    uvicorn.run(app, host="0.0.0.0", port=port)
