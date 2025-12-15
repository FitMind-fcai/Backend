# Environment Variables Setup Guide

## 🔐 Security Notice
**NEVER commit your `.env` file to Git!** It contains sensitive credentials like API keys, database passwords, and secret keys.

---

## 📋 Quick Setup for Team Members

### Step 1: Copy the Example File
```bash
cp .env.example .env
```
Or on Windows:
```cmd
copy .env.example .env
```

### Step 2: Get Your API Keys

#### **GROQ API Key** (Required for AI Features)
1. Go to [Groq Console](https://console.groq.com/keys)
2. Sign up or log in
3. Create a new API key
4. Copy the key (starts with `gsk_...`)
5. Paste it in your `.env` file:
   ```
   GROQ_API_KEY=gsk_your_actual_key_here
   ```

#### **Email SMTP Credentials** (Required for Email Verification)
If using Gmail:
1. Go to [Google App Passwords](https://myaccount.google.com/apppasswords)
2. Create an app password for "Mail"
3. Update your `.env`:
   ```
   SMTP_USERNAME=your_email@gmail.com
   SMTP_PASSWORD=your_16_char_app_password
   ```

### Step 3: Verify Your Configuration
Open your `.env` file and make sure it looks like this:
```bash
# ========== AI Services ==========
GROQ_API_KEY=gsk_your_actual_key_here

# ========== Database ==========
DATABASE_URL=postgresql+psycopg://postgres:postgres123@db:5432/fastapi_db

# ========== Redis Cache ==========
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_URL=redis://redis:6379/0

# ========== Email (SMTP) ==========
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password_here
SMTP_FROM_EMAIL=your_email@gmail.com

# ========== JWT Authentication ==========
SECRET_KEY=your_super_secret_key_change_this_in_production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

### Step 4: Start the Application
```bash
docker-compose up --build
```

---

## 🚨 Common Issues & Solutions

### Issue: "GROQ_API_KEY not found" Error
**Problem:** The `.env` file is missing or doesn't have the GROQ API key.

**Solution:**
1. Make sure you created `.env` from `.env.example`
2. Verify the GROQ API key is added: `GROQ_API_KEY=gsk_...`
3. Restart Docker: `docker-compose down && docker-compose up --build`

### Issue: Email Verification Not Working
**Problem:** SMTP credentials are incorrect or missing.

**Solution:**
1. For Gmail, use an [App Password](https://myaccount.google.com/apppasswords), not your regular password
2. Make sure 2-Step Verification is enabled on your Google account
3. Check `SMTP_USERNAME` and `SMTP_PASSWORD` in `.env`

### Issue: Database Connection Error
**Problem:** Database container not ready or credentials mismatch.

**Solution:**
1. Check if PostgreSQL is running: `docker-compose ps`
2. Wait for health check to pass (10-20 seconds)
3. Verify `DATABASE_URL` matches `docker-compose.yml` credentials

### Issue: Changes to `.env` Not Taking Effect
**Problem:** Docker containers need to be rebuilt to pick up new environment variables.

**Solution:**
```bash
docker-compose down
docker-compose up --build
```

---

## 🔧 Environment Variables Reference

### Required Variables
| Variable        | Description                      | Example                                       |
| --------------- | -------------------------------- | --------------------------------------------- |
| `GROQ_API_KEY`  | API key for Groq LLM (AI Coach)  | `gsk_abc123...`                               |
| `DATABASE_URL`  | PostgreSQL connection string     | `postgresql+psycopg://user:pass@host:port/db` |
| `SMTP_USERNAME` | Email address for sending emails | `your_email@gmail.com`                        |
| `SMTP_PASSWORD` | Email app password               | `abcd efgh ijkl mnop`                         |
| `SECRET_KEY`    | JWT token secret key             | Any random 32+ character string               |

### Optional Variables
| Variable                      | Description           | Default           |
| ----------------------------- | --------------------- | ----------------- |
| `REDIS_HOST`                  | Redis server hostname | `redis`           |
| `REDIS_PORT`                  | Redis server port     | `6379`            |
| `SMTP_SERVER`                 | SMTP server address   | `smtp.gmail.com`  |
| `SMTP_PORT`                   | SMTP server port      | `587`             |
| `ALGORITHM`                   | JWT algorithm         | `HS256`           |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token expiry      | `1440` (24 hours) |

---

## 🔒 Security Best Practices

### ✅ DO:
- Keep `.env` file in `.gitignore` (already configured)
- Use `.env.example` to document required variables (no real values!)
- Generate strong random values for `SECRET_KEY`:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- Use environment-specific `.env` files for different environments
- Rotate API keys and secrets regularly

### ❌ DON'T:
- Commit `.env` to Git
- Share your `.env` file in chat/email
- Use default passwords in production
- Hardcode secrets in source code
- Reuse passwords across services

---

## 🐳 Docker Environment Variable Loading

The `docker-compose.yml` is configured to automatically load variables from `.env`:

```yaml
web:
  environment:
    DATABASE_URL: postgresql+psycopg://postgres:postgres123@db:5432/fastapi_db
    REDIS_HOST: redis
    REDIS_PORT: 6379
    # Add more variables here or use env_file
```

To use `.env` file directly, you can also add:
```yaml
web:
  env_file:
    - .env
```

---

## 📞 Need Help?

If you're still having issues:
1. Check the main `README.md` for general setup instructions
2. Review `DOCKER_GUIDE.md` for Docker-specific issues
3. Ensure your Docker Desktop is running
4. Verify you have internet connection (for pulling Docker images)
5. Ask the team lead for help with credentials

---

## 🔄 Quick Reference Commands

```bash
# Create .env from example
cp .env.example .env

# Start all services
docker-compose up

# Rebuild and start (use after .env changes)
docker-compose up --build

# Stop all services
docker-compose down

# View logs
docker-compose logs web

# View environment variables inside container
docker-compose exec web env | grep GROQ
```
