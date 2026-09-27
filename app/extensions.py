"""
Shared extension instances that need to be importable from multiple places
(app factory, sockets.py) without causing circular imports.
"""

from flask_socketio import SocketIO

# cors_allowed_origins="*" is fine for local dev; lock this down to your
# actual frontend URL before deploying.
socketio = SocketIO(cors_allowed_origins="*")