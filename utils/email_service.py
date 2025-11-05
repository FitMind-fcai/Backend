import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

# Email configuration - TODO: Move to environment variables
SMTP_SERVER = "smtp.gmail.com"  # Change to your SMTP server
SMTP_PORT = 587
SENDER_EMAIL = "fitmind.dev.fcai@gmail.com"  # Change this
SENDER_PASSWORD = "reiislglpgbmoafr"  # Use app password for Gmail
APP_URL = "http://localhost:8000"  # Change in production

def send_verification_email(recipient_email: str, verification_token: str) -> bool:
    """
    Send verification email to user.
    
    Args:
        recipient_email: User's email address
        verification_token: Unique verification token
        
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Create verification link
        verification_link = f"{APP_URL}/auth/verify-email?token={verification_token}"
        
        print(f"📧 Attempting to send email to {recipient_email}")
        print(f"🔗 Verification link: {verification_link}")
        
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = "Verify Your Email Address"
        message["From"] = SENDER_EMAIL
        message["To"] = recipient_email
        
        # HTML email body
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 30px; border-radius: 10px;">
                    <h2 style="color: #333;">Welcome! Please Verify Your Email</h2>
                    <p style="color: #666; font-size: 16px;">
                        Thank you for signing up! To complete your registration, please verify your email address by clicking the button below:
                    </p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{verification_link}" 
                           style="background-color: #CC6A14; color: white; padding: 15px 30px; 
                                  text-decoration: none; border-radius: 5px; font-size: 16px; display: inline-block;">
                            Verify Email Address
                        </a>
                    </div>
                    <p style="color: #999; font-size: 14px;">
                        Or copy and paste this link in your browser:<br>
                        <a href="{verification_link}" style="color: #4CAF50;">{verification_link}</a>
                    </p>
                    <p style="color: #999; font-size: 12px; margin-top: 30px;">
                        This link will expire in 24 hours. If you didn't create an account, please ignore this email.
                    </p>
                </div>
            </body>
        </html>
        """
        
        # Attach HTML content
        part = MIMEText(html, "html")
        message.attach(part)
        
        # Send email
        print(f"📡 Connecting to SMTP server {SMTP_SERVER}:{SMTP_PORT}...")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            print("🔐 Starting TLS...")
            server.starttls()
            print(f"🔑 Logging in as {SENDER_EMAIL}...")
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            print("📤 Sending email...")
            server.sendmail(SENDER_EMAIL, recipient_email, message.as_string())
        
        print(f"✅ Verification email sent successfully to {recipient_email}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print("💡 Check your email and password. For Gmail, use an App Password!")
        return False
    except smtplib.SMTPException as e:
        return False
    except Exception as e:
        print(f"Failed to send email: {type(e).__name__}: {str(e)}")
        return False


def send_resend_verification_email(recipient_email: str, verification_token: str) -> bool:
    """
    Resend verification email.
    """
    return send_verification_email(recipient_email, verification_token)