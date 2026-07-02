"""
Shared, responsive HTML email shell used by every transactional email
(verification, resend, OTP, etc.). Table-based layout with inline-friendly
CSS so it renders consistently across Gmail, Apple Mail, Outlook.com/mobile,
and other major clients, and adapts to narrow (phone) viewports via the
included media query.
"""
from app.core.config import APP_URL

BRAND_COLOR = "#F97316"
BRAND_COLOR_DARK = "#EA580C"
LOGO_URL = f"{APP_URL}/static/logo.svg"


def render_email(
    heading: str,
    preheader: str,
    body_html: str,
    cta_text: str | None = None,
    cta_url: str | None = None,
    footer_note: str = "",
) -> str:
    """Wrap the given body content in the shared FitMind email shell.

    Args:
        heading: Large heading shown at the top of the email body.
        preheader: Hidden preview text shown next to the subject in inbox lists.
        body_html: Pre-rendered HTML for the main message (paragraphs, etc.).
        cta_text: Optional call-to-action button label.
        cta_url: Optional call-to-action button target URL.
        footer_note: Small print shown at the bottom of the email.
    """
    cta_block = ""
    if cta_text and cta_url:
        cta_block = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin: 28px 0 8px;">
          <tr>
            <td align="center">
              <a href="{cta_url}" class="btn" target="_blank" rel="noopener">{cta_text}</a>
            </td>
          </tr>
        </table>
        <p class="link-fallback muted">
          Or copy and paste this link into your browser:<br>
          <a href="{cta_url}" class="link-fallback">{cta_url}</a>
        </p>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light">
<title>FitMind</title>
<style>
  body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
  table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
  img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
  body {{ margin: 0; padding: 0; width: 100% !important; background-color: #f4f4f5;
         font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }}
  .email-wrapper {{ width: 100%; background-color: #f4f4f5; padding: 32px 12px; }}
  .email-card {{ max-width: 560px; margin: 0 auto; background-color: #ffffff; border-radius: 16px;
                overflow: hidden; box-shadow: 0 2px 12px rgba(17, 24, 39, 0.06); }}
  .email-header {{ background: linear-gradient(135deg, {BRAND_COLOR} 0%, {BRAND_COLOR_DARK} 100%);
                   padding: 32px 24px; text-align: center; }}
  .email-body {{ padding: 36px 32px; }}
  .email-footer {{ padding: 20px 32px 32px; text-align: center; }}
  h1 {{ color: #111827; font-size: 22px; line-height: 1.3; margin: 0 0 16px; }}
  p {{ color: #4b5563; font-size: 15px; line-height: 1.6; margin: 0 0 16px; }}
  .btn {{ display: inline-block; background-color: {BRAND_COLOR}; color: #ffffff !important;
         text-decoration: none; font-weight: 600; font-size: 16px; padding: 14px 36px; border-radius: 10px; }}
  .muted {{ color: #9ca3af; font-size: 12px; line-height: 1.6; }}
  .link-fallback {{ word-break: break-all; color: {BRAND_COLOR}; }}
  .brand-name {{ color: #ffffff; font-weight: 700; font-size: 20px; letter-spacing: 0.5px; margin-top: 8px; }}
  @media only screen and (max-width: 600px) {{
    .email-body {{ padding: 28px 20px !important; }}
    .email-header {{ padding: 24px 16px !important; }}
    h1 {{ font-size: 20px !important; }}
    .btn {{ display: block !important; width: 100% !important; box-sizing: border-box; }}
  }}
</style>
</head>
<body>
  <div style="display:none; max-height:0; overflow:hidden; opacity:0; mso-hide:all;">{preheader}</div>
  <div class="email-wrapper">
    <table role="presentation" class="email-card" width="100%" cellpadding="0" cellspacing="0" align="center">
      <tr>
        <td class="email-header">
          <img src="{LOGO_URL}" width="56" height="56" alt="FitMind" style="display:block; margin: 0 auto;">
          <div class="brand-name">FitMind</div>
        </td>
      </tr>
      <tr>
        <td class="email-body">
          <h1>{heading}</h1>
          {body_html}
          {cta_block}
        </td>
      </tr>
      <tr>
        <td class="email-footer">
          <p class="muted" style="margin:0;">{footer_note}</p>
        </td>
      </tr>
    </table>
  </div>
</body>
</html>"""
