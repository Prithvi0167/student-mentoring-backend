from flask import Flask
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_cors import CORS

from app.models import db
from app.extensions import socketio

migrate = Migrate()
jwt = JWTManager()


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///mentoring.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = "change-this-to-a-real-secret"  # move to env var before deploying

    # Allow the React dev server (Vite, default port 5173) to call this API.
    # Lock allowed origins down to your real frontend URL before deploying.
    CORS(app, origins=["http://localhost:5173"], supports_credentials=True)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    socketio.init_app(app)

    with app.app_context():
        db.create_all()

        from app.routes.auth import auth_bp
        from app.routes.student import student_bp
        from app.routes.mentor import mentor_bp
        from app.routes.admin import admin_bp
        from app.routes.meeting import meeting_bp
        from app.routes.chat import chat_bp
        from app import sockets  # noqa: F401 — registers the socket event handlers

        app.register_blueprint(auth_bp)
        app.register_blueprint(student_bp)
        app.register_blueprint(mentor_bp)
        app.register_blueprint(admin_bp)
        app.register_blueprint(meeting_bp)
        app.register_blueprint(chat_bp)

    return app