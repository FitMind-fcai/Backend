"""
Shared HTML shell for standalone browser-rendered pages (e.g. the page shown
when a user clicks an email verification link). Unlike email_templates.py,
this targets real browsers, so it can use modern CSS/JS freely.
"""
from app.core.config import APP_URL

BRAND_COLOR = "#F97316"
BRAND_COLOR_DARK = "#EA580C"
LOGO_URL = f"{APP_URL}/static/logo.svg"

_SUCCESS_ICON = """
<svg viewBox="0 0 52 52" width="64" height="64">
  <circle cx="26" cy="26" r="25" fill="none" stroke="#22C55E" stroke-width="2"/>
  <path fill="none" stroke="#22C55E" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"
        d="M15 27 L22 34 L38 17"/>
</svg>
"""

_ERROR_ICON = """
<svg viewBox="0 0 52 52" width="64" height="64">
  <circle cx="26" cy="26" r="25" fill="none" stroke="#F59E0B" stroke-width="2"/>
  <path fill="none" stroke="#F59E0B" stroke-width="3" stroke-linecap="round"
        d="M26 15 L26 30"/>
  <circle cx="26" cy="37" r="1.8" fill="#F59E0B"/>
</svg>
"""


def render_status_page(
    status: str,
    heading: str,
    message: str,
    extra_html: str = "",
) -> str:
    """Render a standalone, responsive status page (success or error/expired).

    Args:
        status: "success" or "error" — controls the icon shown.
        heading: Main heading text.
        message: Supporting paragraph text.
        extra_html: Optional extra HTML injected below the message
                    (e.g. the resend-verification form).
    """
    icon = _SUCCESS_ICON if status == "success" else _ERROR_ICON

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FitMind</title>
<style>
  :root {{
    --brand: {BRAND_COLOR};
    --brand-dark: {BRAND_COLOR_DARK};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(160deg, #FFF7ED 0%, #F4F4F5 60%);
    font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    padding: 24px;
  }}
  .card {{
    width: 100%;
    max-width: 440px;
    background: #ffffff;
    border-radius: 20px;
    box-shadow: 0 8px 30px rgba(17, 24, 39, 0.08);
    overflow: hidden;
  }}
  .card-header {{
    background: linear-gradient(135deg, var(--brand) 0%, var(--brand-dark) 100%);
    padding: 32px 24px;
    text-align: center;
  }}
  .card-header img {{ display: block; margin: 0 auto 8px; }}
  .card-header .brand-name {{ color: #fff; font-weight: 700; font-size: 20px; letter-spacing: 0.5px; }}
  .card-body {{ padding: 36px 32px 40px; text-align: center; }}
  .icon-wrap {{ margin-bottom: 20px; }}
  h1 {{ color: #111827; font-size: 22px; margin: 0 0 12px; }}
  p.message {{ color: #4b5563; font-size: 15px; line-height: 1.6; margin: 0 0 8px; }}
  .form-row {{ margin-top: 24px; text-align: left; }}
  label {{ display: block; font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 6px; }}
  input[type="email"] {{
    width: 100%;
    padding: 12px 14px;
    font-size: 15px;
    border: 1px solid #d1d5db;
    border-radius: 10px;
    outline: none;
    transition: border-color 0.15s ease;
  }}
  input[type="email"]:focus {{ border-color: var(--brand); }}
  button.btn {{
    margin-top: 14px;
    width: 100%;
    background-color: var(--brand);
    color: #fff;
    font-weight: 600;
    font-size: 15px;
    border: none;
    border-radius: 10px;
    padding: 13px 20px;
    cursor: pointer;
    transition: background-color 0.15s ease;
  }}
  button.btn:hover {{ background-color: var(--brand-dark); }}
  button.btn:disabled {{ opacity: 0.6; cursor: not-allowed; }}
  .feedback {{ margin-top: 14px; font-size: 14px; min-height: 20px; }}
  .feedback.ok {{ color: #16A34A; }}
  .feedback.err {{ color: #DC2626; }}
  @media only screen and (max-width: 480px) {{
    .card-body {{ padding: 28px 20px 32px; }}
    .card-header {{ padding: 24px 16px; }}
    h1 {{ font-size: 20px; }}
  }}
</style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <img src="{LOGO_URL}" width="52" height="52" alt="FitMind">
      <div class="brand-name">FitMind</div>
    </div>
    <div class="card-body">
      <div class="icon-wrap">{icon}</div>
      <h1>{heading}</h1>
      <p class="message">{message}</p>
      {extra_html}
    </div>
  </div>
</body>
</html>"""


def render_resend_form(email: str = "") -> str:
    """Resend-verification form: posts to /v1/auth/resend-verification via fetch."""
    return f"""
    <div class="form-row">
      <form id="resend-form">
        <label for="email">Your email address</label>
        <input type="email" id="email" name="email" placeholder="you@example.com" value="{email}" required>
        <button type="submit" class="btn" id="resend-btn">Resend Verification Email</button>
        <div id="feedback" class="feedback"></div>
      </form>
    </div>
    <script>
      document.getElementById('resend-form').addEventListener('submit', async function (e) {{
        e.preventDefault();
        const btn = document.getElementById('resend-btn');
        const feedback = document.getElementById('feedback');
        const email = document.getElementById('email').value.trim();

        btn.disabled = true;
        btn.textContent = 'Sending...';
        feedback.className = 'feedback';
        feedback.textContent = '';

        try {{
          const res = await fetch('/v1/auth/resend-verification', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ email }})
          }});
          const data = await res.json().catch(() => ({{}}));

          if (res.ok) {{
            feedback.className = 'feedback ok';
            feedback.textContent = 'A new verification link has been sent — check your inbox!';
            btn.textContent = 'Email Sent';
          }} else {{
            feedback.className = 'feedback err';
            feedback.textContent = data.detail || 'Could not resend verification email. Please try again.';
            btn.disabled = false;
            btn.textContent = 'Resend Verification Email';
          }}
        }} catch (err) {{
          feedback.className = 'feedback err';
          feedback.textContent = 'Network error — please try again.';
          btn.disabled = false;
          btn.textContent = 'Resend Verification Email';
        }}
      }});
    </script>
    """
