#!/bin/sh
set -e
# Apply pending migrations before serving. Safe to run repeatedly.
alembic upgrade head
exec "$@"
