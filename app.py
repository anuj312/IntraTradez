"""WSGI entrypoint for Gunicorn.

Usage on Render:
  gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --worker-class gthread --threads 8 --timeout 120
"""

import threading
from live_scanner_server import app, initialize_live  # Flask WSGI app

# For Gunicorn deployments, start instrument/token validation and the tick
# connection on worker boot, not on the first user request after market open.
threading.Thread(target=initialize_live, name="pre-market-warmup", daemon=True).start()