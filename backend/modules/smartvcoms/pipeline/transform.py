"""Main transform from Data sheet rows to Dashboard-form dataframe."""

from __future__ import annotations

from typing import Any

import pandas as pd
from datetime import date

from .assignment import assign_officer, recalculate_config_load, update_last_assigned
from .excel_io import DASHBOARD_COLUMNS, WorkbookInputs
from .parser import normalize_text, parse_email_row
from .sla import calculate_sla


def _empty_dashboard_row() -> dict[str, Any]:
    return {c: pd.NA for c in DASHBOARD_COLUMNS}


def _is_blank(value: Any) -> bool:
    if pd.isna(value):
        return True
    return str(value).strip() == ""


def _norm_money(value: Any) -> float:
    s = str(value or "").replace(",", "").replace(" VND", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def _norm_mahs(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _norm_cif(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _build_state(dashboard_df: pd.DataFrame) -> dict[str, Any]:
    by_ma_hs: dict[str, int] = {}
    open_by_cif_money: dict[tuple[str, float], list[int]] = {}

    for idx in range(len(dashboard_df)):
        row = dashboard_df.iloc[idx]
        ma_hs = _norm_mahs(row.get("Mã hồ sơ"))
        cif = _norm_cif(row.get("CIF"))
        money = _norm_money(row.get("Số tiền GN"))
        status = str(row.get("Trạng thái Luồng") or "").strip().upper()

        if ma_hs:
            by_ma_hs[ma_hs] = idx
        if status == "OPEN" and cif and money > 0:
            open_by_cif_money.setdefault((cif, money), []).append(idx)

    return {
        "by_ma_hs": by_ma_hs,
        "open_by_cif_money": open_by_cif_money,
    }


def _parse_row_business_date(row: pd.Series) -> date | None:
    for col in ("Thời gian nhận email", "Hồ sơ đến", "Cập nhật cuối"):
        val = row.get(col)
        dt = pd.to_datetime(val, errors="coerce")
        if pd.notna(dt):
            return dt.date()
    return None


def _filter_dashboard_by_business_date(dashboard_df: pd.DataFrame, target_date: date) -> pd.DataFrame:
    if dashboard_df is None or dashboard_df.empty:
        return pd.DataFrame(columns=dashboard_df.columns if dashboard_df is not None else [])
    out = dashboard_df.copy()
    out["_biz_date"] = out.apply(_parse_row_business_date, axis=1)
    out = out[out["_biz_date"] == target_date].copy()
    return out.drop(columns=["_biz_date"], errors="ignore")


def _find_target_row(parsed: dict[str, Any], dashboard_df: pd.DataFrame) -> tuple[int | None, str]:
    state = _build_state(dashboard_df)

    ma_hs = _norm_mahs(parsed.get("ma_ho_so"))
    cif = _norm_cif(parsed.get("cif"))
    money = _norm_money(parsed.get("so_tien_gn"))

    if ma_hs:
        idx = state["by_ma_hs"].get(ma_hs)
        if idx is not None:
            return idx, "UPDATE_BY_MAHS"

        if cif and money > 0:
            candidates = state["open_by_cif_money"].get((cif, money), [])
            blank_mahs_candidates = [
                i for i in candidates if _is_blank(dashboard_df.at[i, "Mã hồ sơ"])
            ]
            if blank_mahs_candidates:
                chosen = sorted(blank_mahs_candidates, key=lambda i: pd.to_numeric(dashboard_df.at[i, "STT"], errors="coerce"))[0]
                return int(chosen), "UPDATE_BY_CIF_MONEY_AND_FILL_MAHS"

        return None, "CREATE_NEW"

    if cif and money > 0:
        candidates = state["open_by_cif_money"].get((cif, money), [])
        if candidates:
            chosen = sorted(candidates, key=lambda i: pd.to_numeric(dashboard_df.at[i, "STT"], errors="coerce"))[0]
            return int(chosen), "UPDATE_BY_CIF_MONEY_NO_MAHS"

    return None, "CREATE_NEW"


def _compute_status(row: dict[str, Any], parsed: dict[str, Any], keywords: dict[str, str]) -> str:
    progress = normalize_text(row.get("Tiến độ HS"))
    body = normalize_text(parsed.get("body"))
    luong = normalize_text(row.get("Luồng GN"))
    is_return = bool(parsed.get("is_return_case", False))

    k_dagn = normalize_text(keywords.get("Da_GN", "đã giải ngân"))
    k_kyso = normalize_text(keywords.get("Ky_So", "ký số"))
    k_kyso2 = normalize_text(keywords.get("Ky_So2", "kí số"))
    k_phed = normalize_text(keywords.get("Phe_Duyet", "phê duyệt"))
    k_tt = normalize_text(keywords.get("Thong_Thuong", "Thông thường"))

    if k_dagn and k_dagn in progress:
        return "CLOSED"
    if is_return:
        return "CLOSED"
    if ((k_kyso and k_kyso in progress) or (k_kyso2 and k_kyso2 in progress)) and "ipay" in body:
        return "CLOSED"
    if ((k_kyso and k_kyso in progress) or (k_kyso2 and k_kyso2 in progress)) and pd.isna(row.get("Hồ sơ đến")):
        return "CLOSED"
    if k_phed and k_phed in progress and k_tt and k_tt in luong:
        return "CLOSED"
    return "OPEN"


def _clean_progress(progress: str | None) -> str | None:
    if not progress:
        return None
    p = str(progress).strip()
    for pref in ["C.tiếp:", "FW:", "RE:"]:
        if p.lower().startswith(pref.lower()):
            p = p[len(pref) :].strip()
    return p


def _get_last_recipient_name(body: str, recipients: str) -> str:
    body_text = str(body or "").replace("_x000D_", "\n").replace("\r", "")
    ds = ""
    if "to:" in body_text.lower():
        for line in body_text.split("\n"):
            line_strip = line.strip()
            if line_strip.lower().startswith("to:"):
                ds = line_strip[3:].strip()
                break
    if not ds:
        ds = str(recipients or "")
    parts = ds.split(";")
    return parts[-1].strip() if parts else ""


def process_data_to_dashboard(
    inputs: WorkbookInputs,
    skip_done: bool = True,
    collect_lineage: bool = False,
    return_config_cb: bool = False,
    assignment_scope: str = "today",
    assignment_date: date | None = None,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame] | tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Process Data sheet rows sequentially into a 24-column Dashboard dataframe."""
    data_df = inputs.data.copy()
    dashboard_df = inputs.dashboard.copy()
    config_cb = inputs.config_cb.copy()
    lineage_rows: list[dict[str, Any]] = []

    data_df["_sort_stt"] = pd.to_numeric(data_df.get("STT"), errors="coerce")
    data_df = data_df.sort_values(by=["_sort_stt"], na_position="last")
    if skip_done and "Status" in data_df.columns:
        status_norm = data_df["Status"].astype(str).str.strip().str.lower()
        data_df = data_df[status_norm != "done"]

    if dashboard_df.empty:
        dashboard_df = pd.DataFrame(columns=DASHBOARD_COLUMNS)
    if assignment_date is None:
        assignment_date = date.today()

    for _, src_row in data_df.iterrows():
        stt_data = src_row.get("STT")
        if pd.isna(src_row.get("EntryID")):
            continue

        parsed = parse_email_row(src_row, inputs.keywords, inputs.config_ld, inputs.phongban)
        if parsed.get("skip"):
            if collect_lineage:
                lineage_rows.append(
                    {
                        "data_row_number": stt_data,
                        "subject_raw": src_row.get("Tiêu đề"),
                        "progress_normalized": "",
                        "CIF": "",
                        "Mã hồ sơ": "",
                        "money_normalized": 0,
                        "Tên KH": "",
                        "event_type": "",
                        "is_return": False,
                        "target_action": "SKIP",
                        "target_stt_before": "",
                        "target_stt_after": "",
                        "target_ma_hs_before": "",
                        "target_ma_hs_after": "",
                        "reason": parsed.get("reason", "skip"),
                        "open_closed_after": "",
                    }
                )
            continue

        idx, action = _find_target_row(parsed, dashboard_df)
        creating_new = idx is None

        target_stt_before = ""
        target_ma_before = ""
        if not creating_new:
            target_stt_before = dashboard_df.at[idx, "STT"]
            target_ma_before = dashboard_df.at[idx, "Mã hồ sơ"]

        if creating_new:
            row = _empty_dashboard_row()
            row["STT"] = len(dashboard_df) + 1
            row["Trạng thái Luồng"] = "OPEN"
            row["Thời gian nhận email"] = parsed.get("receive_time")

            suggested_cb = ""
            cif = _norm_cif(parsed.get("cif"))
            assignment_df = (
                _filter_dashboard_by_business_date(dashboard_df, assignment_date)
                if assignment_scope == "today"
                else dashboard_df
            )
            if cif and not assignment_df.empty:
                hist = assignment_df[assignment_df["CIF"].astype(str).str.strip() == cif]
                if not hist.empty:
                    suggested_cb = str(hist.iloc[-1].get("CB HTTD") or "")

            config_cb = recalculate_config_load(config_cb, assignment_df)
            officer = assign_officer(parsed, dashboard_df, config_cb, suggested_cb=suggested_cb)
            row["CB HTTD"] = officer
            config_cb = update_last_assigned(config_cb, officer or "", parsed.get("receive_time"))
        else:
            row = dashboard_df.loc[idx].to_dict()

        if _is_blank(row.get("Mã hồ sơ")):
            row["Mã hồ sơ"] = parsed.get("ma_ho_so") or row.get("Mã hồ sơ")
        if _is_blank(row.get("Phòng")):
            row["Phòng"] = parsed.get("phong") or row.get("Phòng")
        if _is_blank(row.get("CIF")):
            row["CIF"] = parsed.get("cif") or row.get("CIF")
        if _is_blank(row.get("Tên KH")):
            row["Tên KH"] = parsed.get("ten_kh") or row.get("Tên KH")
        if _is_blank(row.get("Số tiền GN")):
            row["Số tiền GN"] = parsed.get("so_tien_gn") or row.get("Số tiền GN")
        if _is_blank(row.get("Luồng GN")):
            row["Luồng GN"] = parsed.get("luong_gn") or row.get("Luồng GN")
        if parsed.get("cb_thuc_te") and str(parsed.get("cb_thuc_te")) != str(row.get("CB HTTD") or ""):
            row["CB HTTD"] = parsed.get("cb_thuc_te")
            config_cb = update_last_assigned(config_cb, row["CB HTTD"], pd.Timestamp.now())
        if parsed.get("ldp_ksv") and _is_blank(row.get("LĐP/KSV HTTD")):
            row["LĐP/KSV HTTD"] = parsed.get("ldp_ksv")
        if pd.notna(parsed.get("sla")):
            row["SLA"] = parsed.get("sla")
        if parsed.get("so_tai_khoan"):
            row["Số tài khoản"] = parsed.get("so_tai_khoan")

        event_type = parsed.get("event_type")
        recv_time = parsed.get("receive_time")
        if event_type == "HS_Den":
            row["Hồ sơ đến"] = recv_time
        elif event_type == "Tiep_Nhan":
            row["Tiếp nhận"] = recv_time
        elif event_type == "Phe_Duyet":
            row["Phê duyệt"] = recv_time
        elif event_type == "Ky_So":
            row["Ký số"] = recv_time
        elif event_type == "Da_GN":
            row["Giải ngân"] = recv_time

        subj_norm = normalize_text(parsed.get("subject"))
        progress = _clean_progress(parsed.get("progress"))
        if progress and "thay đổi" not in subj_norm:
            row["Tiến độ HS"] = progress

        row["_is_return_case"] = parsed.get("is_return_case", False)
        if (
            parsed.get("event_type") == "Phe_Duyet"
            and normalize_text(row.get("Luồng GN")) == normalize_text(inputs.keywords.get("Thong_Thuong", "Thông thường"))
        ):
            ldp_last = _get_last_recipient_name(parsed.get("body", ""), parsed.get("recipients", ""))
            if ldp_last:
                row["LĐP/KSV HTTD"] = ldp_last
        row["Trạng thái Luồng"] = _compute_status(row, parsed, inputs.keywords)

        total, httd, bgd = calculate_sla(row, inputs.sla_config)
        row["Thời gian SLA"] = total
        row["Thời gian SLA HTTD"] = httd
        row["Thời gian SLA BGĐ"] = bgd

        row["Cập nhật cuối"] = pd.Timestamp.now().floor("s")
        row["EntryID"] = parsed.get("entry_id")
        row.pop("_is_return_case", None)

        if creating_new:
            dashboard_df = pd.concat([dashboard_df, pd.DataFrame([row])], ignore_index=True)
            target_stt_after = row.get("STT")
            target_ma_after = row.get("Mã hồ sơ")
        else:
            for col in row.keys():
                if col in dashboard_df.columns:
                    dashboard_df.at[idx, col] = row[col]
            target_stt_after = dashboard_df.at[idx, "STT"]
            target_ma_after = dashboard_df.at[idx, "Mã hồ sơ"]

        if collect_lineage:
            lineage_rows.append(
                {
                    "data_row_number": stt_data,
                    "subject_raw": src_row.get("Tiêu đề"),
                    "progress_normalized": progress or "",
                    "CIF": parsed.get("cif") or "",
                    "Mã hồ sơ": parsed.get("ma_ho_so") or "",
                    "money_normalized": _norm_money(parsed.get("so_tien_gn")),
                    "Tên KH": parsed.get("ten_kh") or "",
                    "event_type": event_type or "",
                    "is_return": bool(parsed.get("is_return_case", False)),
                    "target_action": action,
                    "target_stt_before": target_stt_before,
                    "target_stt_after": target_stt_after,
                    "target_ma_hs_before": target_ma_before,
                    "target_ma_hs_after": target_ma_after,
                    "reason": action,
                    "open_closed_after": row.get("Trạng thái Luồng", ""),
                }
            )

    for col in DASHBOARD_COLUMNS:
        if col not in dashboard_df.columns:
            dashboard_df[col] = pd.NA
    dashboard_df = dashboard_df[DASHBOARD_COLUMNS]
    dashboard_df = dashboard_df.sort_values(by="STT", na_position="last").reset_index(drop=True)
    dashboard_df["CIF"] = dashboard_df["CIF"].astype("string").fillna("").str.strip()
    dashboard_df["Số tài khoản"] = dashboard_df["Số tài khoản"].astype("string").fillna("").str.strip()

    if collect_lineage and return_config_cb:
        lineage_df = pd.DataFrame(lineage_rows)
        return dashboard_df, lineage_df, config_cb
    if collect_lineage:
        lineage_df = pd.DataFrame(lineage_rows)
        return dashboard_df, lineage_df
    if return_config_cb:
        return dashboard_df, config_cb
    return dashboard_df
