import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discord_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    tier: Mapped[str] = mapped_column(String(20), default="free", nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    admin_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # MFA fields
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Access review
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subscriptions = relationship("Subscription", back_populates="user", lazy="noload")
    watchlist_items = relationship("Watchlist", back_populates="user", lazy="noload")
    discord_connection = relationship(
        "DiscordConnection",
        back_populates="user",
        uselist=False,
        lazy="noload",
    )
    api_partner_keys = relationship(
        "ApiPartnerKey",
        back_populates="user",
        foreign_keys="ApiPartnerKey.user_id",
        lazy="noload",
    )
    api_partner_entitlement = relationship(
        "ApiPartnerEntitlement",
        back_populates="user",
        uselist=False,
        lazy="noload",
    )
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", lazy="noload")
    mfa_backup_codes = relationship("MfaBackupCode", back_populates="user", lazy="noload")
    webhooks = relationship("ApiPartnerWebhook", back_populates="user", lazy="noload")
