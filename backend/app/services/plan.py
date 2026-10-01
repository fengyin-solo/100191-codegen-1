"""处置预案库业务规则：按机型分组、版本单向流转、历史快照回看都收在这里。

口径约定（概览与列表必须一致，都从本服务取数）：
- 值班入口只出现「最新版本不是停用」的预案系列，一条系列在列表里只占一个条位；
- 预案版本只能 草稿 → 生效 → 停用 单向推进，生效版被新生效版替换时自动停用；
- 停用是终态：停用系列退出值班入口，但历史版本与处置步骤仍可按修订时间回看；
- 每个版本的 steps 是当时口径的快照，补录到生效版会开出新的草稿修订，不改旧版。
"""
from __future__ import annotations

import copy
import re
from datetime import date
from typing import Any

from app.store import store

MODULE = "plan"

# 值班场景在册的机型，顺序即列表分组顺序；不在册的机型不能挂预案
TURBINE_MODELS = ["GW-1.5MW", "MY2.0-104", "SE-12125", "EN-141/2.5", "GW-3.0MW"]

# 预案版本只允许沿这个方向单向推进，不允许回退
VERSION_FLOW = ["草稿", "生效", "停用"]
ACTION_RULES = {"发布生效": "生效", "停用预案": "停用"}

REQUIRED_FIELDS = ["预案名称", "适用机型"]

EMPTY_NO_PLAN = "值班入口暂未配置任何处置预案，请先在对应机型下新建预案，补录处置步骤后发布生效。"
EMPTY_NO_MATCH = "当前筛选条件下没有可展示的处置预案，请调整机型、版本状态或关键词后重试。"
PENDING_DONE = "全部在册机型均已配置处置预案，暂无待补充机型。"
STEPS_EMPTY = "该版本暂未录入处置步骤；草稿状态可直接补录，生效版本补录会生成新的草稿修订。"

_VERSION_RE = re.compile(r"^V(\d+)(?:\.(\d+))?$")


def _today() -> str:
    return date.today().isoformat()


def _step_count(row: dict[str, Any]) -> int:
    return len(row.get("steps") or [])


