import os
import re
import smtplib
import random
from email.mime.text import MIMEText
from flask import current_app


def generate_verification_code(length=6):
    return "".join(random.choices("0123456789", k=length))


def validate_password(password: str):
    if len(password) < 8:
        return "Пароль должен быть не короче 8 символов"

    if not re.fullmatch(r"[A-Za-z0-9]+", password):
        return "Пароль должен содержать только латинские буквы и цифры"

    if not re.search(r"[A-Za-z]", password):
        return "Пароль должен содержать хотя бы одну букву"

    if not re.search(r"\d", password):
        return "Пароль должен содержать хотя бы одну цифру"

    return None


def send_email_message(to_email: str, subject: str, body: str):
    sender_email = current_app.config.get("MAIL_SENDER_EMAIL") or os.getenv("MAIL_SENDER_EMAIL")
    app_password = current_app.config.get("MAIL_APP_PASSWORD") or os.getenv("MAIL_APP_PASSWORD")
    smtp_host = current_app.config.get("MAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(current_app.config.get("MAIL_SMTP_PORT", 465))

    if not sender_email or not app_password:
        raise RuntimeError("MAIL_SENDER_EMAIL и MAIL_APP_PASSWORD не настроены")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    server = smtplib.SMTP_SSL(smtp_host, smtp_port)
    server.login(sender_email, app_password)
    server.send_message(msg)
    server.quit()