# Übergabe an Codex – Accommodation Search

Stand: 11.11.2026 · Branch `main` · HEAD `63d477e` (lokal = `origin/main`, Arbeitsbaum sauber bis auf die untracked Dateien `PROJECT_SUMMARY.md` und diese Datei)

Dieses Dokument fasst alles zusammen, was in den bisherigen Sessions (mit Claude Code, 25.–28.10.2026) herausgefunden, geändert, gemessen und entschieden wurde. Lies es ganz, bevor du etwas änderst. Die Abschnitte 11 (Spielregeln) und 10 (Lessons learned) sind verbindlich.

---

## 0. Kurzfassung

- **Was:** Web-App, die Unterkünfte auf **Airbnb, Booking.com und Google Hotels** per Selenium/Chrome scrapt, filtert und als HTML-Report anzeigt. FastAPI-Backend, statisches HTML-Frontend, Favoriten in SQLite, optionale KI-Review-Analyse.
- **Hosting:** Frontend auf **Vercel** (https://accommodation-search.vercel.app), Backend auf **Render Free** (https://accommodation-search.onrender.com) als **Docker**-Service. Beide deployen automatisch bei Push auf `main`.
- **Zustand (live verifiziert am 28.10.2026):** Die Suche läuft auf Render bis zum Ende durch und hängt nicht mehr. Die Ergebnisse je Plattform:
  - **Airbnb** liefert echte Treffer, braucht aber rund **45 min**. Etwa die Hälfte der Detailseiten läuft in einen Timeout, diesen Treffern fehlen dann Bilder und Ausstattung.
  - **Google Hotels** liefert nach rund **2 min** korrekte Preise.
  - **Booking.com** liefert auf Render **0 Treffer**. Es gibt einen Sofortabbruch nach rund 1,5 min, Ursache ist wahrscheinlich Booking-Bot-Schutz gegen die Rechenzentrums-IP. **Lokal funktioniert Booking.**
- **Hauptengpass:** Render Free hat **0,1 CPU und 512 MB RAM**. Jeder WebDriver-Roundtrip dauert dort Sekunden, und zwei Chromes gleichzeitig sprengen den Speicher.
- **Ursprüngliches Problem** („Suche hängt auf Render, Chrome startet nicht“) ist gelöst. `PROJECT_SUMMARY.md` beschreibt noch diesen alten Zustand vom März 2026 und ist **veraltet**.

---

## 1. Orte, Repos, URLs, Accounts

| Was | Wo |
|---|---|
| Lokaler Repo-Pfad | `C:\Projekt\Airbnb Suche\webapp` (Git-Repo, Branch `main`) |
| Elternordner | `C:\Projekt\Airbnb Suche` – **nicht** im Git. Enthält alte CLI-Versionen der Scraper (`accommodation_search.py`, `airbnb_searcher.py`, `booking_com_searcher.py`, `trivago_searcher.py`, diverse `*_README.md`, `.bat`, Debug-PNGs, alte Configs). Altlast, nicht anfassen, nicht als Referenz für den aktuellen Code verwenden. |
| GitHub | https://github.com/xantharu123-png/accommodation-search (remote `origin`) |
| Frontend (Vercel) | https://accommodation-search.vercel.app – liefert `index.html` aus dem Repo-Root, deployt automatisch bei Push. GitHub zeigt bei Commits nur die Vercel-Statuschecks, **nicht** Render. |
| Backend (Render) | https://accommodation-search.onrender.com · Health: `/health` |
| Render-Dashboard | https://dashboard.render.com/web/srv-d6mo2k3h46gs73bqrrs0 (Logs: `/logs`, Events: `/events`, Env: `/env`). **Login macht nur Miroslav selbst.** |
| Render-Service | Name `accommodation-search`, ID `srv-d6mo2k3h46gs73bqrrs0`, Region Frankfurt, Plan Free, Runtime **Docker** (am 28.10. im Dashboard von „Python native“ auf Docker umgestellt), Dockerfile `./Dockerfile`, Auto-Deploy bei Push auf `main`. |
| Netlify | Lokaler Ordner `.netlify/` (gitignored) stammt von einem früheren Netlify-Deploy. Altlast. |
| Railway | `railway.json` stammt vom früheren Railway-Hosting (Trial abgelaufen). Altlast. |

`PROJECT_SUMMARY.md` (untracked, gehört Miroslav) nennt noch den alten Pfad `C:\Users\miros\Desktop\Airbnb Suche\webapp`. Der aktuelle Pfad ist der oben genannte.

---

## 2. Architektur und Datenfluss

```
Browser (index.html von Vercel, oder / vom Backend)
  │ POST /api/search  {location, check_in, check_out, guests, max_price, ratings, platforms, amenities, ...}
  ▼
FastAPI app.py ── legt search_id an (uuid[:8]), status "queued" im RAM-Dict search_status
  │ BackgroundTasks → run_search(search_id, params)   (läuft im Threadpool, 1 uvicorn-Worker)
  │   1. löscht alte results/search_results_*.html
  │   2. baut config-Dict → results/config_<id>.json
  │   3. pro gewählter Plattform nacheinander: Searcher(config_path).search()  (je eigener Chrome)
  │      - run_platform() fängt Exceptions pro Plattform ab, andere Plattformen laufen weiter
  │   4. erzeugt results/search_results_<id>.html (eigenes HTML in app.py, max. 50 Treffer,
  │      inkl. "Zu Favoriten"-Button und optionaler KI-Analyse)
  │   5. status "completed" + html_report_url "/results/search_results_<id>.html"
  ▼
Frontend pollt alle 2 s GET /api/search/{id}; bei "completed" öffnet es
`${API_BASE_URL}${html_report_url}` in neuem Tab; bei 404 (Server neu gestartet) stoppt das Polling.
```

- `index.html:796`: `API_BASE_URL` ist auf `localhost`/`127.0.0.1` leer (gleiche Herkunft, also das lokale Backend), sonst `https://accommodation-search.onrender.com`.
- Der Report und `favorites.html` werden vom Backend selbst ausgeliefert und nutzen relative API-URLs (`API_BASE_URL = ''`).
- `platforms` leer oder `"all"` → `combined_search.CombinedAccommodationSearch` (alle drei nacheinander + eigener Vergleichsreport). Das Frontend schickt aber nie eine leere Liste (Alert, wenn nichts angehakt). Der Combined-Pfad ist für die Web-UI also praktisch ungenutzt.
- `platforms` mit `"expedia"` oder `"hotelscom"` setzt nur eine „nicht mehr unterstützt“-Meldung und startet **keinen Chrome**. Das ist nützlich als Deploy-Marker (siehe 10.6).

---

## 3. Dateien im Repo (tracked)

| Datei | Zweck / Stand |
|---|---|
| `app.py` | FastAPI-App: Routen, `SearchParams`, `run_search`, Report-HTML, Favoriten-Endpunkte. Siehe 4. |
| `chrome_driver.py` | Gemeinsamer Chrome-Start für alle Scraper. Liest `CHROME_BIN` und `CHROMEDRIVER_PATH` (Docker); ohne diese Variablen sucht Selenium Manager Chrome selbst (lokal). `LOW_MEMORY=1` aktiviert RAM-sparende Flags, schaltet Bilder ab und setzt `page_load_strategy='eager'`. Page-Load- und Script-Timeout kommen aus `PAGE_LOAD_TIMEOUT` (Default 90 s). |
| `airbnb_searcher.py` | Airbnb-Scraper (airbnb.ch). Siehe 6.1. |
| `booking_searcher.py` | Booking-Scraper (searchresults.de.html). Siehe 6.2. |
| `google_hotels_searcher.py` | Google-Hotels-Scraper über google.com/travel. Siehe 6.3. |
| `combined_search.py` | Alle drei nacheinander + Vergleichsreport. Nur bei `platforms` leer/`all`. |
| `google_maps_distance.py` | Distanzen über Google Distance Matrix API (`GOOGLE_MAPS_API_KEY`). Wird **nur von Airbnb** benutzt. Ohne Key: Distanz bleibt 0 bzw. nicht gesetzt. |
| `review_analyzer.py` | KI-Analyse von Reviews über die Anthropic API (`ANTHROPIC_API_KEY`). Modell-ID hart codiert: `claude-sonnet-4-20250514` (`review_analyzer.py:92`). Ohne Key wird die Analyse übersprungen. `import anthropic` steht auf Modulebene, das Paket muss also installiert sein. |
| `database.py` | SQLite `favorites.db` (Tabellen `favorites`, `ai_analyses`). |
| `index.html` | Suchformular und Polling. Datalist mit ~267 Orten im Format „Ort, Land“ bzw. Regionen. Filter: Gäste, Max-Preis, Bewertung (einfach oder erweitert pro Plattform), Radius, Unterkunftstyp, Ausstattung, Verpflegung, Plattformen. |
| `favorites.html` | Favoritenlisten, Umbenennen, Löschen, KI-Analyse. |
| `Dockerfile` | `python:3.12-slim-bookworm` + Debian `chromium` + `chromium-driver` (Versionen passen immer zusammen), `PYTHONUNBUFFERED=1`, `CHROME_BIN=/usr/bin/chromium`, `CHROMEDRIVER_PATH=/usr/bin/chromedriver`, `LOW_MEMORY=1`, `uvicorn app:app --workers 1` auf `${PORT:-10000}`. |
| `render.yaml` | Blueprint-Beschreibung (Docker, free, frankfurt, Env-Vars). **Der Service ist nicht Blueprint-verwaltet.** Die Datei dokumentiert nur den Sollzustand; Änderungen daran wirken nicht automatisch. Env-Vars werden im Dashboard gesetzt. |
| `requirements.txt` | fastapi 0.109, uvicorn 0.27, selenium 4.17.2, pandas 2.2.3, numpy 2.0.0, googlemaps, anthropic>=0.34, bs4, lxml u. a. |
| `.dockerignore` | `.git`, `.netlify`, `__pycache__`, `*.pyc`, `results`, `favorites.db`, `*.bat`, `PROJECT_SUMMARY.md` |
| `.gitignore` | `.netlify`, `__pycache__/`, `*.pyc`, `favorites.db`, `results/` |
| `start_server.bat` | Lokaler Start auf Port 8000 mit `--reload`. Installiert nur einen **Teil** der Abhängigkeiten (siehe 9.3). |
| `expedia_searcher.py`, `hotelscom_searcher.py` | Alt, vom Web-Flow nicht mehr benutzt (durch Google Hotels ersetzt). |
| `railway.json`, `Aptfile`, `runtime.txt` (`python-3.11.9`) | Altlasten früherer Hostings. Docker ignoriert sie. |
| `WEBAPP_README.md`, `WEBAPP_INSTALLATION.txt`, `WEBAPP_FILES_LIST.txt`, `webapp_gitignore.txt` | Alte Doku (Januar 2026), teils veraltet. |
| `__pycache__/airbnb_searcher.cpython-312.pyc`, `results/config_*.json` (4 Stück) | **Versehentlich getrackt**, obwohl inzwischen in `.gitignore`. Kandidat für `git rm --cached` (siehe 8). |

Untracked: `PROJECT_SUMMARY.md` (Miroslavs Datei, **nie committen**), `favorites.db` (lokal, ignoriert), `results/` (lokal, ignoriert), `HANDOFF_CODEX.md` (diese Datei).

---

## 4. API (app.py)

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/` | liefert `index.html` |
| GET | `/favorites.html` | liefert `favorites.html` |
| POST | `/api/search` | startet Suche → `{search_id, status:"queued", message}` |
| GET | `/api/search/{id}` | `{search_id, status, progress, results_count, html_report_url, csv_file_url, error}`; 404, wenn die ID unbekannt ist (z. B. nach einem Neustart) |
| GET | `/results/{filename}` | liefert HTML inline bzw. CSV als Download (die Route ist **doppelt** definiert, siehe 8) |
| GET | `/health` | `{"status":"healthy","timestamp":...}` |
| POST/GET | `/api/favorites` | Favorit hinzufügen / alle bzw. `?list_name=` |
| GET | `/api/favorites/lists` | Listennamen |
| PUT | `/api/favorites/lists/rename` | `{old_name,new_name}` |
| DELETE | `/api/favorites/{id}` | löschen |
| POST | `/api/favorites/analyze` | `{favorite_ids:[...]}`, KI-Analyse, wird in `ai_analyses` gecacht |

**Statusverlauf:** `queued` → `running` (`progress` z. B. „Suche auf Booking.com...“) → `completed` (`progress` „Fertig!“, ggf. mit „(fehlgeschlagen: X)“) oder `failed` (`error`).

**`SearchParams`** (`app.py:73`): `location, check_in, check_out` (YYYY-MM-DD), `guests=2, min_bedrooms=1, max_price=300, min_rating_airbnb=4.0` (Skala 0–5), `min_rating_booking/hotels/expedia=8.0` (Skala 0–10), `min_rating` (veraltet), `min_reviews=3, search_radius_km=5, property_type="any"` (any|house|apartment|guesthouse|hotel|private_room), `platforms=["airbnb","booking","google_hotels"], amenities` (Dict `{key:{required:bool}}`). **Kein Feld `meal_plan`** (Bug, siehe 8.1).

**Env-Variablen im Code:** `MAX_RESULTS` (Default 50), `MAX_PAGES` (Default 3), `PAGE_LOAD_TIMEOUT` (90), `LOW_MEMORY`, `CHROME_BIN`, `CHROMEDRIVER_PATH`, `GOOGLE_MAPS_API_KEY`, `ANTHROPIC_API_KEY`, `PORT`.

**Config-Dict** (wird als `results/config_<id>.json` an die Scraper übergeben):
```json
{
  "search_parameters": {"location","check_in","check_out","guests","min_bedrooms","search_radius_km","property_type"},
  "filters": {"max_price_per_night_chf","min_rating_airbnb","min_rating_booking","min_rating_hotels","min_rating_expedia",
              "min_rating","min_number_of_reviews","superhost_only","instant_book_only","max_price","min_reviews"},
  "amenities": {"private_pool":{"required":false}, "private_whirlpool":..., "private_sauna":..., "fireplace":..., "parking":...},
  "location_settings": {"radius_km", "use_exact_location": false},
  "output": {"max_results": MAX_RESULTS, "max_pages": MAX_PAGES, "save_to_csv": true, "save_to_html": true},
  "scraping_settings": {"headless": true, "wait_time_seconds": 3}
}
```
`save_results()` der Scraper wird im Web-Flow **nicht** aufgerufen, nur in deren `main()` beim CLI-Aufruf. Der Report kommt aus `app.py`.

---

## 5. Deployment und Betrieb

### 5.1 Render (Backend)
- **Ressourcen:** Free-Plan, 512 MB RAM, 0,1 CPU, Docker, Frankfurt.
- **Deploy:** Auto-Deploy bei Push auf `main`. Mit Build-Cache ist der Service etwa **1 Minute** nach dem Push live (gemessen am 28.10.: Push 18:50:09, neue Instanz 18:51:21).
- **Env-Vars im Dashboard** (Stand 28.10.2026, gesetzt am 28.10.):
  - gesetzt: `MAX_RESULTS=15`, `MAX_PAGES=2`;
  - **nicht gesetzt:** `GOOGLE_MAPS_API_KEY` (deshalb sind die Airbnb-Distanzen 0 km) und `ANTHROPIC_API_KEY` (deshalb keine KI-Analyse);
  - aus dem Dockerfile: `LOW_MEMORY=1`, `CHROME_BIN`, `CHROMEDRIVER_PATH`.
  - Ob Miroslav seither Keys eingetragen hat, ist unbekannt; im Dashboard nachsehen lassen.
- **Spin-down:** Free-Instanzen schlafen nach etwa 15 min ohne eingehenden Traffic. Ein Kaltstart dauert ≥ 50 s.
  - Während einer Suche hält das 2-s-Polling des offenen Browser-Tabs die Instanz wach.
  - **Risiko (nicht getestet):** Schließt man den Tab während einer langen Suche, kann Render die Instanz schlafen legen, und die Suche geht verloren.
- **Flüchtiges Dateisystem:** `results/` und `favorites.db` gehen bei jedem Deploy und Neustart verloren. **Favoriten auf Render sind also nicht dauerhaft** (siehe 8.4).
- **RAM-Zustand im Speicher:** `search_status` liegt im RAM; ein Neustart (Deploy, OOM) liefert für laufende IDs 404.
- **Logs:** Render-Dashboard → Logs. Der Log-Viewer ist virtualisiert und rendert nur etwa 100 Zeilen. Mit dem URL-Parameter `?q=<Suchtext>&r=1h` filtern, z. B. `q=⚠`, `q=breche`, `q=CHF`, `q=Reisedaten`, `q=Chrome`. Für neue Zeilen die Seite neu laden.
- **Beim Start** loggt `app.py` die Chrome-Version, z. B. „✅ Chrome gefunden: Chromium …“.

### 5.2 Vercel (Frontend)
- Statisches `index.html`, deployt automatisch bei Push. Am 11.11.2026 geprüft: Status 200, die Seite enthält die onrender-API-URL.
- Für Vercel gibt es keine weitere Konfiguration im Repo.

### 5.3 Hosting-Alternativen (Recherche Oktober 2026, Preise können sich geändert haben)
- Render Starter (rund $7/Monat) hat ebenfalls nur 512 MB und bringt beim RAM also nichts. Mehr Speicher gibt es erst ab Render Standard (2 GB, rund $25).
- Railway (rund $5, verbrauchsabhängig) lief früher.
- Miroslav will Render Free behalten. Die Suche darf lange dauern („ich habe ja keinen Stress“), muss aber zu Ende laufen.

---

## 6. Plattformen im Detail

### 6.1 Airbnb (`airbnb_searcher.py`)
- **URL:** `https://www.airbnb.ch/s/<ort>/homes?checkin=&checkout=&adults=&min_bedrooms=&price_max=` plus Typfilter (`property_type_id[]` bzw. `room_types[]`) und Pflicht-Ausstattungs-Codes (`amenities[]`: Pool 7, Whirlpool 25, Sauna 325, Kamin 27, Parkplatz 9).
- **Ablauf in `search()` (`:689`):**
  1. Cookie-Banner wegklicken.
  2. Pro Seite `[itemprop='itemListElement']` auslesen (`extract_listing_data`, `:188`). Das kostet **rund 15 WebDriver-Calls pro Karte und ist noch nicht gebündelt**.
  3. Den „Weiter“-Button bis `max_pages` klicken.
  4. Gesamtpreis in Preis pro Nacht umrechnen.
  5. Optional Google-Maps-Distanzen berechnen und danach sortieren.
  6. Für die ersten `max_results` Treffer `get_listing_details()` (`:370`) aufrufen. Das ist ein Detailseiten-Load im selben Tab mit `WebDriverWait` 30 s. Bilder, Reviews und Ausstattung werden seit `76b3c42` mit je einem `execute_script` gelesen.
  7. KI-Analyse ab 3 Reviews, sofern ein Key gesetzt ist.
  8. Filter anwenden.
- **Render:** rund 45 min für 15 Treffer. Etwa die Hälfte der Detailseiten läuft in den Timeout; diesen Treffern fehlen Bilder und Ausstattung, die Ergebnisse sind aber echt.
- **Größter Hebel:** `extract_listing_data` wie bei Booking in **ein** JS-Snapshot pro Karte (oder einmal für alle Karten) umbauen und Detailseiten in `LOW_MEMORY` begrenzen. Siehe 8.2.

### 6.2 Booking.com (`booking_searcher.py`)
- **URL** (`build_search_url`, `:59`): `searchresults.de.html?ss=<location>&checkin&checkout&group_adults&no_rooms&group_children&price=CHF-0-CHF-<max>`. Dazu kommen:
  - `nflt=ht_id=…` je Unterkunftstyp;
  - `review_score`;
  - `mealplan` (`:118`), das aber nie ankommt (siehe 8.1).
- **Ablauf in `search()`:**
  1. `driver.get`, 5 s warten, Popups schließen.
  2. **Warten (max. 180 s, Poll 2 s) mit `RESULTS_STATE_JS` (`:215`).** Das Ergebnis ist `'cards'`, sobald `[data-testid='property-card']` da ist. Enthält die URL `errorc_`, kommt die URL zurück, und die Suche **bricht sofort ab** (`:473–483`, Log „🚫 Booking zeigt eine Fehlerseite statt Ergebnissen (errorc_…) - breche ab“ plus URL).
  3. Ohne `LOW_MEMORY` dreimal scrollen, um mehr Karten zu laden. Mit `LOW_MEMORY` nicht, weil 75 Karten den Renderer abstürzen ließen.
  4. Karten über eine Selektor-Kaskade finden (Strategy 1–3, `> 3` Treffer nötig).
  5. **Keine Karten:** Es gibt **kein** Fallback mehr. Geloggt werden Titel, URL und die ersten 600 Zeichen der Seite, außerdem wird `/tmp/booking_debug.html` geschrieben, was auf Render nicht erreichbar ist.
     - Das frühere „jedes div mit Preis“-Fallback erzeugte auf Render 15 Fake-Treffer („Support“, Preis 0) und lokal Duplikate.
  6. Pro Karte **ein** `execute_async_script(CARD_SNAPSHOT_JS)` (`:193`). Es scrollt die Karte in die Mitte, wartet 500 ms und liefert Text, den ersten Treffer je Selektor, Links und bis zu 20 Bild-URLs.
  7. Bilder von der Detailseite werden nur ohne `LOW_MEMORY` nachgeladen.
  8. `filter_properties`: Preis, Rating, Reviews, Radius (`distance_km` aus dem Kartentext „x km vom Zentrum“).
- **Render:** Booking leitet **jede** Suche auf `https://www.booking.com/index.de.html?...&errorc_searchstring_not_found=ss` um (Titel „Booking.com | Offizielle Seite | …“, Währung EUR).
  - Getestet mit „Interlaken“ und „Lanzarote, Spanien“.
  - Lokal funktioniert dieselbe URL; lokal hängt Booking zwar einen `chal_t=`-Challenge-Parameter an, die Ergebnisse laden aber.
  - Sehr wahrscheinlich ist das Bot-Schutz gegen die Rechenzentrums-IP.
  - Ein Versuch über `autocomplete.json` lieferte 403 und wurde verworfen.
  - **Entscheidung: Den Bot-Schutz nicht umgehen** (siehe 11).
- **Messwerte:**
  - Render, nur Booking, live am 28.10. um 18:51:29–18:52:55: rund 1,5 min, 0 Treffer, Abbruchmeldung im Log um 18:52:53.
  - Lokal, Interlaken: 45 Karten gefunden, 15 ausgelesen, 12 nach Filter, 39 s.
  - Lokal, erzwungene Fehlerseite: Abbruch nach 22 s.
  - Lokal, unbekanntes Ziel: Booking zeigt eine normale Seite mit „0 Unterkünfte“ ohne `errorc_`, die Suche wartet die vollen 180 s (204 s, 0 Treffer). Das ist bewusst unverändert.
- **WebDriver-Calls lokal:** 345 vor der Optimierung, 47 danach.

### 6.3 Google Hotels (`google_hotels_searcher.py`)
- **URL:** `https://www.google.com/travel/search?q=hotels in <ort>&hl=de&gl=ch&curr=CHF&ts=<base64-Protobuf>`. `build_ts_param()` kodiert Daten, Erwachsene und Währung CHF. Die alte URL `google.com/search?ibp=htl` funktioniert nicht mehr (normale Websuche, Daten werden ignoriert).
- **Ablauf:**
  1. Consent-Seite (`consent.google.com`) wegklicken.
  2. `wait_for_cards` (60 s).
  3. Prüfen, ob die Daten übernommen wurden (`dates_applied`, liest die Datumsfelder mit deutschen und englischen Monatskürzeln). Falls nicht, im Kalender setzen (`set_dates_in_ui`); scheitert das, gibt es **keine** Ergebnisse, weil die Preise sonst falsch wären.
  4. Pro Seite (20 Hotels) `wait_for_prices` (bis 120 s, bis der erste `a[aria-label^="Preise ab"]` da ist).
  5. `EXTRACT_CARDS_JS` liest alle Karten in **einem** Call (`div[jsname="mutHjb"]`, Fallback über `h2`).
  6. Treffer ohne Preis, Duplikate und Werbung (Keyword-Liste) verwerfen.
  7. `go_to_next_page`.
  8. Filter: Rating aus dem Frontend auf der 10er-Skala, Google nutzt 5 → durch 2 teilen.
- **Preis-Regex:** Währung und Betrag müssen auf **derselben Zeile** stehen (`(?:CHF|Fr\.)[^\S\n]*(\d…)`). Sonst wurde das Rating als Preis gelesen („CHF 45“ bei 4,5 Sternen).
- **Render:** rund 2 min (Interlaken, 13 Treffer, korrekte Preise). Booking und Google zusammen: 5 min.

---

## 7. Verlauf der letzten Commits (alle 25.–28.10.2026)

| Commit | Inhalt |
|---|---|
| `b73f1fe` | **Render wieder lauffähig.** <br>– Dockerfile mit Debian-Chromium und passendem Chromedriver, `$PORT`; `render.yaml`. <br>– `chrome_driver.py` mit Low-Memory-Flags und Page-Load-Timeout. <br>– Airbnb: Parsing von „Fr. X Gesamtpreis“. <br>– Booking: Umrechnung Gesamtpreis → pro Nacht. <br>– `app.py`: Google Hotels aktiv, Chrome-Version im Log, Limits per Env, relative Report-URLs, liefert `index.html` und `favorites.html` aus. <br>– Frontend: stoppt das Polling bei 404. <br>– `anthropic` in `requirements.txt`. <br>– Maps: Land des Ursprungsorts statt fix „Switzerland“. |
| `8723094` | Google Hotels komplett neu über google.com/travel mit `ts`-Parameter. |
| `76b3c42` | **Hänger auf 0,1 CPU behoben.** <br>– Airbnb: Bilder, Reviews und Ausstattung per Script statt pro Element; Detailseite im selben Tab. <br>– Booking in `LOW_MEMORY`: kein Nachscrollen, keine Detailbilder. <br>– `app.py`: try/except pro Plattform. |
| `1ee0d32` | Booking: ein Roundtrip pro Karte (`CARD_SNAPSHOT_JS`), Wartezeit 180 s auf die erste Karte, Script-Timeout 90 s. |
| `c360501` | Booking: Fake-Fallback entfernt, Diagnose-Log eingebaut. Google Hotels: auf Preise warten, Same-Line-Regex. |
| `63d477e` | Booking: Sofortabbruch bei `errorc_`-Fehlerseite. |

Die ursprünglichen Ursachen des Render-Hängers waren:
1. Die native Python-Runtime hatte kein Chrome. Selenium Manager lud Chrome erst zur Laufzeit herunter (73 s), es gab keine Speicher-Flags und keine Env-Vars, und der Prozess lief in den OOM.
2. Nach der Umstellung auf Docker blieben die Element-für-Element-WebDriver-Schleifen auf 0,1 CPU stecken.

---

## 8. Bekannte Bugs und offene Punkte (verifiziert im Code, priorisiert)

1. **Verpflegungsfilter wirkungslos.**
   - `index.html:856` schickt `meal_plan`, aber `SearchParams` (`app.py:73`) hat kein solches Feld. Pydantic verwirft unbekannte Felder still, und `run_search` schreibt es nicht in `search_parameters`.
   - `booking_searcher.py:118` liest `params.get('meal_plan')` und bekommt deshalb nie etwas.
   - Fix: Feld `meal_plan: List[str] = []` ergänzen und in `config["search_parameters"]` übernehmen.
   - Prüfen, ob die Booking-Parameter (`mealplan=999/2/3`) noch stimmen. Google Hotels ignoriert die Verpflegung (die UI behauptet „Booking & Google Hotels“).
2. **Airbnb zu langsam auf Render (rund 45 min).** `extract_listing_data` bündeln, analog zu `CARD_SNAPSHOT_JS`. Danach Detailseiten-Timeouts und -Anzahl in `LOW_MEMORY` überdenken. Vorher und nachher die WebDriver-Calls zählen (Methode: siehe 9.4).
3. **Report-HTML unescaped** (`app.py:286–437`). Titel, Ort und URLs werden roh ins HTML geschrieben. `SEARCH_LOCATION` steht unescaped in einem JS-String-Literal (`app.py:390`); ein `'` im Ortsnamen bricht das Script, und es ist eine XSS-Lücke. `html.escape` bzw. `json.dumps` verwenden.
4. **Favoriten auf Render nicht persistent** (SQLite im flüchtigen Container). Für eine Lösung braucht es eine Entscheidung von Miroslav, z. B. eine externe DB oder Render Disk (kostenpflichtig).
5. **Doppelte Route** `/results/{filename}` (`app.py:537` und `:565`). Die zweite ist toter Code; entfernen.
6. **Versehentlich getrackt:** `__pycache__/airbnb_searcher.cpython-312.pyc` und `results/config_*.json`. Mit `git rm --cached` entfernen (nur nach Rückfrage committen).
7. **`review_analyzer.py:92`**: Die Modell-ID `claude-sonnet-4-20250514` ist alt und könnte abgeschaltet sein. Vor einer Aktivierung die aktuelle Anthropic-Modellliste prüfen (aktuelle Generation: Claude 5, z. B. `claude-sonnet-5-5`). Auf Render ist ohnehin kein Key gesetzt.
8. **`start_server.bat`** installiert nur `fastapi uvicorn pydantic selenium pandas requests python-multipart aiofiles`.
   - Es fehlt vor allem `anthropic`. (`googlemaps` steht zwar in `requirements.txt`, wird aber nirgends importiert; `google_maps_distance.py` nutzt `requests`.)
   - Folge: `review_analyzer` importiert `anthropic` auf Modulebene, und `app.py` lädt es beim Report-Bau. Eine lokale Suche **mit Treffern** scheitert dann mit ImportError am Ende.
   - Besser: `pip install -r requirements.txt`.
9. **Report-Links veralten:** Jede neue Suche löscht alle älteren `search_results_*.html`, alte Report-Links liefern danach 404. Der Report zeigt außerdem nur die ersten 50 Treffer.
10. **`/tmp/booking_debug.html`** (`booking_searcher.py:549`), ebenso in den alten Expedia- und Hotels.com-Scrapern: Unter Windows existiert `/tmp` meist nicht; der Fehler wird abgefangen. Besser wäre `tempfile.gettempdir()` wie bei Google Hotels.
11. **CORS:** `allow_origins=["*"]` zusammen mit `allow_credentials=True`. Funktioniert, ist aber unsauber; auf die Vercel-Domain plus localhost einschränken.
12. **Frontend schickt kein `min_bedrooms`**, es gilt immer der Default 1.
13. **`runtime.txt`, `railway.json`, `Aptfile`, `expedia_searcher.py`, `hotelscom_searcher.py`, alte READMEs:** Aufräumkandidaten. Nur nach Rückfrage löschen.
14. **Booking auf Render: 0 Treffer.** Offen und bewusst so gelassen. Mögliche Wege, alle **nur mit Miroslavs ausdrücklicher Zustimmung**:
    - offizielle Booking-Affiliate- oder Demand-API;
    - Booking nur lokal nutzen (`start_server.bat`);
    - anderes Hosting.
    - **Kein** Umgehen des Bot-Schutzes (Proxies, Stealth, Captcha-Lösen o. Ä.).

---

## 9. Lokale Entwicklung und Tests

### 9.1 Umgebung (Stand 11.11.2026)
- **Betriebssystem:** Windows 11, Shells PowerShell 5.1 und Git Bash.
- **Python:** `python` ist 3.11.9; Python 3.12 ist ebenfalls installiert (`py -3.12`). **Keine** der beiden Installationen hat die Projekt-Abhängigkeiten installiert. Die frühere Test-venv unter `%TEMP%\abv` ist gelöscht.
- **Chrome:** 157 lokal installiert. Selenium 4.17.2 holt den passenden Treiber über Selenium Manager (mit Chrome 156 getestet).
- **Docker:** nutzt Python 3.12, daher lokal ebenfalls **3.12** empfohlen.

### 9.2 Setup und Start (venv außerhalb des Repos, weil `.venv` weder in `.gitignore` noch in `.dockerignore` steht)
```powershell
py -3.12 -m venv "$env:TEMP\acc-venv"
& "$env:TEMP\acc-venv\Scripts\python.exe" -m pip install -r "C:\Projekt\Airbnb Suche\webapp\requirements.txt"
cd "C:\Projekt\Airbnb Suche\webapp"
$env:LOW_MEMORY = "1"      # optional: Render-Verhalten nachstellen (keine Bilder, kein Booking-Nachscrollen)
$env:MAX_RESULTS = "15"; $env:MAX_PAGES = "2"
& "$env:TEMP\acc-venv\Scripts\python.exe" -m uvicorn app:app --port 8000
# → http://localhost:8000
```

### 9.3 Einzelnen Scraper ohne Server testen
Config-Datei, z. B. in einem Temp-Ordner, **nicht im Repo**:
```json
{"search_parameters": {"location": "Interlaken", "check_in": "2026-12-04", "check_out": "2026-12-06", "guests": 2, "min_bedrooms": 1, "search_radius_km": 50, "property_type": "house"},
 "filters": {"max_price_per_night_chf": 400, "min_rating_booking": 0, "min_rating": 0, "min_number_of_reviews": 0, "max_price": 400, "min_reviews": 0},
 "amenities": {}, "location_settings": {"radius_km": 50, "use_exact_location": false},
 "output": {"max_results": 15, "max_pages": 2, "save_to_csv": false, "save_to_html": false},
 "scraping_settings": {"headless": true, "wait_time_seconds": 3}}
```
Das Check-in-Datum muss in der Zukunft liegen.
```python
import os, sys, time
sys.path.insert(0, r"C:\Projekt\Airbnb Suche\webapp")
os.environ.setdefault('LOW_MEMORY', '1')
from booking_searcher import BookingSearcher          # bzw. google_hotels_searcher.GoogleHotelsSearcher / airbnb_searcher.AirbnbSearcher
s = BookingSearcher(r"C:\pfad\zu\test_config.json")
# Render-Fehlerseite nachstellen:
# s.build_search_url = lambda: "https://www.booking.com/index.de.html?errorc_searchstring_not_found=ss"
t0 = time.time(); s.search(); print(len(s.results), "Treffer in", round(time.time() - t0), "s")
```
Vor dem Start `PYTHONIOENCODING=utf-8` setzen, denn die Logs enthalten Emojis.

### 9.4 WebDriver-Calls zählen (für Performance-Arbeit)
`selenium.webdriver.remote.webdriver.WebDriver.execute` per Monkeypatch mit einem Zähler umhüllen, die Suche laufen lassen und die Summe ausgeben.

Faustregel: Auf Render kostet jeder Call Sekunden. Ziel sind wenige Calls pro Karte, idealerweise ein Call pro Seite.

### 9.5 Live-Test auf Render (Git Bash)
```bash
BASE=https://accommodation-search.onrender.com
RESP=$(curl -s -m 120 -X POST "$BASE/api/search" -H 'Content-Type: application/json' \
  -d '{"location":"Interlaken","check_in":"2026-12-04","check_out":"2026-12-06","guests":2,"max_price":400,"platforms":["google_hotels"]}')
ID=$(echo "$RESP" | python -c "import sys,json; print(json.load(sys.stdin)['search_id'])")
while sleep 10; do
  S=$(curl -s -m 30 -w " [HTTP %{http_code}]" "$BASE/api/search/$ID"); echo "$(date +%T) $S"
  echo "$S" | grep -qE '"status":"(completed|failed)"|HTTP (404|5..)' && break
done
```
- Den Report bekommst du über `$BASE` + `html_report_url`.
- Erst `/health` aufrufen, um die Instanz aufzuwecken (Kaltstart ≥ 50 s).
- **Nie zwei Suchen gleichzeitig starten** (siehe 10.3). Vorher mit Miroslav abklären, weil eine laufende Testsuche den Dienst für ihn blockiert.
- Eine volle Suche mit allen drei Plattformen dauert rund 50 min.

### 9.6 Es gibt keine automatisierten Tests und keine CI
Abgesehen von den Vercel-Checks auf GitHub gibt es nichts. Prüfung bisher: lokal gegen die echten Seiten laufen lassen, dann live auf Render.

---

## 10. Lessons learned (verbindlich für neuen Scraper-Code)

1. **DOM-Lesungen bündeln.** Auf Render (0,1 CPU) dauert jeder WebDriver-Roundtrip (`find_element`, `.text`, `get_attribute`, `click` …) Sekunden. Alles, was gelesen wird, sollte in einem `execute_script` oder `execute_async_script` passieren und strukturierte Daten zurückgeben.
2. **`.text` von Selenium liefert '' für nicht gerenderte Elemente.** Booking rendert Karten nur in Viewport-Nähe. Im JS deshalb `el.getClientRects().length ? el.innerText : ''` nachbilden, vorher `scrollIntoView` und kurz warten, `\u00a0` durch ein Leerzeichen ersetzen.
3. **Nie zwei Suchen gleichzeitig auf Render.** Zwei Chromes überschreiten 512 MB, das führt zum OOM, die Instanz startet neu und alle Status sind weg.
4. **`LOW_MEMORY=1` beachten:** keine Bilder, `eager` Page-Load, Renderer-Limit. Bilder-URLs stehen trotzdem im HTML. Keine zweiten Tabs.
5. **Nichts erfinden, wenn nichts gefunden wird.** Lieber 0 Treffer plus aussagekräftiges Log als Fallbacks, die Footer-Blöcke zu „Unterkünften“ machen.
6. **Deploy-Erkennung ohne Dashboard (Marker-Trick):**
   - `POST /api/search` mit `"platforms":["expedia"]` starten. Das läuft ohne Chrome sofort durch.
   - Die ID merken und alle 10 s abfragen.
   - Kommt **404**, ist eine neue Instanz live (der RAM-Status ist weg), und `/health` antwortet.
   - Alternativ fragt Miroslav die Render-Events-Seite ab.
7. **Google Travel lädt Preise nach den Karten.** Immer auf den „Preise ab“-Link warten, bevor gelesen wird.
8. **Booking-Fehlerseiten erkennt man an `errorc_` in der URL.**
9. **Logs sind Deutsch mit Emojis** (✓ ⚠ ❌ 🚫 📍 …). Neue Logzeilen im selben Stil schreiben, damit die Render-Logsuche (`q=`) funktioniert.
10. **Code-Stil:** Kommentare und Bezeichner auf Englisch, Log- und UI-Texte auf Deutsch. Die Kommentardichte des umgebenden Codes übernehmen.

---

## 11. Spielregeln von Miroslav (unbedingt einhalten)

- **Kommunikation** auf Deutsch.
- **Committen und Pushen nur nach ausdrücklicher Zustimmung**, und zwar jedes Mal neu. Ein Push auf `main` deployt sofort Backend (Render) und Frontend (Vercel).
- **Git:**
  - Die Git-Config **nicht ändern**.
  - Commits mit demselben Autor wie die bisherigen anlegen, per `git -c user.name=… -c user.email=… commit`; Name und E-Mail aus `git log -1 --format='%an <%ae>'` übernehmen.
  - Commit-Messages wie bisher im Conventional-Stil (`fix:`, `feat:`) auf Englisch, mit erklärendem Body.
- **`PROJECT_SUMMARY.md` nie committen.**
- **Render-Dashboard:**
  - Grundsätzlich **nur lesen**; Änderungen (Env-Vars, Runtime, Plan) nur nach ausdrücklicher Zustimmung.
  - **Anmelden macht Miroslav selbst.** Niemals Passwörter oder Zugangsdaten eingeben.
  - **Werte von Secrets (API-Keys) nie ausgeben**, auch nicht in Logs, Commits oder Doku.
- **Booking-Bot-Schutz nicht umgehen** (keine Proxies, Stealth-Plugins, Captcha-Löser, IP-Rotation). Andere Wege zu Booking nur nach Rückfrage.
- **Live-Tests auf Render:** immer nur eine Suche gleichzeitig. Lange Laufzeiten sind okay, die Suche muss aber fertig werden.
- **Destruktive Git-Operationen** (force-push, reset --hard, Dateien löschen) nur nach Rückfrage.

---

## 12. Offene Entscheidungen und Aufgaben bei Miroslav

- `GOOGLE_MAPS_API_KEY` im Render-Dashboard setzen, damit Airbnb echte Distanzen und die Radius-Sortierung bekommt. Stand 28.10.: nicht gesetzt.
- Optional `ANTHROPIC_API_KEY` setzen, falls die KI-Review-Analyse gewünscht ist. Dann vorher die Modell-ID aktualisieren (8.7).
- Booking: bei 0 Treffern auf Render bleiben, oder Affiliate-API, lokaler Betrieb bzw. anderes Hosting? (8.14)
- Dauerhafte Favoriten auf Render gewünscht? (8.4)
- Aufräumen der Altlasten (8.6, 8.13) freigeben?

## 13. Vorgeschlagene nächste Schritte für Codex (in dieser Reihenfolge, jeweils lokal testen, dann vor dem Push fragen)

1. Verpflegungsfilter durchreichen (8.1). Klein und klar.
2. Doppelte Route entfernen und Report-HTML escapen (8.5, 8.3).
3. Airbnb-Extraktion bündeln (8.2), mit Call-Zählung vorher und nachher. Danach **ein** Live-Test auf Render nur mit Airbnb, nach Absprache.
4. Getrackte Junk-Dateien aus dem Index nehmen und `.gitignore`/`.dockerignore` um `.venv` ergänzen (8.6).
5. `start_server.bat` auf `pip install -r requirements.txt` umstellen (8.8).
