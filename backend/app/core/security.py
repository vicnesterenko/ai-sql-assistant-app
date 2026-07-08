from fastapi import Header, HTTPException
from pydantic import BaseModel


class CurrentUser(BaseModel):
    email: str
    role: str


def get_current_user(
    x_user_email: str = Header(default='analyst@example.com', alias='X-User-Email'),
    x_user_role: str = Header(default='analyst', alias='X-User-Role'),
) -> CurrentUser:
    role = x_user_role.lower().strip()
    if role not in {'analyst', 'approver'}:
        raise HTTPException(status_code=403, detail='X-User-Role must be analyst or approver')
    return CurrentUser(email=x_user_email, role=role)


def require_approver(user: CurrentUser) -> None:
    if user.role != 'approver':
        raise HTTPException(status_code=403, detail='Approver role required')
