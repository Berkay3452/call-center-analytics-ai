"""Sürümlü API yönlendiricisi (/api/v1). Yeni route modülleri buraya eklenir."""

from fastapi import APIRouter

from app.api.routes import auth, call_intake, calls, crm

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(call_intake.router)
api_v1_router.include_router(calls.router)
api_v1_router.include_router(crm.router)
# Sıradakiler: analysis, dashboard, chat
