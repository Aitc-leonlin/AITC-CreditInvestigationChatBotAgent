from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    login: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    rememberMe: bool = False

    @field_validator("login")
    @classmethod
    def normalize_login(cls, value: str) -> str:
        return value.strip().lower()


class RefreshTokenCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    refreshToken: str = Field(min_length=20)


class LogoutCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    refreshToken: str | None = None


class ForgotPasswordCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ResetPasswordCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    token: str = Field(min_length=20)
    newPassword: str = Field(min_length=8, max_length=128)


class EmailVerificationCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    token: str = Field(min_length=20)


class AuthUserResponse(BaseModel):
    id: str
    username: str
    email: str
    displayName: str
    status: str
    emailVerifiedAt: str | None
    mustChangePassword: bool


class AuthTokenResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str
    expiresIn: int
    refreshExpiresAt: str
    sessionId: str
    user: AuthUserResponse


class ForgotPasswordResponse(BaseModel):
    accepted: bool
    resetToken: str | None = None


class EmailVerificationResponse(BaseModel):
    accepted: bool
    verificationToken: str | None = None


class SessionResponse(BaseModel):
    id: str
    userId: str
    rememberMe: bool
    ipAddress: str
    userAgent: str
    startedAt: str
    lastSeenAt: str
    expiresAt: str
    revokedAt: str | None
