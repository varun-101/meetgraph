"""Auth routes (contract: module-level ``router``).

Exposes:
- POST /auth/jwt/login (form: username, password) -> bearer token
- POST /auth/jwt/logout
- POST /auth/register
- /users/* management routes (me, by id)
"""
from fastapi import APIRouter

from api.auth.schemas import UserCreate, UserRead, UserUpdate
from api.auth.users import auth_backend, fastapi_users

router = APIRouter()

router.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"]
)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"]
)
