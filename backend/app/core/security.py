"""
    Спрощена автентифікація й перевірка ролей через HTTP-заголовки.
    For production:
        JWT access token;
        OAuth2;
        корпоративний SSO;
"""

from fastapi import Header, HTTPException
from pydantic import BaseModel, EmailStr

from app.models.types import UserRole


class CurrentUser(BaseModel):
    """Дані автентифікованого користувача та його роль."""

    email: EmailStr
    role: UserRole


def get_current_user(
    x_user_email: str = Header(
        default="analyst@example.com",
        alias="X-User-Email",
    ),
    x_user_role: str = Header(
        default=UserRole.ANALYST.value,
        alias="X-User-Role",
    ),
) -> CurrentUser:
    """Отримує користувача з HTTP-заголовків і перевіряє його роль."""

    role = x_user_role.lower().strip()

    try:
        role = UserRole(role)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="X-User-Role must be analyst or approver",
        )

    return CurrentUser(
        email=x_user_email,
        role=role,
    )


def require_approver(user: CurrentUser) -> None:
    """Перевіряє, чи має користувач роль approver."""

    if user.role != UserRole.APPROVER:
        raise HTTPException(
            status_code=403,
            detail="Approver role required",
        )
