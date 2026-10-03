"""Sürümlü API yönlendiricisi (/api/v1). Yeni route modülleri buraya eklenir."""

from fastapi import APIRouter

from app.api.routes import auth

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
# Sıradakiler: calls, analysis, dashboard, chat
