from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, flash, url_for, session
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

from .models import User, PendingRegistration, PasswordResetCode
from .extensions import db, limiter
from .utils import send_email_message, generate_verification_code, validate_password, validate_email

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Введите логин и пароль", "danger")
            return redirect(url_for("auth.login"))

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get("next")
            if next_page and next_page.startswith("/"):
                return redirect(next_page)
            return redirect(url_for("main.dashboard"))

        flash("Неверный логин или пароль", "danger")

    return render_template("login.html")


@auth.route("/register", methods=["GET", "POST"])
@limiter.limit("3 per 10 minutes", methods=["POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if not username or not email or not password or not password_confirm:
            flash("Логин, email и пароль обязательны", "danger")
            return redirect(url_for("auth.register"))

        if not validate_email(email):
            flash("Введите корректный email", "danger")
            return redirect(url_for("auth.register"))

        if password != password_confirm:
            flash("Пароли не совпадают", "danger")
            return redirect(url_for("auth.register"))

        password_error = validate_password(password)
        if password_error:
            flash(password_error, "danger")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(username=username).first():
            flash("Пользователь с таким именем уже существует", "warning")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(email=email).first():
            flash("Пользователь с таким email уже существует", "warning")
            return redirect(url_for("auth.register"))

        PendingRegistration.query.filter(
            (PendingRegistration.username == username) |
            (PendingRegistration.email == email)
        ).delete(synchronize_session=False)

        code = generate_verification_code()

        pending = PendingRegistration(
            username=username,
            password_hash=generate_password_hash(password),
            email=email,
            code=code,
            expires_at=datetime.utcnow() + timedelta(minutes=15),
        )

        db.session.add(pending)
        db.session.commit()

        try:
            send_email_message(
                email,
                "TrainGain | Подтверждение регистрации",
                f"Ваш код подтверждения: {code}\n\nКод действует 15 минут."
            )

            db.session.add(pending)
            db.session.commit()

        except Exception as e:
            flash(f"Ошибка отправки кода: {e}", "danger")
            return redirect(url_for("auth.register"))

        session["pending_registration_id"] = pending.id

        flash("Код подтверждения отправлен на вашу почту", "success")
        return redirect(url_for("auth.verify_registration"))

    return render_template("register.html")


@auth.route("/verify_registration", methods=["GET", "POST"])
@limiter.limit("5 per 5 minutes", methods=["POST"])
def verify_registration():
    pending_id = session.get("pending_registration_id")
    if not pending_id:
        flash("Сначала заполните форму регистрации", "warning")
        return redirect(url_for("auth.register"))

    pending = PendingRegistration.query.get(pending_id)
    if not pending:
        session.pop("pending_registration_id", None)
        flash("Заявка на регистрацию не найдена", "danger")
        return redirect(url_for("auth.register"))

    if pending.is_expired():
        db.session.delete(pending)
        db.session.commit()
        session.pop("pending_registration_id", None)
        flash("Срок действия кода истёк. Зарегистрируйтесь заново.", "danger")
        return redirect(url_for("auth.register"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()

        if not code:
            flash("Введите код подтверждения", "danger")
            return redirect(url_for("auth.verify_registration"))

        if code != pending.code:
            flash("Неверный код подтверждения", "danger")
            return redirect(url_for("auth.verify_registration"))

        if User.query.filter_by(username=pending.username).first():
            flash("Пользователь с таким именем уже существует", "warning")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(email=pending.email).first():
            flash("Пользователь с таким email уже существует", "warning")
            return redirect(url_for("auth.register"))

        user = User(
            username=pending.username,
            password=pending.password_hash,
            email=pending.email,
            email_verified_at=datetime.utcnow()
        )

        db.session.add(user)
        db.session.delete(pending)
        db.session.commit()

        session.pop("pending_registration_id", None)

        flash("Регистрация подтверждена! Теперь войдите.", "success")
        return redirect(url_for("auth.login"))

    return render_template("verify_registration.html", pending_email=pending.email)


@auth.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Вы вышли из системы", "info")
    return redirect(url_for("auth.login"))


@auth.route("/reset_password", methods=["GET", "POST"])
@limiter.limit("3 per 5 minutes", methods=["POST"])
def reset_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Введите email", "danger")
            return redirect(url_for("auth.reset_password"))

        if not validate_email(email):
            flash("Введите корректный email", "danger")
            return redirect(url_for("auth.reset_password"))

        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Пользователь с таким email не найден", "danger")
            return redirect(url_for("auth.reset_password"))

        PasswordResetCode.query.filter_by(user_id=user.id, is_used=False).delete(synchronize_session=False)

        code = generate_verification_code()
        reset_request = PasswordResetCode(
            user_id=user.id,
            email=email,
            code=code,
            expires_at=datetime.utcnow() + timedelta(minutes=15),
            is_used=False
        )

        try:
            send_email_message(
                email,
                "TrainGain | Восстановление пароля",
                f"Ваш код для восстановления пароля: {code}\n\nКод действует 15 минут."
            )

            db.session.add(reset_request)
            db.session.commit()

        except Exception as e:
            flash(f"Ошибка отправки кода: {e}", "danger")
            return redirect(url_for("auth.reset_password"))

        flash("Код для восстановления пароля отправлен на email", "success")
        return redirect(url_for("auth.reset_password_confirm", email=email))

    return render_template("reset_password.html")


@auth.route("/reset_password/confirm", methods=["GET", "POST"])
@limiter.limit("5 per 10 minutes", methods=["POST"])
def reset_password_confirm():
    email = request.args.get("email", "").strip().lower() or request.form.get("email", "").strip().lower()

    if not email:
        flash("Сначала укажите email", "warning")
        return redirect(url_for("auth.reset_password"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if not code or not password or not password_confirm:
            flash("Заполните все поля", "danger")
            return redirect(url_for("auth.reset_password_confirm", email=email))

        if password != password_confirm:
            flash("Пароли не совпадают", "danger")
            return redirect(url_for("auth.reset_password_confirm", email=email))

        password_error = validate_password(password)
        if password_error:
            flash(password_error, "danger")
            return redirect(url_for("auth.reset_password_confirm", email=email))

        reset_request = PasswordResetCode.query.filter_by(
            email=email,
            code=code,
            is_used=False
        ).order_by(PasswordResetCode.created_at.desc()).first()

        if not reset_request:
            flash("Неверный код", "danger")
            return redirect(url_for("auth.reset_password_confirm", email=email))

        if reset_request.is_expired():
            flash("Срок действия кода истёк", "danger")
            return redirect(url_for("auth.reset_password"))

        user = User.query.get(reset_request.user_id)
        if not user:
            flash("Пользователь не найден", "danger")
            return redirect(url_for("auth.reset_password"))

        user.password = generate_password_hash(password)
        reset_request.is_used = True
        db.session.commit()

        flash("Пароль успешно изменён. Теперь войдите.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password_confirm.html", email=email)