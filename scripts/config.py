import os

# Single source of truth for the DB connection; override with DATABASE_URL.
DB_URL = os.getenv("DATABASE_URL", "postgresql://permit:permit@localhost:5432/needtoknow")
