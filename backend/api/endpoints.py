"""Compose the versioned API router.

Auth is attached per-router: the ``auth`` router is public, while every other
router requires a valid bearer token via ``get_current_user``.
"""

from fastapi import APIRouter, Depends

from api.deps import get_current_user
from api.v1 import auth, users

api_router = APIRouter()

# Public.
api_router.include_router(auth.router)

# Protected.
api_router.include_router(users.router, dependencies=[Depends(get_current_user)])
