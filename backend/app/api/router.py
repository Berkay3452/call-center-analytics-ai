"""Sürümlü API yönlendiricisi (/api/v1). Yeni route modülleri buraya eklenir."""

from fastapi import APIRouter

from app.api.routes import auth, call_intake

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(call_intake.router)
# Sıradakiler: calls, analysis, dashboard, chat
