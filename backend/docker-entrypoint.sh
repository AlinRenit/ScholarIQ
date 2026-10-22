#!/bin/sh
set -e
# Apply pending migrations and load curriculum content before serving.
# Both steps are idempotent.
alembic upgrade head
python -m scholariq.curriculum.sync
exec "$@"
