from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    is_verified: bool

    class Config:
        from_attributes = True



class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginResponse(BaseModel):
    token: str
    user: UserResponse
    
    class Config:
        from_attributes = True

class EmailVerificationRequest(BaseModel):
    email: EmailStr

class VerifyEmailRequest(BaseModel):
    token: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=5, max_length=5)

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=5, max_length=5)
    new_password: str = Field(..., min_length=6)

class DeleteAccountRequest(BaseModel):
    password: str = Field(..., description="Current password, required to confirm account deletion")