"""故障处置预案库接口：值班看板、版本列表、详情历史、步骤补录与版本流转。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.plan import STATUS_ORDER, plan_service

router = APIRouter(prefix="/api/plan", tags=["故障处置预案库"])


@router.get("/duty-board")
def duty_board() -> dict[str, Any]:
    """值班入口：按适用机型分组呈现可用预案；未配预案的机型单独待补充。"""
    return plan_service.duty_board()


@router.get("/models")
def list_models() -> dict[str, Any]:
    """机型目录：用于筛选与新建预案；为空时给出说明。"""
    models = plan_service.models()
    return {
        "items": models,
        "total": len(models),
        "note": "机型目录尚未维护，请先在机组台账中确认适用机型" if not models else "",
    }


@router.get("", response_model=PageResult[dict])
def list_versions(
    keyword: str | None = Query(default=None, description="按预案编号或名称检索"),
    model: str | None = Query(default=None, description="按适用机型筛选"),
    status: str | None = Query(default=None, description="草稿、生效、停用"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """预案列表：按机型分组口径返回版本；空结果带说明而不是空白页。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUS_ORDER:
        raise HTTPException(status_code=400, detail=f"版本状态只支持：{'、'.join(STATUS_ORDER)}")
    items, total, note = plan_service.list_versions(
        keyword=keyword, model=model, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size, note=note)


@router.get("/{version_id}", response_model=dict)
def get_version(version_id: int) -> dict[str, Any]:
    """单条预案详情：包含完整处置步骤；不存在时给出可读说明。"""
    row = plan_service.get(version_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"预案版本 {version_id} 不存在或已删除")
    return row


@router.get("/{version_id}/history")
def get_history(version_id: int) -> dict[str, Any]:
    """历史修订版本：按修订当时的步骤快照回看。"""
    row = plan_service.get(version_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"预案版本 {version_id} 不存在或已删除")
    history = plan_service.history(str(row.get("预案编号") or ""))
    assert history is not None
    return history


@router.post("/{version_id}/steps", response_model=ActionResult)
def add_step(version_id: int, payload: EntryPayload) -> ActionResult:
    """补录处置步骤：仅草稿版本可补录，补录后列表步骤数量同步变化。"""
    title = str(payload.values.get("标题") or "").strip()
    content = str(payload.values.get("内容") or "").strip()
    entry, message = plan_service.add_step(version_id, title, content)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{version_id}/actions", response_model=ActionResult)
def run_action(version_id: int, payload: EntryPayload) -> ActionResult:
    """版本流转：发布生效、停用；单向推进，回退动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = plan_service.transition(version_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{version_id}/revision", response_model=ActionResult)
def create_revision(version_id: int) -> ActionResult:
    """基于生效版本修订出新草稿版本，沿用当时的处置步骤继续完善。"""
    entry, message = plan_service.create_revision(version_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("", response_model=ActionResult)
def create_plan(payload: EntryPayload) -> ActionResult:
    """为待补充机型登记一份草稿预案。"""
    entry, message = plan_service.create_plan(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
