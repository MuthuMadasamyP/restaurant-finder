# Restaurant Finder

Restaurant Finder is a FastAPI web application for searching restaurants from Google Maps, showing ranked results in a browser UI, saving user/admin activity in MySQL, and exporting restaurant shortlists to Excel.

The current app includes a separate user login/signup page, a separate admin portal, search limits, search history, feedback, star-hotel search analytics, city-wise favourite restaurant tracking, speech input, and Excel export.

## Current Features

- User signup and login with JWT authentication
- Admin login and admin control portal
- Restaurant search by location, radius, and result count
- Google Maps scraping with Playwright
- Browser results table with rating sort and shortlist search
- Favourite button for each restaurant result
- City-specific favourite restaurant tracking for Chennai, Madurai, and Coimbatore
- Star-hotel search tracking when the user searches terms like `5 star hotel`
- Feedback and rating submission
- Admin dashboard with live refresh
- Search limit settings from the admin portal
- Year-wise and area-wise admin analytics
- Excel export for searched restaurant results
- Speech input for location entry
- MySQL database storage with SQLite fallback

## Project Structure

```text
restaurant-finder/
|-- main.py                         # Root launcher for uvicorn main:app
|-- requirements.txt                # Python dependencies
|-- README.md                       # Project overview
|-- DB.md                           # Database setup and table details
|-- source/
    |-- backend/
    |   |-- .env.example            # Example local environment config
    |   |-- database.py             # SQLAlchemy engine/session and MySQL DB creation
    |   |-- main.py                 # FastAPI app, routers, frontend serving
    |   |-- app/
    |   |   |-- main.py             # Compatibility wrapper for app.main:app
    |   |-- models/
    |   |   |-- admin_data.py       # SQLAlchemy database tables
    |   |   |-- admin_schemas.py    # Admin/auth/feedback request schemas
    |   |   |-- restaurant.py       # Search/export Pydantic schemas
    |   |-- routes/
    |   |   |-- admin.py            # Admin dashboard and analytics APIs
    |   |   |-- auth.py             # User/admin login and signup APIs
    |   |   |-- export.py           # Excel export API
    |   |   |-- feedback.py         # Feedback and favourite restaurant APIs
    |   |   |-- search.py           # Restaurant search API
    |   |   |-- speech.py           # Speech transcription API
    |   |-- services/
    |       |-- auth.py             # Password hashing and JWT helpers
    |       |-- bootstrap.py        # Table creation and default seed data
    |       |-- exporter.py         # Excel workbook generation
    |       |-- scraper.py          # Google Maps scraper
    |       |-- speech_recognizer.py # Speech recognition helper
    |-- frontend/
        |-- auth.html               # User login/signup page
        |-- index.html              # User application page
        |-- admin.html              # Admin portal page
        |-- static/
            |-- css/
            |   |-- styles.css      # User UI styles
            |   |-- admin.css       # Admin UI styles
            |-- js/
                |-- auth.js         # User login/signup behavior
                |-- app.js          # User app behavior and API calls
                |-- admin.js        # Admin portal behavior and live refresh
                |-- speech-input.js # Microphone recording UI
```

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Install Playwright Chromium:

```powershell
playwright install chromium
```

Create the backend environment file:

```powershell
cd D:\restaurant-finder\source\backend
copy .env.example .env
```

Edit `.env` with your local MySQL username/password:

```env
DATABASE_URL=mysql+pymysql://root:YOUR_MYSQL_PASSWORD@127.0.0.1:3306/restaurant_finder
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin@123
SECRET_KEY=change-this-secret-key
```

The real `.env` is ignored by Git because it contains secrets.

## Run

From the backend folder:

```powershell
cd D:\restaurant-finder\source\backend
python -m uvicorn app.main:app --reload --port 800 --env-file .env
```

Open:

```text
User login:  http://127.0.0.1:800/login
User app:    http://127.0.0.1:800/app
Admin app:   http://127.0.0.1:800/admin
API docs:    http://127.0.0.1:800/docs
Health:      http://127.0.0.1:800/health
```

You can also run from the project root:

```powershell
cd D:\restaurant-finder
python -m uvicorn main:app --reload --port 800 --env-file source/backend/.env
```

## Default Admin

Default admin is seeded on startup if it does not exist:

```text
Username: admin
Password: Admin@123
```

Change `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env` before real use.

## Main API Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/signup` | Create user account |
| `POST` | `/api/auth/login` | User login |
| `POST` | `/api/admin/login` | Admin login |
| `POST` | `/api/search` | Search restaurants and store search history |
| `POST` | `/api/export` | Download Excel export |
| `POST` | `/api/feedback` | Save user feedback |
| `POST` | `/api/favorite-restaurant` | Save selected restaurant as city favourite |
| `POST` | `/api/speech/transcribe` | Convert microphone audio to text |
| `GET` | `/api/admin/summary` | Admin dashboard counts |
| `GET` | `/api/admin/search-history` | User search history table |
| `GET` | `/api/admin/feedback` | Feedback table |
| `GET` | `/api/admin/star-hotels` | Star hotel searches table |
| `GET` | `/api/admin/area/{area_name}` | Area analytics |
| `GET`/`PUT` | `/api/admin/settings` | Read/update search limits |

## Data Flow

```text
User signs in
  |
  v
Search request -> /api/search
  |
  |-- writes search_history
  |-- writes star_hotel_searches only if location contains a star-hotel keyword
  v
Playwright scraper returns restaurant results
  |
  v
User clicks Favourite
  |
  v
/api/favorite-restaurant writes to city favourite table
```

Feedback is stored through `/api/feedback`. Admin screens read directly from MySQL-backed API endpoints and refresh every 10 seconds while logged in.

## Database

Database details are documented separately in [DB.md](DB.md).

Short version:

- Default configured database is MySQL database `restaurant_finder`
- SQLAlchemy creates the database and tables on app startup
- SQLite fallback exists only when `DATABASE_URL` is not set
- Current MySQL table count: 10 app tables

## Cleanup Notes

Removed generated/unwanted files:

- Python `__pycache__` folders
- Empty `source/backend/README.md`

Kept intentionally:

- `.venv/` because it is your local working environment
- `source/backend/restaurant_finder.db` because it is a SQLite fallback/backup from before MySQL migration
- `source/backend/app/` because your command uses `app.main:app`
- root `main.py` because it supports running `uvicorn main:app` from project root
- `paladar-reference.png` and `Python Web Scraping.docx` because they look like user-provided reference files, not generated code

## Troubleshooting

If the admin page looks old after a code change:

```text
Ctrl + F5
```

If MySQL tables are missing, start the backend once with `.env`:

```powershell
python -m uvicorn app.main:app --reload --port 800 --env-file .env
```

If scraping fails, reinstall Playwright Chromium:

```powershell
playwright install chromium
```