def _sort_versions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一系列按修订时间排版本；同一天补录的按记录 id 兜底，保证先后稳定。"""
    return sorted(rows, key=lambda row: (str(row.get("修订日期", "")), int(row.get("id", 0))))


def _version_meta(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "版本号": row["版本号"],
        "status": row["status"],
        "修订日期": row["修订日期"],
        "步骤数量": _step_count(row),
        "修订说明": row.get("修订说明", ""),
    }


class PlanService:
    # ---- 取数口径 ----
    def _series(self) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in store.rows(MODULE):
            grouped.setdefault(str(row["plan_id"]), []).append(row)
        return grouped

    def _active_series(self) -> dict[str, tuple[dict[str, Any], list[dict[str, Any]]]]:
        """plan_id -> (最新版本, 全部版本)；最新版已停用的系列不进值班入口。"""
        active: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
        for plan_id, rows in self._series().items():
            versions = _sort_versions(rows)
            head = versions[-1]
            if head.get("status") == "停用":
                continue
            active[plan_id] = (head, versions)
        return active

    def _summary(self, head: dict[str, Any], versions: list[dict[str, Any]]) -> dict[str, Any]:
        # 头部是草稿但系列里还挂着生效版，说明生效版正在修订中
        revising = head.get("status") == "草稿" and any(
            row.get("status") == "生效" for row in versions[:-1]
        )
        return {
            "id": head["id"],
            "plan_id": head["plan_id"],
            "预案名称": head["预案名称"],
            "适用机型": head["适用机型"],
            "版本号": head["版本号"],
            "status": head["status"],
            "步骤数量": _step_count(head),
            "最近修订日期": head["修订日期"],
            "修订中": revising,
        }

    def duty_list(
        self,
        *,
        keyword: str | None = None,
        model: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """值班入口分组列表：按机型分组呈现，没配预案的机型进待补充栏。"""
        active = self._active_series()
        configured = {head["适用机型"] for head, _ in active.values()}
        key = (keyword or "").strip()

        def matched(head: dict[str, Any]) -> bool:
            if model and head.get("适用机型") != model:
                return False
            if status and head.get("status") != status:
                return False
            if key and key not in f"{head['plan_id']} {head['预案名称']}":
                return False
            return True

        groups: list[dict[str, Any]] = []
        total = 0
        for m in TURBINE_MODELS:
            if model and m != model:
                continue
            items = [
                self._summary(head, versions)
                for head, versions in active.values()
                if head["适用机型"] == m and matched(head)
            ]
            items.sort(key=lambda item: str(item["plan_id"]))
            if items:
                groups.append({"适用机型": m, "items": items})
                total += len(items)

        pending = [m for m in TURBINE_MODELS if m not in configured]
        if model:
            pending = [m for m in pending if m == model]

        if not active:
            empty = EMPTY_NO_PLAN
        elif total == 0:
            empty = EMPTY_NO_MATCH
        else:
            empty = ""

        return {
            "total": total,
            "groups": groups,
            "pending_models": pending,
            "pending_message": PENDING_DONE if not pending else "",
            "empty": empty,
            "stats": self.duty_stats(),
        }

    def duty_stats(self) -> dict[str, int]:
        """概览卡片与列表卡片共用这一份口径，保证条数一致。"""
        active = self._active_series()
        heads = [head for head, _ in active.values()]
        return {
            "值班入口预案": len(heads),
            "生效中": sum(1 for head in heads if head["status"] == "生效"),
            "草稿": sum(1 for head in heads if head["status"] == "草稿"),
            "待补充机型": sum(
                1
                for m in TURBINE_MODELS
                if m not in {head["适用机型"] for head in heads}
            ),
        }

    # ---- 单条与历史回看 ----
    def get_plan(self, version_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, version_id)
        if row is None:
            return None
        versions = _sort_versions(self._series()[str(row["plan_id"])])
        head = versions[-1]
        series_offline = head.get("status") == "停用"
        is_head = row["id"] == head["id"]
        return {
            "plan_id": row["plan_id"],
            "预案名称": row["预案名称"],
            "适用机型": row["适用机型"],
            "head_id": None if series_offline else head["id"],
            "version": _version_meta(row),
            "steps": self._step_view(row),
            "versions": [_version_meta(item) for item in reversed(versions)],
            "readonly": series_offline or not is_head,
            "steps_empty": "" if _step_count(row) else STEPS_EMPTY,
        }

    def _step_view(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        # 返回带序号的快照副本，序号按当时录入顺序，不允许外层改动历史
        return [
            {"序号": index + 1, "内容": str(item.get("内容", "")), "补充时间": item.get("补充时间", "")}
            for index, item in enumerate(copy.deepcopy(row.get("steps") or []))
        ]

    # ---- 写操作 ----
    def create_plan(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        model_name = str(values["适用机型"]).strip()
        if model_name not in TURBINE_MODELS:
            return None, f"机型「{model_name}」不在值班机型册内，可选：{'、'.join(TURBINE_MODELS)}"
        rows = store.rows(MODULE)
        max_serial = 1000
        for raw in rows:
            serial = re.fullmatch(r"PLAN-(\d+)", str(raw.get("plan_id", "")))
            if serial:
                max_serial = max(max_serial, int(serial.group(1)))
        entry = {
            "id": max((int(raw.get("id", 0)) for raw in rows), default=0) + 1,
            "plan_id": f"PLAN-{max_serial + 1}",
            "预案名称": str(values["预案名称"]).strip(),
            "适用机型": model_name,
            "版本号": "V1.0",
            "status": VERSION_FLOW[0],
            "修订日期": _today(),
            "修订说明": "新建草稿",
            "steps": [],
            "pending": True,
            "abnormal": False,
        }
        rows.append(entry)
        return entry, ""

    def add_steps(
        self, version_id: int, contents: list[Any]
    ) -> tuple[dict[str, Any] | None, str]:
        row = store.find(MODULE, version_id)
        if row is None:
            return None, f"预案版本 {version_id} 不存在，可能已被清理"
        if row.get("status") == "停用":
            return None, "已停用版本属于历史归档，不允许再补录步骤；请基于最新版本发起修订"
        clean = [str(item).strip() for item in contents if str(item or "").strip()]
        if not clean:
            return None, "请填写至少一条处置步骤"

        new_steps = [{"内容": text, "补充时间": _today()} for text in clean]
        if row.get("status") == "草稿":
            row.setdefault("steps", []).extend(new_steps)
            row["修订日期"] = _today()
            return row, f"已补录 {len(clean)} 条处置步骤，当前草稿共 {_step_count(row)} 步"

        # 生效版不能直接改：复制当时口径开出下一版草稿，旧版快照保持不动
        versions = _sort_versions(self._series()[str(row["plan_id"])])
        majors = []
        for item in versions:
            parsed = _VERSION_RE.fullmatch(str(item["版本号"]))
            if parsed:
                majors.append(int(parsed.group(1)))
        next_no = f"V{max(majors, default=1) + 1}.0"
        rows = store.rows(MODULE)
        draft = {
            "id": max((int(raw.get("id", 0)) for raw in rows), default=0) + 1,
            "plan_id": row["plan_id"],
            "预案名称": row["预案名称"],
            "适用机型": row["适用机型"],
            "版本号": next_no,
            "status": "草稿",
            "修订日期": _today(),
            "修订说明": f"基于 {row['版本号']} 补录 {len(clean)} 条处置步骤",
            "steps": copy.deepcopy(row.get("steps") or []) + new_steps,
            "pending": True,
            "abnormal": False,
        }
        rows.append(draft)
        return draft, (
            f"已基于生效版本 {row['版本号']} 生成草稿修订 {next_no} 并补录 {len(clean)} 步，"
            "发布生效后才会替换值班入口版本"
        )

    def run_action(self, version_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        row = store.find(MODULE, version_id)
        if row is None:
            return None, f"预案版本 {version_id} 不存在，可能已被清理"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于预案版本可执行范围（仅支持发布生效、停用预案）"
        target = ACTION_RULES[action]
        current = row.get("status")
        current_index = VERSION_FLOW.index(current) if current in VERSION_FLOW else -1
        target_index = VERSION_FLOW.index(target)
        if target_index <= current_index:
            # 同级或回退一律拦下：版本只能单向推进，停用后不允许回到生效
            if current == "停用":
                return None, "该版本已停用并退出值班入口，停用是终态，不能重新生效"
            if current == target:
                return None, f"该版本当前已是「{current}」状态，无需重复{action}"
            return None, f"预案版本只能按 草稿 → 生效 → 停用 单向推进，不能从{current}回到{target}"

        if target == "生效":
            superseded = [
                item
                for item in self._series()[str(row["plan_id"])]
                if item.get("status") == "生效" and item["id"] != row["id"]
            ]
            for item in superseded:
                item["status"] = "停用"
                item["pending"] = False
                item["修订说明"] = f"被 {row['版本号']} 发布生效替换后自动停用"
            row["status"] = "生效"
            row["pending"] = False
            tail = f"，原生效版本 {'、'.join(item['版本号'] for item in superseded)} 已自动停用" if superseded else ""
            return row, f"预案 {row['版本号']} 已发布生效，出现在值班入口{tail}"

        # target == 停用：只允许从生效停用；草稿未发布，不能跳过生效直接下线
        if current == "草稿":
            return None, "草稿尚未发布生效，不能直接停用；请先发布生效，或放弃草稿后重新修订"
        row["status"] = "停用"
        row["pending"] = False
        return row, f"预案 {row['版本号']} 已停用并从值班入口下线，历史步骤仍可回看"
