from fastapi import APIRouter

from app.api.courses import router as courses_router
from app.api.curriculum import router as curriculum_router
from app.api.dashboard import router as dashboard_router
from app.api.documents import router as documents_router
from app.api.learning import router as learning_router
from app.api.progress import router as progress_router
from app.api.review import router as review_router
from app.auth.router import router as auth_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(courses_router)
api_router.include_router(documents_router)
api_router.include_router(curriculum_router)
api_router.include_router(learning_router)
api_router.include_router(review_router)
api_router.include_router(progress_router)
api_router.include_router(dashboard_router)
