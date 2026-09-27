"""观测记录业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "observation"
REQUIRED_FIELDS = ["记录编号", "所属站点", "观测要素"]
OPTIONAL_FIELDS = ["观测时刻", "观测数值", "数值单位"]
FILTER_FIELDS = ["记录编号", "所属站点", "观测要素"]
STATUS_ORDER = ["待质控", "质控通过", "疑误标记", "已作废"]
VOID_STATUS = STATUS_ORDER[-1]
ACTION_RULES = {"提交质控": "质控通过", "标记疑误": "疑误标记", "作废记录": "已作废"}
# 状态 -> 质控标识：列表、详情、清单都按这一份投影展示，避免三处口径不一
QC_FLAGS = {"待质控": "未质控", "质控通过": "合格", "疑误标记": "疑误", "已作废": "作废"}
# 状态 -> (pending, abnormal)：已作废两个标记都落下，正常统计自然把它排除
STATUS_FLAGS = {
    "待质控": (True, False),
    "质控通过": (False, False),
    "疑误标记": (True, True),
    "已作废": (False, False),
}


def _present(row: dict[str, Any]) -> dict[str, Any]:
    """把内部状态投影成展示字段：列表、详情、清单共用这一份，看到的永远是同一条记录。"""
    item = dict(row)
    status = str(row.get("status") or "")
    item["记录状态"] = status
    item["质控标识"] = QC_FLAGS.get(status, "")
    return item


class ObservationService:
    def _filter_rows(self, filters: dict[str, str]) -> list[dict[str, Any]]:
        """统一筛选口径：列表、统计、清单都走这里，不会出现各算各的。"""
        rows = store.rows(MODULE)
        for field in FILTER_FIELDS:
            value = str(filters.get(field) or "").strip()
            if value:
                rows = [row for row in rows if value in str(row.get(field, ""))]
        status = str(filters.get("status") or "").strip()
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(filters or {})
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_present(row) for row in rows[start:start + size]], total

    def stats(self, *, filters: dict[str, str] | None = None) -> dict[str, Any]:
        """统计口径：与列表同一份过滤结果；已作废不进正常统计，单独计数。"""
        rows = self._filter_rows(filters or {})
        by_status = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            status = str(row.get("status") or "")
            if status in by_status:
                by_status[status] += 1
        voided = by_status[VOID_STATUS]
        return {
            "matched": len(rows),
            "valid": len(rows) - voided,
            "voided": voided,
            "by_status": by_status,
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return _present(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        record_no = str(values.get("记录编号") or "").strip()
        # 记录编号是检索主键，重复编号要单独提示，不能静默落库
        if any(str(row.get("记录编号") or "").strip() == record_no for row in store.rows(MODULE)):
            return None, f"记录编号 {record_no} 已存在，请更换编号后再登记"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip() != "":
                entry[field] = value
        entry["status"] = STATUS_ORDER[0]
        entry["pending"], entry["abnormal"] = STATUS_FLAGS[entry["status"]]
        rows.append(entry)
        return _present(entry), "观测记录已登记"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"观测记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于观测记录可执行范围"
        target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        if current == target:
            # 幂等：同一动作重复执行直接返回现状，不重复计数
            return _present(entry), f"观测记录已处于「{target}」，不重复{action}"
        if current == VOID_STATUS:
            return None, f"观测记录已作废，不能再执行「{action}」"
        entry["status"] = target
        entry["pending"], entry["abnormal"] = STATUS_FLAGS[target]
        return _present(entry), f"观测记录已{action}"
