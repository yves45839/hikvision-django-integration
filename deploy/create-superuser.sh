#!/usr/bin/env bash
# create-superuser.sh — créer le premier compte admin Django
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f deploy/docker-compose.prod.yml --env-file .env.production \
  exec web python manage.py createsuperuser
