"""Reusable email sending via Gmail SMTP."""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(subject, html_content, sender=None, receiver=None, password=None):
    """Send an HTML email via Gmail SMTP_SSL.

    Args:
        subject:      Email subject line.
        html_content: Full HTML body string.
        sender:       Gmail address. Defaults to EMAIL_SENDER env var.
        receiver:     Recipient address. Defaults to EMAIL_RECEIVER env var.
        password:     Gmail app password. Defaults to EMAIL_PASSWORD env var.
    """
    sender = sender or os.environ.get("EMAIL_SENDER")
    receiver = receiver or os.environ.get("EMAIL_RECEIVER")
    password = password or os.environ.get("EMAIL_PASSWORD")

    if not all([sender, receiver, password]):
        print("Email credentials missing. Set EMAIL_SENDER, EMAIL_RECEIVER, EMAIL_PASSWORD.")
        return

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["To"] = receiver
    msg["From"] = sender
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
        print(f"Email sent: {subject}")
    except Exception as e:
        print(f"Email failed to send: {e}")
