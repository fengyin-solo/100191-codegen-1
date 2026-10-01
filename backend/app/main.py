"""风电场机组运维平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ROUTERS
from app.services.plan import plan_service
from app.store import store

app = FastAPI(title="风电场机组运维平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    payload = store.overview()
    modules = payload["modules"]
    assert isinstance(modules, list)
    # 故障处置预案库按值班入口同口径补一行，条数与预案列表完全一致
    board = plan_service.duty_board()
    modules.append({
        "name": "故障处置预案库",
        "created": int(board["total"]),
        "pending": int(board["draft_count"]),
        "abnormal": int(board["pending_model_count"]),
    })
    cards = [
        {"label": "业务模块", "value": len(modules)},
        {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
        {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
        {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
    ]
    return {"cards": cards, "modules": modules}
