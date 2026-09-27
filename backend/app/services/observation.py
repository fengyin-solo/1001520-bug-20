"""观测记录业务规则：状态流转、字段校验与筛选口径都收在这里。

列表、详情、导出清单、统计卡片都走同一份过滤结果，避免出现
"列表一个数、页脚一个数、清单又一个数" 的口径分裂。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "observation"
REQUIRED_FIELDS = ["记录编号", "所属站点", "观测要素"]
EDITABLE_FIELDS = ["记录编号", "所属站点", "观测要素", "观测时刻", "观测数值", "数值单位", "质控标识"]
STATUS_ORDER = ["待质控", "质控通过", "疑误标记", "已作废"]
ACTION_RULES = {"提交质控": "质控通过", "标记疑误": "疑误标记", "作废记录": "已作废"}
NEGATIVE_ACTIONS = ["作废记录"]
VOID_STATUS = "已作废"


class ObservationService:
    def _filtered_rows(
        self,
        *,
        keyword: str | None = None,
        station: str | None = None,
        element: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """唯一的过滤入口：列表、统计、导出清单都从这批行里出数。"""
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if station:
            rows = [row for row in rows if station in str(row.get("所属站点", ""))]
        if element:
            rows = [row for row in rows if element in str(row.get("观测要素", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    @staticmethod
    def _present(row: dict[str, Any]) -> dict[str, Any]:
        """状态以 status 字段为唯一来源，展示用的「记录状态」始终与它同步。"""
        item = dict(row)
        item["记录状态"] = str(row.get("status") or item.get("记录状态") or "")
        return item

    @staticmethod
    def _stats(rows: list[dict[str, Any]]) -> dict[str, int]:
        """统计口径：已作废不进有效记录统计，但单独计数，清单里也能区分。"""
        counts = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            status = str(row.get("status") or "")
            if status in counts:
                counts[status] += 1
        return {
            "有效记录": sum(counts[status] for status in STATUS_ORDER if status != VOID_STATUS),
            "待质控": counts["待质控"],
            "质控通过": counts["质控通过"],
            "疑误标记": counts["疑误标记"],
            VOID_STATUS: counts[VOID_STATUS],
        }

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        station: str | None = None,
        element: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        rows = self._filtered_rows(keyword=keyword, station=station, element=element, status=status)
        total = len(rows)
        start = max(page - 1, 0) * size
        items = [self._present(row) for row in rows[start:start + size]]
        return items, total, self._stats(rows)

    def export_entries(
        self,
        *,
        keyword: str | None = None,
        station: str | None = None,
        element: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """清单与列表同一份过滤结果；已作废记录保留在清单里，靠记录状态列区分。"""
        rows = self._filtered_rows(keyword=keyword, station=station, element=element, status=status)
        return [self._present(row) for row in rows], self._stats(rows)

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self._present(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        serial = str(values.get("记录编号") or "").strip()
        rows = store.rows(MODULE)
        if any(str(row.get("记录编号", "")).strip() == serial for row in rows):
            return None, f"记录编号 {serial} 已存在，请更换编号后再登记"
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in EDITABLE_FIELDS:
            if values.get(field) is not None:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["记录状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._present(entry), ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"观测记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于观测记录可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        current = str(entry.get("status") or "")
        if current == target:
            # 幂等：重复执行同一动作不改变状态，统计也不会重复计数
            return self._present(entry), f"观测记录已是「{target}」，未重复{action}"
        if current == VOID_STATUS:
            return None, f"观测记录已作废，不能再执行「{action}」"
        entry["status"] = target
        entry["记录状态"] = target
        entry["pending"] = target != VOID_STATUS
        entry["abnormal"] = action in NEGATIVE_ACTIONS or target == "疑误标记"
        return self._present(entry), f"观测记录已{action}"
