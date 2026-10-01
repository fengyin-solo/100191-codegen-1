"""故障处置预案库业务规则。

口径约定：
- 版本状态只能按 草稿 -> 生效 -> 停用 单向推进，不允许回退；
- 同一预案编号有新版本生效时，旧生效版本自动停用（仍可按修订时间回看）；
- 停用版本不再进入值班入口，历史版本保留修订当时的步骤快照；
- 值班入口列表与运营概览共用 duty_board 的统计口径，条数天然一致。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.store import store

MODULE = "plan"
MODEL_MODULE = "plan_model"

STATUS_DRAFT = "草稿"
STATUS_ACTIVE = "生效"
STATUS_RETIRED = "停用"
STATUS_ORDER = [STATUS_DRAFT, STATUS_ACTIVE, STATUS_RETIRED]
# 值班入口可见状态：停用版本不再出现在值班入口
DUTY_STATUSES = [STATUS_DRAFT, STATUS_ACTIVE]

EMPTY_NOTE = "当前筛选条件下暂无可展示的预案；停用版本不会出现在值班入口，可在历史修订中回看"


class PlanService:
    # ---------- 基础读取 ----------
    def rows(self) -> list[dict[str, Any]]:
        return store.rows(MODULE)

    def models(self) -> list[str]:
        return [str(row.get("机型") or "") for row in store.rows(MODEL_MODULE)]

    def get(self, version_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, version_id)

    @staticmethod
    def _step_count(row: dict[str, Any]) -> int:
        return len(row.get("步骤") or [])

    @staticmethod
    def _version_parts(version: str) -> tuple[int, int]:
        """解析 V2.0 这种主次版本号，无法识别时按 (0, 0) 处理。"""
        match = re.match(r"^\s*[vV]?(\d+)(?:\.(\d+))?", str(version or ""))
        if not match:
            return 0, 0
        return int(match.group(1)), int(match.group(2) or 0)

    def _summarize(self, row: dict[str, Any]) -> dict[str, Any]:
        """列表项口径：预案版本、适用机型、步骤数量、最近修订日期。"""
        return {
            "id": row["id"],
            "预案编号": row.get("预案编号"),
            "预案名称": row.get("预案名称"),
            "适用机型": row.get("适用机型"),
            "版本": row.get("版本"),
            "status": row.get("status"),
            "步骤数量": self._step_count(row),
            "最近修订": row.get("最近修订"),
        }

    # ---------- 值班入口：按机型分组 ----------
    def duty_board(self) -> dict[str, Any]:
        """值班预案看板：按适用机型分组，未配预案的机型单独列为待补充。

        停用版本不出现在值班入口；某机型只有停用版本时，同样视为待补充。
        """
        visible = [row for row in self.rows() if row.get("status") in DUTY_STATUSES]
        covered = {str(row.get("适用机型") or "") for row in visible}
        models = self.models() or sorted({str(row.get("适用机型") or "") for row in self.rows()})

        grouped: list[dict[str, Any]] = []
        for model in models:
            items = sorted(
                (self._summarize(row) for row in visible if row.get("适用机型") == model),
                key=lambda item: str(item["最近修订"] or ""),
                reverse=True,
            )
            if not items:
                continue
            grouped.append({
                "适用机型": model,
                "预案数量": len(items),
                "生效数量": sum(1 for item in items if item["status"] == STATUS_ACTIVE),
                "草稿数量": sum(1 for item in items if item["status"] == STATUS_DRAFT),
                "items": items,
            })

        pending_models = [model for model in models if model not in covered]
        total = len(visible)
        return {
            "total": total,
            "active_count": sum(1 for row in visible if row.get("status") == STATUS_ACTIVE),
            "draft_count": sum(1 for row in visible if row.get("status") == STATUS_DRAFT),
            "model_count": len(models),
            "pending_model_count": len(pending_models),
            "groups": grouped,
            "pending_models": pending_models,
            "note": "当前没有可用于值班的预案，请先登记处置预案" if not visible else "",
            "pending_note": "全部机型均已配置预案，没有待补充机型" if not pending_models else "",
        }

    def duty_count(self) -> int:
        """概览口径：与值班入口列表逐条同口径。"""
        return int(self.duty_board()["total"])

    # ---------- 预案列表（分页/筛选） ----------
    def list_versions(
        self,
        *,
        keyword: str | None = None,
        model: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int, str]:
        rows = self.rows()
        # 默认口径与值班入口一致：停用版本不出现在列表，保证列表与概览条数一致；
        # 显式按「停用」筛选时仍可在历史口径下检索
        if not status:
            rows = [row for row in rows if row.get("status") in DUTY_STATUSES]
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("预案编号", "")) or keyword in str(row.get("预案名称", ""))
            ]
        if model:
            rows = [row for row in rows if row.get("适用机型") == model]
        if status:
            rows = [row for row in rows if row.get("status") == status]

        # 先按最近修订倒序，再按机型做稳定分组排序：组内保持修订时间倒序
        rows = sorted(rows, key=lambda row: str(row.get("最近修订") or ""), reverse=True)
        rows = sorted(rows, key=lambda row: str(row.get("适用机型") or ""))

        items = [self._summarize(row) for row in rows]
        total = len(items)
        start = max(page - 1, 0) * size
        paged = items[start:start + size]
        note = "" if paged else EMPTY_NOTE
        return paged, total, note

    # ---------- 单条详情与历史 ----------
    def history(self, plan_no: str) -> dict[str, Any] | None:
        """按预案编号取全部修订版本，按修订时间排列；步骤为当时口径的快照。"""
        versions = sorted(
            (row for row in self.rows() if row.get("预案编号") == plan_no),
            key=lambda row: (str(row.get("最近修订") or ""), self._version_parts(str(row.get("版本")))),
        )
        if not versions:
            return None
        return {
            "预案编号": plan_no,
            "预案名称": versions[-1].get("预案名称"),
            "适用机型": versions[-1].get("适用机型"),
            "版本数量": len(versions),
            "versions": [
                {
                    **self._summarize(row),
                    "步骤": list(row.get("步骤") or []),
                }
                for row in versions
            ],
        }

    # ---------- 步骤补录 ----------
    def add_step(self, version_id: int, title: str, content: str) -> tuple[dict[str, Any] | None, str]:
        row = self.get(version_id)
        if row is None:
            return None, f"预案版本 {version_id} 不存在或已删除"
        if row.get("status") != STATUS_DRAFT:
            return None, "仅草稿状态的预案可补录处置步骤；生效版本如需调整请修订出新版本"
        if not title.strip():
            return None, "缺少步骤标题，无法补录"

        steps = list(row.get("步骤") or [])
        steps.append({"seq": len(steps) + 1, "标题": title, "内容": content})
        row["步骤"] = steps
        row["最近修订"] = date.today().isoformat()
        return row, f"处置步骤已补录，当前共 {len(steps)} 步"

    # ---------- 版本流转 ----------
    def transition(self, version_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        row = self.get(version_id)
        if row is None:
            return None, f"预案版本 {version_id} 不存在或已删除"

        rules = {"发布生效": STATUS_ACTIVE, "停用": STATUS_RETIRED}
        target = rules.get(action)
        if target is None:
            return None, f"动作「{action}」不属于预案版本可执行范围"

        current = str(row.get("status") or "")
        current_idx = STATUS_ORDER.index(current) if current in STATUS_ORDER else -1
        target_idx = STATUS_ORDER.index(target)
        # 只能沿 草稿 -> 生效 -> 停用 单向推进，不允许回退
        if target_idx != current_idx + 1:
            return None, f"预案版本只能按 草稿→生效→停用 单向推进，当前为{current}，不能{action}"

        if target == STATUS_ACTIVE:
            # 同编号旧生效版本随新版本生效自动停用，停用后不再进入值班入口
            for other in self.rows():
                if (
                    other is not row
                    and other.get("预案编号") == row.get("预案编号")
                    and other.get("status") == STATUS_ACTIVE
                ):
                    other["status"] = STATUS_RETIRED
                    other["pending"] = False

        row["status"] = target
        row["pending"] = target == STATUS_DRAFT
        return row, f"预案 {row.get('预案编号')} {row.get('版本')} 已{action}"

    # ---------- 新建预案 / 修订新版本 ----------
    def create_plan(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        name = str(values.get("预案名称") or "").strip()
        model = str(values.get("适用机型") or "").strip()
        if not name or not model:
            return None, "缺少必填字段：预案名称、适用机型"
        if model not in self.models():
            return None, f"机型 {model} 不在机型目录中，请先确认适用机型"
        if any(row.get("适用机型") == model and row.get("status") == STATUS_DRAFT for row in self.rows()):
            return None, f"机型 {model} 已有草稿预案待生效，不能重复登记"

        existing = {str(row.get("预案编号") or "") for row in self.rows()}
        next_no = 1
        while f"YJ-{next_no:03d}" in existing:
            next_no += 1
        plan_no = f"YJ-{next_no:03d}"
        return self._insert_version(plan_no, name, model, "V1.0"), f"预案 {plan_no} 已登记为草稿"

    def create_revision(self, version_id: int) -> tuple[dict[str, Any] | None, str]:
        """基于已有版本修订：只有生效版本可以修订，草稿先沿用其内容继续完善。"""
        source = self.get(version_id)
        if source is None:
            return None, f"预案版本 {version_id} 不存在或已删除"
        if source.get("status") != STATUS_ACTIVE:
            return None, "只有生效中的预案可以修订新版本；草稿请直接补录完善，停用版本不可再修订"

        plan_no = str(source.get("预案编号") or "")
        latest = max(
            (row for row in self.rows() if row.get("预案编号") == plan_no),
            key=lambda row: self._version_parts(str(row.get("版本"))),
        )
        if latest.get("status") == STATUS_DRAFT:
            return None, f"该预案已有草稿版本 {latest.get('版本')}，请先发布或删除后再修订"

        major, minor = self._version_parts(str(latest.get("版本")))
        next_version = f"V{major}.{minor + 1}"
        new_row = self._insert_version(
            plan_no,
            str(source.get("预案名称") or ""),
            str(source.get("适用机型") or ""),
            next_version,
            steps=list(source.get("步骤") or []),
        )
        return new_row, f"修订版本 {next_version} 已创建，沿用 {source.get('版本')} 的处置步骤"

    def _insert_version(
        self,
        plan_no: str,
        name: str,
        model: str,
        version: str,
        steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        rows = self.rows()
        row: dict[str, Any] = {
            "id": max((int(item.get("id", 0)) for item in rows), default=0) + 1,
            "status": STATUS_DRAFT,
            "pending": True,
            "abnormal": False,
            "预案编号": plan_no,
            "预案名称": name,
            "适用机型": model,
            "版本": version,
            "最近修订": date.today().isoformat(),
            "步骤": [dict(step) for step in (steps or [])],
        }
        rows.append(row)
        return row


plan_service = PlanService()
