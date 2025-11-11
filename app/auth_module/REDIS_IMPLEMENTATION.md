# Redis Implementation Guide

## 🎯 Overview

This authentication module now uses **Redis** for storing temporary data (OTPs and verification tokens) instead of the database. This is a **best practice** for several reasons:

### Why Redis for OTP and Verification Tokens?

✅ **Automatic Expiration** - Redis TTL handles cleanup automatically
✅ **Better Performance** - In-memory storage is much faster
✅ **Reduced Database Load** - No need for cleanup queries
✅ **Scalability** - Redis can be scaled independently
✅ **Atomic Operations** - Built-in counter for attempt tracking
✅ **No Database Migrations** - No need to add/remove columns

## 📊 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Database (PostgreSQL)                 │
├─────────────────────────────────────────────────────────┤
│  users table:                                           │
│  - id, name, email, age, password                       │
│  - is_verified (boolean) ← KEPT IN DB for login checks │
│  - created_at, updated_at                               │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    Redis (In-Memory)                     │
├─────────────────────────────────────────────────────────┤
│  OTP Storage:                                           │
│  - otp:user@email.com → hashed_otp (TTL: 10 min)      │
│  - otp_attempts:user@email.com → count (TTL: 10 min)  │
│                                                          │
│  Verification Tokens:                                    │
│  - verify:token_string → email (TTL: 24 hours)         │
└─────────────────────────────────────────────────────────┘
```

## 🗂️ File Structure

```
auth_module/
├── core/
│   ├── config.py              # Redis configuration added
│   └── redis_client.py        # NEW: Redis client singleton
├── services/
│   ├── otp_service_redis.py   # NEW: Redis-based OTP service
│   ├── verification_service.py # NEW: Redis-based verification
│   ├── auth_service.py        # UPDATED: Uses Redis services
│   └── email_service.py       # UNCHANGED
├── models/
│   └── user.py                # UPDATED: Removed OTP/token fields
└── routes/
    └── auth.py                # UPDATED: Uses Redis services
```

## 🔑 Redis Keys Structure

### OTP Keys
```
Key Pattern: otp:{email}
Value: Hashed OTP
TTL: 10 minutes (600 seconds)
Example: otp:user@example.com → "$2b$12$..."

Key Pattern: otp_attempts:{email}
Value: Integer (number of failed attempts)
TTL: 10 minutes (600 seconds)
Example: otp_attempts:user@example.com → "3"
```

### Verification Token Keys
```
Key Pattern: verify:{token}
Value: Email address
TTL: 24 hours (86400 seconds)
Example: verify:abc123def456 → "user@example.com"
```

## 📋 Database Schema Changes

### Before (with Redis)
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    email VARCHAR UNIQUE NOT NULL,
    age INTEGER NOT NULL,
    password VARCHAR NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Removed Fields
- ❌ `verification_token` - Now in Redis
- ❌ `verification_token_expires` - TTL handled by Redis
- ❌ `reset_otp` - Now in Redis
- ❌ `reset_otp_expires` - TTL handled by Redis
- ❌ `reset_otp_attempts` - Now in Redis

### Kept Fields
- ✅ `is_verified` - **MUST stay in database** for login checks

## 🚀 Installation

### 1. Install Redis

**Windows:**
```powershell
# Using Chocolatey
choco install redis-64

# Or download from: https://github.com/microsoftarchive/redis/releases
```

**Linux:**
```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

**macOS:**
```bash
brew install redis
brew services start redis
```

**Docker:**
```bash
docker run -d -p 6379:6379 --name redis redis:alpine
```

### 2. Install Python Redis Client
```bash
pip install redis
```

### 3. Update requirements.txt
```txt
redis==5.0.1
```

## ⚙️ Configuration

### Update `core/config.py`
```python
# Redis Configuration
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None  # Set if Redis has password
REDIS_DECODE_RESPONSES = True

# Redis Key Prefixes
REDIS_OTP_PREFIX = "otp:"
REDIS_OTP_ATTEMPTS_PREFIX = "otp_attempts:"
REDIS_VERIFICATION_PREFIX = "verify:"
```

### Production Settings
```python
import os

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
```

## 🔄 Migration Steps

### 1. Backup Database
```bash
pg_dump your_database > backup.sql
```

### 2. Create Migration (Alembic)
```bash
alembic revision -m "Remove OTP and verification token fields"
```

```python
# In migration file
def upgrade():
    op.drop_column('users', 'verification_token')
    op.drop_column('users', 'verification_token_expires')
    op.drop_column('users', 'reset_otp')
    op.drop_column('users', 'reset_otp_expires')
    op.drop_column('users', 'reset_otp_attempts')

def downgrade():
    op.add_column('users', sa.Column('verification_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('verification_token_expires', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('reset_otp', sa.String(), nullable=True))
    op.add_column('users', sa.Column('reset_otp_expires', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('reset_otp_attempts', sa.Integer(), nullable=True))
```

### 3. Run Migration
```bash
alembic upgrade head
```

## 📝 API Usage Examples

### Signup Flow (with Redis)
```python
# 1. User signs up
POST /auth/signup
{
    "name": "John Doe",
    "email": "john@example.com",
    "age": 25,
    "password": "secret123"
}

# Behind the scenes:
# - User created in database with is_verified=False
# - Token generated and stored in Redis: verify:abc123 → john@example.com
# - Email sent with link: http://app.com/verify-email?token=abc123

# 2. User clicks link
GET /auth/verify-email?token=abc123

# Behind the scenes:
# - Redis: verify:abc123 → returns "john@example.com"
# - Database: UPDATE users SET is_verified=TRUE WHERE email='john@example.com'
# - Redis: DELETE verify:abc123
```

