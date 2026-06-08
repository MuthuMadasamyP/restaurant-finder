# Database Guide

Restaurant Finder stores application data in MySQL when `DATABASE_URL` is configured. SQLite is kept only as a fallback if `DATABASE_URL` is missing.

## Connection

Local MySQL connection used by the app:

```env
DATABASE_URL=mysql+pymysql://root:YOUR_MYSQL_PASSWORD@127.0.0.1:3306/restaurant_finder
```

For MySQL Workbench:

```text
Connection Method: Standard (TCP/IP)
Hostname: 127.0.0.1
Port: 3306
Username: root
Default Schema: restaurant_finder
```

Do not commit the real password. Store it only in:

```text
source/backend/.env
```

An example file is available at:

```text
source/backend/.env.example
```

## Configuration Files

| File | Purpose |
| --- | --- |
| `source/backend/.env` | Local database URL and secrets |
| `source/backend/.env.example` | Safe template for local setup |
| `source/backend/database.py` | Creates SQLAlchemy engine and creates MySQL database if missing |
| `source/backend/services/bootstrap.py` | Creates tables and seeds default admin/settings |
| `source/backend/models/admin_data.py` | SQLAlchemy table models |

## Startup Behavior

When the backend starts:

1. Uvicorn loads `.env` through `--env-file .env`.
2. `database.py` reads `DATABASE_URL`.
3. If the URL starts with `mysql`, the app runs `CREATE DATABASE IF NOT EXISTS restaurant_finder`.
4. `services.bootstrap.init_database()` runs `Base.metadata.create_all(bind=engine)`.
5. Missing tables are created automatically.
6. `seed_defaults()` inserts default `settings` and default admin if missing.

Start command:

```powershell
cd D:\restaurant-finder\source\backend
python -m uvicorn app.main:app --reload --port 800 --env-file .env
```

## Table Count

Current app tables: 10

```text
admins
users
search_history
feedback
star_hotels
star_hotel_searches
settings
chennai_favouritehotel
madurai_favouritehotel
coimbatore_favouritehotel
```

## Tables

### admins

Stores admin login accounts.

| Column | Meaning |
| --- | --- |
| `id` | Primary key |
| `username` | Unique admin username |
| `password_hash` | Hashed password |
| `created_at` | Creation timestamp |

Seeded from:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin@123
```

### users

Stores normal user accounts.

| Column | Meaning |
| --- | --- |
| `id` | Primary key |
| `name` | User display name |
| `email` | Unique login email |
| `password_hash` | Hashed password |
| `status` | `active`, `inactive`, or `blocked` |
| `created_at` | Signup timestamp |
| `last_login_at` | Last login timestamp |

### search_history

Stores every successful user restaurant search.

| Column | Meaning |
| --- | --- |
| `id` | Primary key |
| `user_id` | Foreign key to `users.id` |
| `location` | Search text/location |
| `radius` | Radius in km |
| `restaurant_count` | Requested result count |
| `searched_at` | Search timestamp |

Used by:

- Admin dashboard user-search table
- Year-wise search chart
- Area analytics
- Daily search limit counting

### feedback

Stores user feedback.

| Column | Meaning |
| --- | --- |
| `id` | Primary key |
| `user_id` | Foreign key to `users.id` |
| `rating` | Rating from 1 to 5 |
| `feedback` | Feedback message |
| `created_at` | Submit timestamp |

### star_hotel_searches

Stores only searches that contain star-hotel keywords, for example:

```text
5 star hotel in Avadi
3-star hotels Chennai
```

| Column | Meaning |
| --- | --- |
| `id` | Primary key |
| `user_id` | Foreign key to `users.id` |
| `star_term` | Normalized term such as `5 star hotel` |
| `search_area` | Full user search text |
| `created_at` | Search timestamp |

Working rule:

- Every search writes to `search_history`.
- Only star-keyword searches write to `star_hotel_searches`.
- Admin card **Star Hotel Searches** counts this table.

### star_hotels

Legacy/manual favourite hotel table used by `/api/star-hotels`.

| Column | Meaning |
| --- | --- |
| `id` | Primary key |
| `user_id` | Foreign key to `users.id` |
| `hotel_name` | Hotel name or label |
| `area` | Area text |
| `created_at` | Creation timestamp |

This table is kept for backward compatibility.

### chennai_favouritehotel

Stores favourite restaurant button clicks for Chennai searches.

| Column | Meaning |
| --- | --- |
| `id` | Primary key |
| `user_id` | Foreign key to `users.id` |
| `restaurant_name` | Restaurant selected by user |
| `search_area` | Search area/location |
| `rating` | Restaurant rating at click time |
| `category` | Restaurant category |
| `address` | Restaurant address |
| `created_at` | Favourite timestamp |

### madurai_favouritehotel

Same structure as `chennai_favouritehotel`, but for Madurai searches.

### coimbatore_favouritehotel

Same structure as `chennai_favouritehotel`, but for Coimbatore searches.

### settings

Stores admin-controlled app limits.

| Column | Meaning |
| --- | --- |
| `id` | Primary key |
| `daily_search_limit` | Normal per-user daily search limit |
| `special_event_limit` | Temporary event limit |
| `event_enabled` | Whether event limit overrides daily limit |
| `active_user_days` | Days used for active-user analytics |

## Relationships

```text
users.id
  |-- search_history.user_id
  |-- feedback.user_id
  |-- star_hotels.user_id
  |-- star_hotel_searches.user_id
  |-- chennai_favouritehotel.user_id
  |-- madurai_favouritehotel.user_id
  |-- coimbatore_favouritehotel.user_id
