"""Officer assignment logic for VCOMS dashboard records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


def _normalize_cb_id(value: Any, config_cb: pd.DataFrame) -> str:
    raw = str(value or "").strip()
    if not raw or config_cb.empty:
        return raw
    cb = config_cb.copy()
    if "ID_CB" not in cb.columns:
        return raw
    cb["ID_CB"] = cb["ID_CB"].astype(str).str.strip()
    hit_by_id = cb[cb["ID_CB"].str.upper() == raw.upper()]
    if not hit_by_id.empty:
        return str(hit_by_id.iloc[0].get("ID_CB") or "").strip() or raw
    if "Tên Cán bộ" not in cb.columns:
        return raw
    cb["Tên Cán bộ"] = cb["Tên Cán bộ"].astype(str).str.strip()
    hit_by_name = cb[cb["Tên Cán bộ"].str.upper() == raw.upper()]
    if not hit_by_name.empty:
        return str(hit_by_name.iloc[0].get("ID_CB") or "").strip() or raw
    return raw


def recalculate_config_load(config_cb: pd.DataFrame, dashboard_df: pd.DataFrame) -> pd.DataFrame:
    """Recompute workload score columns from current dashboard snapshot."""
    cb = config_cb.copy()
    dashboard = dashboard_df.copy()

    id_col = "ID_CB"
    status_col = "Trạng thái"
    total_col = "Tổng phút SLA"
    offset_col = "Phút Bù Trừ"
    score_col = "Điểm Phân Giao"

    if "CB HTTD" in dashboard.columns:
        dashboard["CB HTTD"] = dashboard["CB HTTD"].map(lambda value: _normalize_cb_id(value, cb))
    totals = (
        dashboard.groupby("CB HTTD", dropna=True)["Thời gian SLA"].sum(min_count=1).fillna(0).to_dict()
        if "CB HTTD" in dashboard.columns and "Thời gian SLA" in dashboard.columns
        else {}
    )

    if id_col not in cb.columns:
        cb[id_col] = ""
    cb[id_col] = cb[id_col].astype(str).str.strip()
    cb[total_col] = cb[id_col].map(lambda officer_id: totals.get(officer_id, 0.0) if pd.notna(officer_id) else 0.0)
    if offset_col not in cb.columns:
        cb[offset_col] = 0.0
    cb[offset_col] = pd.to_numeric(cb[offset_col], errors="coerce").fillna(0.0)
    cb[score_col] = pd.to_numeric(cb[total_col], errors="coerce").fillna(0.0) + cb[offset_col]

    if "Lần giao cuối" not in cb.columns:
        cb["Lần giao cuối"] = pd.NaT
    if status_col not in cb.columns:
        cb[status_col] = "Ready"

    return cb


def assign_officer(record: dict[str, Any], dashboard_df: pd.DataFrame, config_cb: pd.DataFrame, suggested_cb: str = "") -> str | None:
    """Assign officer using VBA rule: suggested Ready first, else lowest score and oldest assign time."""
    if config_cb.empty:
        return None

    id_col = "ID_CB"
    status_col = "Trạng thái"

    ready = config_cb[config_cb[status_col].astype(str).str.lower() == "ready"].copy()
    if ready.empty:
        first = config_cb[id_col].dropna()
        return str(first.iloc[0]) if not first.empty else None

    if suggested_cb:
        suggested_id = _normalize_cb_id(suggested_cb, config_cb)
        m = ready[ready[id_col].astype(str).str.strip() == suggested_id]
        if not m.empty:
            return suggested_id

    ready["Điểm Phân Giao"] = pd.to_numeric(ready.get("Điểm Phân Giao", 0), errors="coerce").fillna(0)
    ready["Lần giao cuối"] = pd.to_datetime(ready.get("Lần giao cuối"), errors="coerce")
    ready = ready.sort_values(by=["Điểm Phân Giao", "Lần giao cuối"], ascending=[True, True], na_position="first")

    chosen = ready.iloc[0].get(id_col)
    return str(chosen) if pd.notna(chosen) else None


def update_last_assigned(config_cb: pd.DataFrame, officer: str, timestamp: datetime | pd.Timestamp | None) -> pd.DataFrame:
    """Update in-memory last-assigned timestamp for selected officer."""
    if not officer:
        return config_cb
    cb = config_cb.copy()
    if "ID_CB" not in cb.columns:
        return cb
    if "Lần giao cuối" not in cb.columns:
        cb["Lần giao cuối"] = pd.NaT
    cb["Lần giao cuối"] = pd.to_datetime(cb["Lần giao cuối"], errors="coerce").dt.floor("s")
    ts = pd.to_datetime(timestamp, errors="coerce")
    if pd.isna(ts):
        ts = pd.Timestamp.now()
    ts = pd.Timestamp(ts).floor("s")
    # Assign through series to avoid pandas datetime64[s] precision conversion errors.
    series = cb["Lần giao cuối"].astype("object")
    normalized_officer = _normalize_cb_id(officer, cb)
    mask = cb["ID_CB"].astype(str).str.strip() == normalized_officer
    if not mask.any():
        return cb
    series.loc[mask] = ts
    cb["Lần giao cuối"] = pd.to_datetime(series, errors="coerce")
    return cb
