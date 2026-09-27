"""观测记录接口：维护观测记录，覆盖提交质控、标记疑误、作废记录等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.observation import ObservationService

router = APIRouter(prefix="/api/observation", tags=["观测记录"])

service = ObservationService()

MAX_PAGE_SIZE = 200
EXPORT_PAGE_SIZE = 10000


def observation_filters(
    record_no: str | None = Query(default=None, alias="记录编号", description="按记录编号模糊检索"),
    station: str | None = Query(default=None, alias="所属站点", description="按所属站点模糊检索"),
    element: str | None = Query(default=None, alias="观测要素", description="按观测要素模糊检索"),
    status: str | None = Query(default=None, description="待质控、质控通过、疑误标记、已作废"),
) -> dict[str, str]:
    """把查询参数整理成服务层认的过滤条件：列表、统计、清单共用同一份口径。"""
    filters: dict[str, str] = {}
    if record_no and record_no.strip():
        filters["记录编号"] = record_no.strip()
    if station and station.strip():
        filters["所属站点"] = station.strip()
    if element and element.strip():
        filters["观测要素"] = element.strip()
    if status and status.strip():
        filters["status"] = status.strip()
    return filters


# 注意：/export、/stats 必须注册在 /{entry_id} 之前，否则 "export" 会被当成 entry_id
# 匹配进详情接口，清单请求永远落在 422 上。
@router.get("/export")
def export_entries(filters: dict[str, str] = Depends(observation_filters)) -> dict[str, Any]:
    """导出观测记录清单：与列表同一份过滤口径；已作废记录保留在清单里并标注状态。"""
    items, total = service.list_entries(filters=filters, page=1, size=EXPORT_PAGE_SIZE)
    summary = service.stats(filters=filters)
    return {
        "module": "observation",
        "total": total,
        "voided": summary["voided"],
        "items": items,
    }


@router.get("/stats")
def stats_entries(filters: dict[str, str] = Depends(observation_filters)) -> dict[str, Any]:
    """观测记录统计：与列表同一份过滤口径；已作废不进正常统计，单独计数。"""
    return service.stats(filters=filters)


@router.get("", response_model=PageResult[dict])
def list_entries(
    filters: dict[str, str] = Depends(observation_filters),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号、所属站点、观测要素与状态过滤观测记录列表；没有数据时返回空页，不报错。"""
    if size > MAX_PAGE_SIZE:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(filters=filters, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条观测记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"观测记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条观测记录；缺字段或记录编号重复时说明原因，不静默丢弃。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """状态流转：动作落库后才返回；同一动作重复执行幂等，不重复计数。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
