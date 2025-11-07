# Auth Module - Clean Architecture Guide

## 📁 Project Structure

```
auth_module/
├── core/               # Core functionality (config, security, dependencies)
│   ├── config.py      # Configuration constants
│   ├── security.py    # Password hashing, JWT, OTP generation
│   └── dependencies.py # FastAPI dependency injection functions
├── middleware/        # Optional middleware for logging/tracking
│   └── user.py        # User activity tracking middleware
├── models/            # Database models
│   └── user.py        # User SQLAlchemy model
├── routes/            # API endpoints
│   └── auth.py        # Authentication routes (clean, uses services)
├── schemas/           # Pydantic schemas for validation
│   └── user.py        # Request/Response schemas
└── services/          # Business logic layer
    ├── auth_service.py    # User authentication logic
    ├── email_service.py   # Email sending functionality
    └── otp_service.py     # OTP generation and validation
```

## 🎯 Architecture Principles

### 1. **Separation of Concerns**
Each module has a single, well-defined responsibility:

- **Routes**: Handle HTTP requests/responses
- **Services**: Contain business logic
- **Core**: Provide utilities and configurations
- **Models**: Define database structure
- **Schemas**: Validate input/output data

### 2. **Dependency Injection**
Used for route protection and code reusability:

```python
# Instead of validating JWT in every endpoint...
@router.get("/protected")
def protected_route(current_user: User = Depends(get_current_user)):
    # current_user is automatically validated!
    return {"user": current_user.email}
```

### 3. **Service Layer Pattern**
Business logic is separated from HTTP handling:

```python
# ❌ BAD: Logic in routes
@router.post("/signup")
def signup(user_data, db):
    # Check user exists
    # Hash password
    # Create user
    # Send email
    # ... (100 lines of logic)

# ✅ GOOD: Logic in services
@router.post("/signup")
def signup(user_data, db):
    user = create_user(user_data, db)  # Service handles logic
    send_verification_email(user.email, user.token)  # Service handles email
    return user
```

## 📚 Module Documentation

### `core/config.py`
Contains all configuration constants in one place:
- JWT settings
- OTP configuration
- Email SMTP settings
- Password requirements

**Why?** Easy to change settings, move to environment variables later.

### `core/security.py`
Security utilities:
- `hash_password()` - Hash passwords with bcrypt
- `verify_password()` - Verify password against hash
- `create_access_token()` - Generate JWT token
- `verify_access_token()` - Validate JWT token
- `generate_otp()` - Create random OTP
- `hash_otp()` / `verify_otp()` - Secure OTP handling

**Why?** Centralized security functions, easy to test and maintain.

### `core/dependencies.py`
FastAPI dependency injection functions:
- `get_current_user()` - Validate JWT and return user
- `get_verified_user()` - Ensure email is verified
- `get_optional_user()` - Optional authentication

**Why?** Reusable route protection, clean endpoint code.

**Usage:**
```python
# Requires authentication
@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user)):
    return {"user": user.name}

# Requires authentication + verification
@router.get("/premium")
def premium(user: User = Depends(get_verified_user)):
    return {"premium_content": "..."}

# Optional authentication
@router.get("/public")
def public(user: User | None = Depends(get_optional_user)):
    if user:
        return {"message": f"Hello {user.name}"}
    return {"message": "Hello Guest"}
```

### `services/auth_service.py`
User authentication business logic:
- `create_user()` - Create new user account
- `authenticate_user()` - Login user and generate token
- `verify_user_email()` - Verify email with token
- `resend_verification()` - Resend verification email
- `reset_user_password()` - Reset user password
- `get_user_by_email()` - Find user by email

**Why?** Business logic separated from HTTP layer, easy to test.

### `services/otp_service.py`
OTP management:
- `create_password_reset_otp()` - Generate and store OTP
- `validate_otp()` - Verify OTP with expiration/attempts checks
- `clear_otp()` - Clear OTP after use
- `is_otp_valid()` - Check if OTP is still valid

**Why?** Dedicated OTP logic, tracks attempts, handles expiration.

### `services/email_service.py`
Email sending functionality:
- `send_verification_email()` - Send email verification link
- `send_resend_verification_email()` - Resend verification
- `send_password_reset_otp()` - Send OTP email

**Why?** Centralized email handling, easy to switch providers.

### `routes/auth.py`
Clean API endpoints:
- `POST /auth/signup` - Register new user
- `POST /auth/login` - Authenticate and get token
- `GET /auth/verify-email?token=...` - Verify email
- `POST /auth/resend-verification` - Resend verification
- `GET /auth/me` - Get current user
- `POST /auth/forgot-password` - Request password reset
- `POST /auth/verify-reset-otp` - Verify OTP
- `POST /auth/reset-password` - Reset password

**Why?** Thin routes, delegate to services, easy to read.

