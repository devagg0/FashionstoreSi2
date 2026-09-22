from typing import Literal
from urllib.parse import urlsplit

from pydantic import EmailStr, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: SecretStr = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = Field(default=60, gt=0)
    DIGITAL_CHECKOUT_TTL_MINUTES: int = Field(default=30, gt=0, le=1440)
    RESERVATION_GRACE_MINUTES: int = Field(default=60, gt=0, le=1440)
    RESERVATION_SLOT_MINUTES: int = Field(default=30, gt=0, le=120)
    APP_TIMEZONE: str = Field(default="America/La_Paz", min_length=1)
    BREVO_API_KEY: SecretStr = Field(min_length=1)
    BREVO_SENDER_EMAIL: EmailStr
    BREVO_SENDER_NAME: str = Field(min_length=1, max_length=100)
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: SecretStr | None = None
    SUPABASE_STORAGE_BUCKET: str | None = None
    GEMINI_API_KEY: SecretStr | None = Field(default=None, repr=False)
    STRIPE_SECRET_KEY: SecretStr = Field(repr=False)
    STRIPE_PUBLISHABLE_KEY: SecretStr = Field(repr=False)
    STRIPE_MODE: str
    STRIPE_CHECKOUT_RETURN_BASE_URL: str = "http://localhost:4201"
    STRIPE_CHECKOUT_MOBILE_RETURN_BASE_URL: str = "fashionstore://payment-return"
    QR_SIMULATION_RESULT: Literal["APROBADO", "RECHAZADO"] = "APROBADO"

    @field_validator("STRIPE_CHECKOUT_RETURN_BASE_URL")
    @classmethod
    def validate_checkout_return_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")
                or parsed.scheme not in {"https", "http"}
                or parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}):
            raise ValueError("Checkout requiere un origen HTTPS o HTTP local sin credenciales ni parametros")
        # Acceder a port valida tambien puertos malformados.
        parsed.port
        return value.rstrip("/")

    @field_validator("STRIPE_CHECKOUT_MOBILE_RETURN_BASE_URL")
    @classmethod
    def validate_mobile_checkout_return_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme != "fashionstore" or parsed.netloc != "payment-return"
                or parsed.path not in ("", "/") or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError("Checkout movil requiere fashionstore://payment-return")
        return "fashionstore://payment-return"

    @field_validator("STRIPE_MODE")
    @classmethod
    def validate_stripe_mode(cls, value: str) -> str:
        if value != "test":
            raise ValueError("Stripe solo admite modo test en este entorno")
        return value

    @field_validator("STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY")
    @classmethod
    def validate_stripe_test_key(cls, value: SecretStr, info) -> SecretStr:
        prefix = "sk_test_" if info.field_name == "STRIPE_SECRET_KEY" else "pk_test_"
        key = value.get_secret_value()
        if not key.startswith(prefix) or len(key) <= len(prefix):
            raise ValueError("Stripe requiere una clave TEST valida")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )


settings = Settings()
