# 🏠 Accommodation Search Web App

Multi-platform accommodation search tool with web interface!

## 🚀 Features

- ✅ Search on Airbnb, Booking.com, Hotels.com & Expedia simultaneously
- ✅ Beautiful web interface (responsive!)
- ✅ Real-time search progress
- ✅ HTML reports with image sliders
- ✅ Google Maps distance calculation
- ✅ Multi-filter support (price, rating, distance, etc.)

---

## 📦 Quick Start (Local Development)

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Copy Your Search Scripts

Copy these files to the `webapp/` directory:
```
- airbnb_searcher.py
- booking_searcher.py
- hotelscom_searcher.py
- expedia_searcher.py
- combined_search.py
- google_maps_distance.py (optional)
```

### 3. Set Environment Variables

```bash
# Google Maps API Key (optional but recommended)
export GOOGLE_MAPS_API_KEY="your-api-key-here"
```

### 4. Start Backend

```bash
cd webapp
python app.py
```

Backend runs on: `http://localhost:8000`

### 5. Open Frontend

Open `index.html` in your browser, or serve it:

```bash
python -m http.server 3000
```

Frontend runs on: `http://localhost:3000`

**Update API URL in index.html:**
```javascript
const API_BASE_URL = 'http://localhost:8000';
```

---

## 🌐 Deployment (Production)

### Option 1: Railway (Recommended for Backend)

**Why Railway?** 
- Free tier with 500 hours/month
- Supports Selenium + headless Chrome
- Easy deployment

**Steps:**

1. **Install Railway CLI:**
```bash
npm install -g @railway/cli
```

2. **Login:**
```bash
railway login
```

3. **Initialize Project:**
```bash
cd webapp
railway init
```

4. **Add Buildpack for Chrome:**

Create `railway.json`:
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python app.py",
    "healthcheckPath": "/health"
  }
}
```

Create `Aptfile`:
```
chromium
chromium-driver
```

5. **Deploy:**
```bash
railway up
```

6. **Get URL:**
```bash
railway domain
```

7. **Set Environment Variables:**
```bash
railway variables set GOOGLE_MAPS_API_KEY="your-key"
```

---

### Option 2: Render (Alternative)

1. Go to https://render.com
2. Create new "Web Service"
3. Connect GitHub repo
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
6. Add environment variables

---

### Frontend Deployment

#### Option A: Netlify (Easiest)

1. Go to https://netlify.com
2. Drag & drop `index.html`
3. Update `API_BASE_URL` in HTML to your Railway URL
4. Done! ✅

#### Option B: Vercel

```bash
npm install -g vercel
cd webapp
vercel
```

---

## 🔧 Configuration

### Backend (app.py)

The API accepts these parameters:

```json
{
  "location": "Leukerbad",
  "check_in": "2026-01-10",
  "check_out": "2026-01-12",
  "guests": 2,
  "max_price": 300,
  "min_rating": 4.6,
  "min_reviews": 3,
  "search_radius_km": 5,
  "platforms": ["airbnb", "booking", "hotelscom", "expedia"]
}
```

### Frontend (index.html)

Update this line with your deployed backend URL:
```javascript
const API_BASE_URL = 'https://your-app.railway.app';
```

---

## 📡 API Endpoints

### POST /api/search
Start a new search

**Request:**
```json
{
  "location": "Zermatt",
  "check_in": "2026-02-01",
  "check_out": "2026-02-03",
  "guests": 2,
  "max_price": 300,
  "platforms": ["airbnb", "booking"]
}
```

**Response:**
```json
{
  "search_id": "a1b2c3d4",
  "status": "queued",
  "message": "Suche gestartet!"
}
```

### GET /api/search/{search_id}
Check search status

**Response:**
```json
{
  "search_id": "a1b2c3d4",
  "status": "completed",
  "progress": "Fertig!",
  "results_count": 15,
  "html_report_url": "/results/combined_results_20260107.html"
}
```

### GET /results/{filename}
Download HTML or CSV report

---

## 🐛 Troubleshooting

### Selenium not working in production?

Make sure your hosting supports headless Chrome:
- ✅ Railway (with Aptfile)
- ✅ Render (with Dockerfile)
- ❌ Vercel (doesn't support Selenium)
- ❌ Netlify (static only)

### CORS errors?

Update CORS settings in `app.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.com"],
    ...
)
```

### Search timeout?

Increase timeouts in scraper config:
```python
"scraping_settings": {
    "wait_time_seconds": 5  # Increase if needed
}
```

---

## 📱 Mobile Access

The frontend is fully responsive! Access from:
- 📱 Phone
- 💻 Tablet
- 🖥️ Desktop

---

## 🔮 Future Enhancements

- [ ] User accounts
- [ ] Search history
- [ ] Email notifications
- [ ] Price alerts
- [ ] Scheduled searches
- [ ] Compare saved searches
- [ ] Mobile app (React Native)

---

## 📄 License

MIT

---

## 🤝 Support

Questions? Open an issue or contact support!

---

**Built with ❤️ for finding the best accommodations!** 🏠✨
