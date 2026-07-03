"""Shared FastAPI dependencies (CONTRACTS.md: other modules import from here).

    from api.deps import current_active_user
"""
from api.auth.users import current_active_user, current_superuser, fastapi_users
from api.db import get_session

__all__ = ["current_active_user", "current_superuser", "fastapi_users", "get_session"]
