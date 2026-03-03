"""
Auth-specific email service.
Handles sending verification emails, OTP emails, and other auth-related emails.
"""
from app.shared.services.email_service import EmailService
from app.core.config import APP_URL


class AuthEmailService:
    """
    Email service for authentication module.
    Uses the shared EmailService for sending and provides auth-specific email templates.
    """

    def __init__(self, email_service: EmailService):
        """
        Initialize AuthEmailService with injected EmailService.

        Args:
            email_service: Shared email service for sending emails
        """
        self.email_service = email_service
        self.app_url = APP_URL

    def send_verification_email(self, recipient_email: str, verification_token: str) -> bool:
        """
        Send verification email to user.

        Args:
            recipient_email: User's email address
            verification_token: Unique verification token

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        verification_link = f"{self.app_url}/v1/auth/verify-email?token={verification_token}"
        print(f"🔗 Verification link: {verification_link}")

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

        return self.email_service.send_email(recipient_email, "Verify Your Email Address", html)

    def send_resend_verification_email(self, recipient_email: str, verification_token: str) -> bool:
        """
        Send resend verification email to user.

        Args:
            recipient_email: User's email address
            verification_token: Unique verification token

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        verification_link = f"{self.app_url}/v1/auth/verify-email?token={verification_token}"
        print(f"🔗 Resend verification link: {verification_link}")

        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 30px; border-radius: 10px;">
                    <h2 style="color: #333;">Email Verification Reminder</h2>
                    <p style="color: #666; font-size: 16px;">
                        You requested a new verification email. Please verify your email address by clicking the button below:
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
                        This link will expire in 24 hours.
                    </p>
                </div>
            </body>
        </html>
        """

        return self.email_service.send_email(recipient_email, "Verify Your Email Address - Resend", html)

    def send_password_reset_otp(self, recipient_email: str, otp: str) -> bool:
        """
        Send OTP for password reset.

        Args:
            recipient_email: User's email address
            otp: One-time password

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        print(f"🔐 Password reset OTP: {otp}")

        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 30px; border-radius: 10px;">
                    <h2 style="color: #333;">Password Reset Request</h2>
                    <p style="color: #666; font-size: 16px;">
                        You requested to reset your password. Use the OTP below to proceed:
                    </p>
                    <div style="text-align: center; margin: 30px 0;">
                        <div style="background-color: #CC6A14; color: white; padding: 20px; 
                                    border-radius: 5px; font-size: 32px; font-weight: bold; letter-spacing: 5px;">
                            {otp}
                        </div>
                    </div>
                    <p style="color: #666; font-size: 14px;">
                        This OTP will expire in 10 minutes.
                    </p>
                    <p style="color: #999; font-size: 12px; margin-top: 30px;">
                        If you didn't request a password reset, please ignore this email and your password will remain unchanged.
                    </p>
                </div>
            </body>
        </html>
        """

        return self.email_service.send_email(recipient_email, "Password Reset OTP", html)

