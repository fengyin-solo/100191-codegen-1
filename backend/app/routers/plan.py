"""处置预案库接口：值班入口按机型分组、单条版本明细、步骤补录与版本单向流转。

与台账类模块不同，值班入口返回的是分组结构（groups + pending_models），
但 total 与概览取同一份口径；任何空结果都带 empty/pending_message 说明而不是空白。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.schemas import ActionResult, EntryPayload
from app.services.plan import PlanService

router = APIRouter(prefix="/api/plan", tags=["处置预案库"])

service = PlanService()


class StepsPayload(BaseModel):
    """步骤补录支持一次录入一条或多条，空内容会在服务层拦下并说明。"""

    contents: list[str] = Field(default_factory=list)


@router.get("")
def list_plans(
    keyword: str | None = None,
    model: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """值班入口：按适用机型分组的处置预案，未配置机型单列待补充。

    返回说明字段：total 为值班入口条位数（与概览同口径），groups 为分组列表，
    pending_models 为还没配预案的机型，empty/pending_message 在对应集合为空时给出说明。
    """
    return service.duty_list(keyword=keyword, model=model, status=status)


@router.get("/{version_id}")
def get_plan(version_id: int) -> dict[str, Any]:
    """读取单条预案版本的完整处置步骤与版本历史；停用版本仍可取回看。"""
    plan = service.get_plan(version_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"预案版本 {version_id} 不存在，可能已被清理")
    return plan


@router.post("/{version_id}/steps", response_model=ActionResult)
def add_steps(version_id: int, payload: StepsPayload) -> ActionResult:
    """补录处置步骤：草稿直接追加；生效版复制口径开出新草稿修订。"""
    entry, message = service.add_steps(version_id, payload.contents)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{version_id}/actions", response_model=ActionResult)
def run_action(version_id: int, payload: EntryPayload) -> ActionResult:
    """对预案版本执行发布生效、停用预案；回退或重复推进会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(version_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("", response_model=ActionResult)
def create_plan(payload: EntryPayload) -> ActionResult:
    """在指定机型下新建一份草稿预案（首个版本 V1.0），步骤随后补录。"""
    entry, message = service.create_plan(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"已在 {entry['适用机型']} 下新建草稿预案 {entry['plan_id']}", entry=entry)