### Password Reset Flow (with Redis)
```python
# 1. Request OTP
POST /auth/forgot-password
{
    "email": "john@example.com"
}

# Behind the scenes:
# - OTP generated: "1234"
# - Redis: otp:john@example.com → hashed("1234") [TTL: 10min]
# - Redis: otp_attempts:john@example.com → 0 [TTL: 10min]
# - Email sent with OTP: 1234

# 2. Verify OTP
POST /auth/verify-reset-otp
{
    "email": "john@example.com",
    "otp": "1234"
}

# Behind the scenes:
# - Redis: GET otp:john@example.com → hashed_otp
# - Verify: bcrypt.checkpw("1234", hashed_otp)
# - If invalid: INCR otp_attempts:john@example.com

# 3. Reset Password
POST /auth/reset-password
{
    "email": "john@example.com",
    "otp": "1234",
    "new_password": "newSecret456"
}

# Behind the scenes:
# - Verify OTP again
# - Database: UPDATE users SET password=hashed("newSecret456")
# - Redis: DELETE otp:john@example.com
# - Redis: DELETE otp_attempts:john@example.com
```

## 🔍 Redis Commands (Debugging)

### View All Keys
```bash
redis-cli KEYS *
```

### View OTP for User
```bash
redis-cli GET "otp:user@example.com"
redis-cli GET "otp_attempts:user@example.com"
```

### View Verification Token
```bash
redis-cli GET "verify:abc123def456"
```

### Check TTL (Time to Live)
```bash
redis-cli TTL "otp:user@example.com"
# Returns: 542 (seconds remaining)
# Returns: -1 (key exists but no expiration)
# Returns: -2 (key doesn't exist)
```

### Clear All Test Data
```bash
redis-cli FLUSHDB
```

### Monitor Redis Activity
```bash
redis-cli MONITOR
```

## 🛡️ Security Features

### OTP Security
✅ **Hashed Storage** - OTPs are hashed with bcrypt before storing
✅ **Automatic Expiration** - 10 minutes TTL
✅ **Attempt Limiting** - Max 5 attempts before OTP is invalidated
✅ **Rate Limiting** - Can add IP-based rate limiting

### Verification Token Security
✅ **Random Generation** - URL-safe tokens (32 bytes)
✅ **Automatic Expiration** - 24 hours TTL
✅ **One-time Use** - Deleted after successful verification
✅ **No User Data in Token** - Token maps to email in Redis

## 📊 Performance Benefits

| Metric | Database Approach | Redis Approach |
|--------|------------------|----------------|
| **OTP Validation** | ~50ms | ~1ms |
| **Cleanup** | Manual query | Automatic (TTL) |
| **Scaling** | Database load increases | Redis scales independently |
| **Expiration Check** | Application logic | Built-in TTL |
| **Attempt Counter** | UPDATE query | Atomic INCR |

## 🐛 Troubleshooting

### Redis Connection Failed
```python
# Error: Could not connect to Redis
# Solution: Check if Redis is running
redis-cli ping
# Expected: PONG
```

### Keys Not Expiring
```python
# Check if TTL is set
redis-cli TTL "otp:user@example.com"

# Set TTL manually if needed
redis-cli EXPIRE "otp:user@example.com" 600
```

### Can't Find Key
```python
# Check key pattern
redis-cli KEYS "otp:*"
redis-cli KEYS "verify:*"

# Verify decode_responses is True in config
REDIS_DECODE_RESPONSES = True
```

## 🔄 Fallback Strategy

If Redis is unavailable, the application will:
1. Return `HTTP 503 Service Unavailable`
2. Log the error
3. Can be extended to use database as fallback

### Implementing Fallback (Optional)
```python
def create_password_reset_otp(email: str) -> str:
    redis_client = get_redis()
    
    if not redis_client:
        # Fallback to database
        return create_otp_in_database(email)
    
    # Use Redis
    return create_otp_in_redis(email)
```

## ✅ Testing Redis Implementation

### Test OTP Flow
```python
import redis

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Simulate OTP creation
r.setex("otp:test@example.com", 600, "hashed_otp_value")
r.setex("otp_attempts:test@example.com", 600, 0)

# Check
print(r.get("otp:test@example.com"))  # hashed_otp_value
print(r.ttl("otp:test@example.com"))  # ~600 seconds

# Increment attempts
r.incr("otp_attempts:test@example.com")
print(r.get("otp_attempts:test@example.com"))  # 1
```

### Test Verification Token
```python
# Create token
token = "abc123def456"
r.setex(f"verify:{token}", 86400, "test@example.com")

# Verify
email = r.get(f"verify:{token}")
print(email)  # test@example.com

# Delete after verification
r.delete(f"verify:{token}")
```

## 🎓 Summary

| Feature | Storage | Reason |
|---------|---------|--------|
| **User Data** | Database | Permanent data |
| **is_verified** | Database | Checked on every login |
| **Passwords** | Database | Permanent, hashed |
| **OTPs** | Redis | Temporary (10 min), auto-expire |
| **Verification Tokens** | Redis | Temporary (24 hrs), auto-expire |
| **OTP Attempts** | Redis | Temporary counter, auto-expire |

---

**This Redis implementation follows industry best practices and provides better performance, security, and scalability! 🚀**
