"""ASGI entrypoint matching Render's `uvicorn main:app` start command.

The live scanner serves its dashboard and APIs without user authentication. Uvicorn
serves Flask using the supported WSGI-to-ASGI adapter. Initialization begins
on worker boot, rather than waiting for the first visitor after 09:15.
"""
import threading
from asgiref.wsgi import WsgiToAsgi
from live_scanner_server import app as flask_app, initialize_live

app = WsgiToAsgi(flask_app)
threading.Thread(target=initialize_live, name="pre-market-warmup", daemon=True).start()
