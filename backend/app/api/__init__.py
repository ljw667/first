"""
API 路由汇总

导入所有子路由模块，创建主路由 router，
在 main.py 中以 /api 前缀统一挂载。
"""

from fastapi import APIRouter

from app.api.chat import router as chat_router
from app.api.health import router as health_router

router = APIRouter()

router.include_router(health_router)
router.include_router(chat_router)
