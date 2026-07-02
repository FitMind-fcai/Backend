"""
Auth-specific email service.
Handles sending verification emails, OTP emails, and other auth-related emails.
"""
from app.shared.services.email_service import EmailService
from app.shared.services.email_templates import render_email
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

        html = render_email(
            heading="Welcome to FitMind!",
            preheader="Verify your email to start your fitness journey.",
            body_html="""
                <p>Thanks for signing up! Please verify your email address to activate
                your account and start your fitness journey with your AI coach.</p>
            """,
            cta_text="Verify Email Address",
            cta_url=verification_link,
            footer_note="This link expires in 24 hours. If you didn't create a FitMind account, you can safely ignore this email.",
        )

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

        html = render_email(
            heading="Here's Your New Verification Link",
            preheader="Verify your email to finish setting up FitMind.",
            body_html="""
                <p>You requested a new verification email. Click the button below to
                verify your email address and activate your FitMind account.</p>
            """,
            cta_text="Verify Email Address",
            cta_url=verification_link,
            footer_note="This link expires in 24 hours.",
        )

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

        body_html = f"""
            <p>You requested to reset your password. Use the one-time code below to proceed:</p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin: 24px 0;">
              <tr>
                <td align="center">
                  <div style="background: linear-gradient(135deg, {'#F97316'} 0%, {'#EA580C'} 100%); color: #ffffff;
                              padding: 20px 28px; border-radius: 12px; font-size: 32px; font-weight: 700;
                              letter-spacing: 8px; display: inline-block;">
                    {otp}
                  </div>
                </td>
              </tr>
            </table>
            <p>This code expires in 10 minutes.</p>
        """

        html = render_email(
            heading="Password Reset Request",
            preheader=f"Your FitMind password reset code is {otp}.",
            body_html=body_html,
            footer_note="If you didn't request a password reset, you can safely ignore this email — your password will remain unchanged.",
        )

        return self.email_service.send_email(recipient_email, "Password Reset OTP", html)

