#!/usr/bin/env bash
set -e

echo "==> Installing dependencies..."
pip install -r requirements.txt

echo "==> Collecting static files..."
python manage.py collectstatic --no-input

echo "==> Running migrations..."
python manage.py makemigrations
python manage.py migrate

echo "==> Seeding database..."
python manage.py minimal_populate_db

echo "==> Build complete."