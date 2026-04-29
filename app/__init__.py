import os
from pathlib import Path
from flask import Flask, render_template
from .extensions import db, login_manager, limiter
from .admin import admin_bp


def load_env_file():
    base_dir = Path(__file__).resolve().parent.parent
    env_path = base_dir / ".env"

    if not env_path.exists():
        return

    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


load_env_file()


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    app.config["MAIL_SENDER_EMAIL"] = os.getenv("MAIL_SENDER_EMAIL")
    app.config["MAIL_APP_PASSWORD"] = os.getenv("MAIL_APP_PASSWORD")
    app.config["MAIL_SMTP_HOST"] = os.getenv("MAIL_SMTP_HOST", "smtp.gmail.com")
    app.config["MAIL_SMTP_PORT"] = int(os.getenv("MAIL_SMTP_PORT", 465))
    app.config["RATELIMIT_STORAGE_URI"] = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Пожалуйста, войдите, чтобы продолжить"
    login_manager.login_message_category = "info"

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return render_template("429.html"), 429

    from .routes import main
    from .auth import auth

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(admin_bp)

    return app