# I'Mobile - Phase 1 (Account Feature)

Django + PostgreSQL/Supabase. Tailwind via CDN. No SQLite.

## Setup
```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then paste your Supabase DATABASE_URL and a SECRET_KEY
python manage.py makemigrations   # migrations are already included; this is a safe no-op
python manage.py migrate
python manage.py seed_test_user
python manage.py runserver
```
Open http://127.0.0.1:8000/

## Test accounts (from `seed_test_user`)
| Role   | Username     | Password       |
|--------|--------------|----------------|
| Member | 24-4749-939  | ChangeMe123!   |
| Admin  | admin_demo   | ChangeMe123!   |

Both can also log in with their email (ram.espina@example.com / admin@imobile.example.com).

## Routes
/register/ /login/ /logout/ (POST) /dashboard/ /dashboard/member/ /dashboard/admin/ /profile/