```

`admins` and `settings` are standalone tables.

## Write Behavior

| User action | Table written |
| --- | --- |
| User signup | `users` |
| User login | updates `users.last_login_at` |
| Restaurant search | `search_history` |
| Search contains star keyword | `star_hotel_searches` |
| Submit feedback | `feedback` |
| Click favourite in Chennai result | `chennai_favouritehotel` |
| Click favourite in Madurai result | `madurai_favouritehotel` |
| Click favourite in Coimbatore result | `coimbatore_favouritehotel` |
| Admin changes settings | `settings` |

## Read Behavior

| Admin section | Tables read |
| --- | --- |
| Top user card | `users`, `search_history` |
| Feedback card | `feedback`, `users` |
| Star Hotel Searches card | `star_hotel_searches`, `users` |
| Chennai area | `search_history`, `chennai_favouritehotel`, `star_hotel_searches` |
| Madurai area | `search_history`, `madurai_favouritehotel`, `star_hotel_searches` |
| Coimbatore area | `search_history`, `coimbatore_favouritehotel`, `star_hotel_searches` |
| Settings page | `settings` |

## Useful SQL

Show tables:

```sql
USE restaurant_finder;
SHOW TABLES;
```

Check counts:

```sql
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM search_history;
SELECT COUNT(*) FROM feedback;
SELECT COUNT(*) FROM star_hotel_searches;
SELECT COUNT(*) FROM chennai_favouritehotel;
SELECT COUNT(*) FROM madurai_favouritehotel;
SELECT COUNT(*) FROM coimbatore_favouritehotel;
```

View latest star-hotel searches:

```sql
SELECT u.name, s.star_term, s.search_area, s.created_at
FROM star_hotel_searches s
JOIN users u ON u.id = s.user_id
ORDER BY s.created_at DESC;
```

View favourite restaurants:

```sql
SELECT restaurant_name, COUNT(*) AS favourite_count
FROM chennai_favouritehotel
GROUP BY restaurant_name
ORDER BY favourite_count DESC;
```

## SQLite Fallback

If `DATABASE_URL` is missing, the app falls back to:

```text
source/backend/restaurant_finder.db
```

For normal use, always start with:

```powershell
python -m uvicorn app.main:app --reload --port 800 --env-file .env
```

That keeps new data in MySQL.
