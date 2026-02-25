from app.models.user import User


ADMIN_ROLE_SUPER = "super_admin"
ADMIN_ROLE_OPS = "ops_admin"
ADMIN_ROLE_SUPPORT = "support_admin"
ADMIN_ROLE_BILLING = "billing_admin"

ADMIN_ROLES = {
    ADMIN_ROLE_SUPER,
    ADMIN_ROLE_OPS,
    ADMIN_ROLE_SUPPORT,
    ADMIN_ROLE_BILLING,
}

PERMISSION_ADMIN_READ = "admin_read"
PERMISSION_USER_TIER_WRITE = "user_tier_write"
PERMISSION_USER_ROLE_WRITE = "user_role_write"
PERMISSION_USER_STATUS_WRITE = "user_status_write"
PERMISSION_USER_PASSWORD_RESET_WRITE = "user_password_reset_write"
PERMISSION_BILLING_WRITE = "billing_write"
PERMISSION_PARTNER_API_WRITE = "partner_api_write"

ROLE_PERMISSIONS: dict[str, set[str]] = {
    ADMIN_ROLE_SUPER: {
        PERMISSION_ADMIN_READ,
        PERMISSION_USER_TIER_WRITE,
        PERMISSION_USER_ROLE_WRITE,
        PERMISSION_USER_STATUS_WRITE,
        PERMISSION_USER_PASSWORD_RESET_WRITE,
        PERMISSION_BILLING_WRITE,
        PERMISSION_PARTNER_API_WRITE,
    },
    ADMIN_ROLE_OPS: {
        PERMISSION_ADMIN_READ,
        PERMISSION_USER_TIER_WRITE,
        PERMISSION_USER_STATUS_WRITE,
        PERMISSION_USER_PASSWORD_RESET_WRITE,
    },
    ADMIN_ROLE_SUPPORT: {
        PERMISSION_ADMIN_READ,
        PERMISSION_USER_TIER_WRITE,
        PERMISSION_USER_STATUS_WRITE,
        PERMISSION_USER_PASSWORD_RESET_WRITE,
    },
    ADMIN_ROLE_BILLING: {
        PERMISSION_ADMIN_READ,
        PERMISSION_BILLING_WRITE,
        PERMISSION_PARTNER_API_WRITE,
    },
}


def normalize_admin_role(role: str | None) -> str | None:
    if role is None:
        return None
    normalized = role.strip().lower()
    if not normalized:
        return None
    return normalized if normalized in ADMIN_ROLES else None


def effective_admin_role(user: User) -> str | None:
    explicit_role = normalize_admin_role(user.admin_role)
    if explicit_role is not None:
        return explicit_role
    if user.is_admin:
        return ADMIN_ROLE_SUPER
    return None


def is_admin_user(user: User) -> bool:
    return effective_admin_role(user) is not None


def has_admin_permission(user: User, permission: str) -> bool:
    role = effective_admin_role(user)
    if role is None:
        return False
    return permission in ROLE_PERMISSIONS.get(role, set())
