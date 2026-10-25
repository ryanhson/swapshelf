# SwapShelf

Campus buy/sell board. Students post textbooks, chargers, and dorm leftovers. Buyers message the seller. Sellers can mark a listing sold.

Django, templates, SQLite.

## Features

- Register, sign in, sign out
- Public board with a category filter
- Post, edit, and mark sold
- Message threads on a listing
- Profile page (name, email, department-board flag)
- Department desk for board accounts

## Run locally

Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed
python manage.py runserver 0.0.0.0:3000
```

Open http://localhost:3000. The database is `data/swapshelf.db`.

## Run with Docker

```bash
docker compose up --build
```

The app listens on port 3000.

## Demo accounts

Sign in with the username, not the email.

| Username | Password | Notes |
|---|---|---|
| `alex` | `campus123` | Has a charger and a bike |
| `jordan` | `campus123` | Has a textbook and a message thread |
| `sam` | `foundit!` | Has a sold lamp |
| `desk` | `deskpass1` | Department-board account; can open the desk |

## Project layout

```
market/models.py     Listing, thread, message
market/views.py      Board, edit, messages, profile, desk
market/forms.py      Listing form and profile form
market/seed.py       First-run demo data
swapshelf/settings.py
```
