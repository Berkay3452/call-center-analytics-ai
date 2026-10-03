"""Oturum bilgisi. Giriş/çıkış Supabase Auth'ta yapılır; backend yalnızca token'ı doğrular."""

from fastapi import APIRouter

from app.api.deps import CurrentUserDep
from app.core.security import CurrentUser
from app.schemas.common import ErrorResponse

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=CurrentUser, responses={401: {"model": ErrorResponse}})
async def me(user: CurrentUserDep) -> CurrentUser:
    return user
