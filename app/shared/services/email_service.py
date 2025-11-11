"""
Shared email service for the entire application.
Provides base email sending functionality that can be used by any module.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import (
    SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD
)


class EmailService:
    """
    Base email service for sending emails.
    Provides generic email sending functionality that can be extended by module-specific services.
    """

    def __init__(self):
        """
        Initialize EmailService with SMTP configuration from config.
        """
        self.smtp_server = SMTP_SERVER
        self.smtp_port = SMTP_PORT
        self.sender_email = SENDER_EMAIL
        self.sender_password = SENDER_PASSWORD

    def send_email(self, recipient_email: str, subject: str, html_content: str) -> bool:
        """
        Send an email with custom subject and HTML content.

        This is the base method that all module-specific email services can use.

        Args:
            recipient_email: Recipient's email address
            subject: Email subject
            html_content: HTML content of the email

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            print(f"📧 Attempting to send email to {recipient_email}")

            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = recipient_email

            # Attach HTML content
            part = MIMEText(html_content, "html")
            message.attach(part)

            # Send email
            print(f"📡 Connecting to SMTP server {self.smtp_server}:{self.smtp_port}...")
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                print("🔐 Starting TLS...")
                server.starttls()
                print(f"🔑 Logging in as {self.sender_email}...")
                server.login(self.sender_email, self.sender_password)
                print("📤 Sending email...")
                server.sendmail(self.sender_email, recipient_email, message.as_string())

            print(f"✅ Email sent successfully to {recipient_email}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ SMTP Authentication Error: {e}")
            print("💡 Check your email and password. For Gmail, use an App Password!")
            return False
        except smtplib.SMTPException as e:
            print(f"❌ SMTP Error: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error sending email: {e}")
            return False