### `middleware/user.py`
Optional middleware:
- `UserActivityMiddleware` - Log user activity
- `RateLimitMiddleware` - Rate limiting (template)

**Why?** Cross-cutting concerns, runs on every request.

## 🔐 Security Features

✅ **Password Hashing** - bcrypt with salt
✅ **JWT Tokens** - Stateless authentication
✅ **OTP Hashing** - OTPs hashed before storage
✅ **Email Verification** - Required before login
✅ **OTP Expiration** - 10-minute validity
✅ **Attempt Tracking** - Prevent brute force
✅ **Token Expiration** - JWT expires after 24 hours

## 🚀 Usage Examples

### Protected Route Example
```python
from fastapi import APIRouter, Depends
from auth_module.core.dependencies import get_current_user, get_verified_user
from auth_module.models.user import User

router = APIRouter()

@router.get("/profile")
def get_profile(user: User = Depends(get_current_user)):
    """Requires valid JWT token"""
    return {"name": user.name, "email": user.email}

@router.get("/dashboard")
def get_dashboard(user: User = Depends(get_verified_user)):
    """Requires JWT + email verification"""
    return {"message": f"Welcome {user.name}"}
```

### Service Usage Example
```python
from auth_module.services.auth_service import create_user, authenticate_user
from auth_module.schemas.user import UserCreate, UserLogin

# Create user
user_data = UserCreate(name="John", email="john@example.com", age=25, password="secret123")
new_user = create_user(user_data, db)

# Authenticate user
credentials = UserLogin(email="john@example.com", password="secret123")
user, token = authenticate_user(credentials, db)
```

## 🔄 Authentication Flow

### Signup & Email Verification
```
1. User → POST /auth/signup
   ↓
2. create_user() → Hash password, generate token
   ↓
3. send_verification_email() → Send email with link
   ↓
4. User clicks link → GET /auth/verify-email?token=...
   ↓
5. verify_user_email() → Mark as verified
   ↓
6. User can now login
```

### Login
```
1. User → POST /auth/login
   ↓
2. authenticate_user() → Verify password, check verified status
   ↓
3. create_access_token() → Generate JWT
   ↓
4. Return token to user
   ↓
5. User sends token in x-auth-token header for protected routes
```

### Password Reset
```
1. User → POST /auth/forgot-password
   ↓
2. create_password_reset_otp() → Generate & hash OTP
   ↓
3. send_password_reset_otp() → Email OTP to user
   ↓
4. User → POST /auth/verify-reset-otp (email + OTP)
   ↓
5. validate_otp() → Check OTP validity
   ↓
6. User → POST /auth/reset-password (email + OTP + new password)
   ↓
7. reset_user_password() → Update password, clear OTP
```

## 📝 Best Practices

### 1. **Always Use Services**
```python
# ❌ DON'T: Business logic in routes
@router.post("/signup")
def signup(user_data, db):
    existing = db.query(User).filter(...).first()
    if existing:
        raise HTTPException(...)
    # ... more logic

# ✅ DO: Delegate to services
@router.post("/signup")
def signup(user_data, db):
    user = create_user(user_data, db)  # Service handles everything
    return user
```

### 2. **Use Dependency Injection**
```python
# ❌ DON'T: Manually validate tokens
@router.get("/profile")
def profile(x_auth_token: str, db: Session):
    token = jwt.decode(x_auth_token, SECRET_KEY)
    user = db.query(User).filter(...).first()
    # ...

# ✅ DO: Use dependencies
@router.get("/profile")
def profile(user: User = Depends(get_current_user)):
    return user  # Already validated!
```

### 3. **Keep Routes Thin**
Routes should be 5-10 lines max, just orchestrating services.

### 4. **Centralize Configuration**
All constants in `config.py`, easy to move to environment variables.

### 5. **Test Services, Not Routes**
Services contain logic → test them extensively.
Routes are thin → basic integration tests.

## 🔧 Migration from Old Code

If you have existing code in `routes/auth.py`, here's how to migrate:

1. **Move configuration** → `core/config.py`
2. **Move password/JWT functions** → `core/security.py`
3. **Extract business logic** → `services/auth_service.py`, `services/otp_service.py`
4. **Simplify routes** → Use services
5. **Add dependencies** → Replace manual token validation with `Depends(get_current_user)`

## 🎓 Key Takeaways

| Concept | Purpose | Example |
|---------|---------|---------|
| **Services** | Business logic | `create_user()`, `validate_otp()` |
| **Dependencies** | Route protection | `Depends(get_current_user)` |
| **Security** | Auth utilities | `hash_password()`, `create_access_token()` |
| **Config** | Centralized settings | `JWT_SECRET_KEY`, `OTP_LENGTH` |
| **Thin Routes** | HTTP handling only | Delegate to services |

---

**This structure is production-ready and follows FastAPI best practices! 🚀**
