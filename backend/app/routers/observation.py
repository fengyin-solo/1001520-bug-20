"""观测记录接口：维护观测记录，覆盖提交质控、标记疑误、作废记录等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.observation import ObservationService

router = APIRouter(prefix="/api/observation", tags=["观测记录"])

service = ObservationService()

LIST_FIELDS = ["记录编号", "所属站点", "观测要素", "观测时刻", "观测数值", "数值单位", "质控标识", "记录状态"]
STATUSES = ["待质控", "质控通过", "疑误标记", "已作废"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    station: str | None = Query(default=None, description="按所属站点检索"),
    element: str | None = Query(default=None, description="按观测要素检索"),
    status: str | None = Query(default=None, description="待质控、质控通过、疑误标记、已作废"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按编号、站点、要素、状态过滤观测记录；统计与列表同口径，没有数据时返回空页。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total, stats = service.list_entries(
        keyword=keyword, station=station, element=element, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size, stats=stats)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    station: str | None = Query(default=None, description="按所属站点检索"),
    element: str | None = Query(default=None, description="按观测要素检索"),
    status: str | None = Query(default=None, description="待质控、质控通过、疑误标记、已作废"),
) -> dict[str, Any]:
    """导出观测记录清单：与列表同一份过滤结果，已作废记录保留并用记录状态列区分。"""
    items, stats = service.export_entries(keyword=keyword, station=station, element=element, status=status)
    return {"module": "observation", "total": len(items), "stats": stats, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条观测记录明细；与列表同一份数据，不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"观测记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条观测记录；缺字段或记录编号重复时说明原因而不是静默丢弃。"""
    entry, error = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=error)
    return ActionResult(ok=True, message="观测记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条观测记录执行提交质控、标记疑误、作废记录；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
