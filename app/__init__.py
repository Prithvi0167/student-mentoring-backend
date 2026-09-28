from flask import Flask
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_cors import CORS
import os

from app.models import db
from app.extensions import socketio

migrate = Migrate()
jwt = JWTManager()


def create_app():
    app = Flask(__name__)

    # Database: Render gives postgres://, SQLAlchemy needs postgresql://
    db_url = os.environ.get("DATABASE_URL", "sqlite:///mentoring.db")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-only-secret")

    # Comma-separated list, e.g. "https://my-app.netlify.app,http://localhost:5173"
    origins_env = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173")
    origins = "*" if origins_env == "*" else [o.strip() for o in origins_env.split(",")]

    CORS(app, origins=origins)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    socketio.init_app(app, cors_allowed_origins=origins)


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