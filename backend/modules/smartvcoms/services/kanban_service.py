import os
import sqlite3
from datetime import datetime

import pandas as pd

from backend.modules.smartvcoms.utils import (
    VCOMS_DB_PATH,
    calc_real_elapsed_mins,
    init_vcoms_extended_tables,
    parse_excel_datetime,
)
from backend.modules.smartvcoms.services.permission_scope import apply_vcoms_scope, room_allowed_for_user


def _get_record_date(row):
    for col in ["business_date", "Hồ sơ đến", "Thời gian nhận email", "Cập nhật cuối"]:
        value = row.get(col)
        if pd.notna(value) and str(value).strip() not in ["", "nan", "NaT", "None"]:
            try:
                if isinstance(value, datetime):
                    return value.date()
                return pd.to_datetime(value).date()
            except Exception:
                pass
    return None


def _load_room_display_map() -> dict:
    try:
        conn = sqlite3.connect(VCOMS_DB_PATH)
        rows = conn.execute("SELECT room_name, display_name FROM vcoms_room_config").fetchall()
        conn.close()
        return {
            str(row[0]).strip().upper(): str(row[1]).strip()
            for row in rows
            if len(row) > 1 and row[1]
        }
    except Exception:
        return {}


def _shorten_room(name: str, room_display_map: dict) -> str:
    room_name = str(name).strip()
    upper_name = room_name.upper()
    if upper_name in room_display_map and room_display_map[upper_name]:
        return room_display_map[upper_name]

    for prefix in ["Phòng giao dịch", "PGD", "Phòng", "phòng"]:
        if room_name.lower().startswith(prefix.lower()):
            room_name = room_name[len(prefix):].strip()

    if room_name.upper() in ["KHDN", "BÁN LẺ", "BAN LE"]:
        return room_name

    if len(room_name) > 13:
        return "".join(word[0].upper() for word in room_name.split() if word)
    return room_name


def _load_restricted_keywords() -> list[str]:
    try:
        conn = sqlite3.connect(VCOMS_DB_PATH)
        rows = conn.execute(
            "SELECT room_name FROM vcoms_room_config WHERE is_restricted = 1"
        ).fetchall()
        conn.close()
        return [row[0].upper() for row in rows] if rows else [
            "KHDN",
            "BÁN LẺ",
            "PGD",
            "PHÒNG GIAO DỊCH",
        ]
    except Exception:
        return ["KHDN", "BÁN LẺ", "PGD", "PHÒNG GIAO DỊCH"]


def _load_name_to_id_map() -> dict:
    try:
        from ..store.config_admin import load_config_for_admin

        cb_df, _, _ = load_config_for_admin(VCOMS_DB_PATH)
        if cb_df.empty:
            return {}
        return dict(
            zip(
                cb_df["Tên Cán bộ"].astype(str).str.strip().str.upper(),
                cb_df["ID_CB"].astype(str).str.strip(),
            )
        )
    except Exception:
        return {}


def _load_active_manual_actions() -> set[str]:
    active = set()
    try:
        conn = sqlite3.connect(VCOMS_DB_PATH)
        rows = conn.execute(
            "SELECT case_key FROM vcoms_manual_case_actions WHERE COALESCE(is_active, 1) = 1"
        ).fetchall()
        conn.close()
        for row in rows:
            active.add(row[0])
    except Exception:
        pass
    return active


def _load_manual_overrides() -> dict:
    overrides = {}
    try:
        conn = sqlite3.connect(VCOMS_DB_PATH)
        rows = conn.execute(
            "SELECT case_key, field_name, manual_value FROM vcoms_manual_overrides"
        ).fetchall()
        conn.close()
        for case_key, field_name, manual_value in rows:
            overrides.setdefault(case_key, {})[field_name] = manual_value
    except Exception:
        pass
    return overrides


def _map_ldp_ksv(df: pd.DataFrame) -> pd.DataFrame:
    try:
        from ..store.sqlite_reader import load_ldp_mapping_from_sqlite

        ld_dict = load_ldp_mapping_from_sqlite(VCOMS_DB_PATH)
        col_i_name = df.columns[8]

        def map_ldp(value):
            sender_str = str(value).strip()
            if not sender_str or sender_str.lower() in ["nan", "none"]:
                return ""
            if "/O=" in sender_str.upper() and "CN=" in sender_str.upper():
                name_key = sender_str.split("CN=")[-1].strip()
            else:
                name_key = sender_str.split("<")[0].strip().replace('"', "")

            sorted_keys = sorted(ld_dict.keys(), key=lambda item: len(str(item)), reverse=True)
            for key in sorted_keys:
                if name_key.upper().startswith(str(key).strip().upper()):
                    return str(ld_dict[key]).strip()
            return name_key

        df["LDP_KSV"] = df[col_i_name].apply(map_ldp)
    except Exception:
        df["LDP_KSV"] = ""
    return df


def _resolve_today_cases(df: pd.DataFrame) -> pd.DataFrame:
    df["record_date"] = df.apply(_get_record_date, axis=1)
    operational_date = datetime.now().date()
    df_today = df[df["record_date"] == operational_date].copy()
    return df_today


def fetch_vcoms_cases(current_user: dict) -> dict:
    init_vcoms_extended_tables(VCOMS_DB_PATH)
    try:
        if not os.path.exists(VCOMS_DB_PATH):
            return {"status": "error", "message": "Không tìm thấy CSDL SQLite SmartVCOMS."}

        from ..store.sqlite_reader import load_case_state_as_dashboard

        df = load_case_state_as_dashboard(VCOMS_DB_PATH)
        if df is None or df.empty:
            return {"status": "success", "data": []}

        df_today = _resolve_today_cases(df)
        if df_today.empty:
            return {"status": "success", "data": []}

        df_today = _map_ldp_ksv(df_today)

        df_today, _permission_meta = apply_vcoms_scope(df_today, current_user, room_col="Phòng")

        room_display_map = _load_room_display_map()
        name_to_id = _load_name_to_id_map()
        active_manual_actions = _load_active_manual_actions()
        overrides_dict = _load_manual_overrides()

        now = datetime.now()
        cases = []

        for _, row in df_today.iterrows():
            case_key = row.get("case_key", "")
            cif = str(row.get("CIF", "")).split(".")[0]
            amount = row.get("Số tiền GN", 0)
            if pd.isna(amount):
                amount = 0

            currency = str(row.get("Đồng tiền GN", row.get("currency", "VNĐ"))).upper()
            if "USD" in currency:
                currency = "USD"
            elif "EUR" in currency:
                currency = "EUR"
            else:
                currency = "VNĐ"

            stk_raw = str(row.get("Số tài khoản", "")).strip()
            stk = stk_raw.split(".")[0] if stk_raw.lower() not in ["nan", "none", "<na>", "nat"] else ""

            current_status = str(row.get("Trạng thái Luồng", row.get("current_status", ""))).upper()
            stage_code = str(row.get("current_stage_code", "")).upper()

            kanban_column = "PROCESSING"
            if current_status == "CLOSED":
                kanban_column = "CLOSED"
            elif stage_code in ["WAIT_DISBURSE"]:
                kanban_column = "WAIT_DISBURSE"
            elif stage_code in ["ARRIVAL", "WAIT_ACCEPT"]:
                kanban_column = "ARRIVAL_ACCEPT"

            sla_dt = parse_excel_datetime(row.get("SLA"))
            mins_left = 9999
            sla_status = "SAFE"
            time_display = "---"

            if pd.notna(sla_dt) and current_status != "CLOSED":
                if sla_dt > now:
                    mins_left = calc_real_elapsed_mins(now, sla_dt)
                    time_display = f"- {mins_left}p"
                    if mins_left < 15:
                        sla_status = "WARNING"
                    elif mins_left <= 30:
                        sla_status = "YELLOW"
                else:
                    mins_over = calc_real_elapsed_mins(sla_dt, now)
                    mins_left = -mins_over
                    time_display = f"+ {mins_over}p"
                    sla_status = "DANGER"
            elif current_status == "CLOSED":
                finish_dt = pd.NaT
                luong_val = str(row.get("Luồng GN", "")).upper()
                hs_den_val = row.get("Hồ sơ đến")
                if "ONLINE" in luong_val:
                    finish_dt = parse_excel_datetime(row.get("Giải ngân"))
                elif pd.isna(hs_den_val) or str(hs_den_val).strip() == "":
                    finish_dt = parse_excel_datetime(row.get("Ký số"))
                else:
                    finish_dt = parse_excel_datetime(row.get("Phê duyệt"))

                if pd.notna(finish_dt) and pd.notna(sla_dt):
                    if sla_dt >= finish_dt:
                        diff = int(calc_real_elapsed_mins(finish_dt, sla_dt))
                        time_display = f"Sớm {diff}p" if diff > 0 else "Đã xong"
                        sla_status = "SAFE"
                    else:
                        diff = int(calc_real_elapsed_mins(sla_dt, finish_dt))
                        time_display = f"Vượt {diff}p"
                        sla_status = "DANGER"
                else:
                    time_display = "Đã xong"
                    sla_status = "SAFE"
                mins_left = 9999

            if stage_code == "ARRIVAL":
                stage_label_base = "Hồ sơ đến"
            elif stage_code == "WAIT_ACCEPT":
                stage_label_base = "Chờ T.Nhận"
            elif stage_code == "PROCESSING":
                stage_label_base = "Đang xử lý"
            elif stage_code == "WAIT_SIGN":
                stage_label_base = "Chờ Ký số"
            elif stage_code == "WAIT_MANUAL_DONE":
                stage_label_base = "Chờ H.Tất"
            elif stage_code == "WAIT_DISBURSE":
                stage_label_base = "Chờ giải ngân"
            else:
                stage_label_base = str(row.get("Tiến độ HS", ""))

            start_dt_for_wait = pd.NaT
            if stage_code in ["ARRIVAL", "WAIT_ACCEPT"]:
                start_dt_for_wait = parse_excel_datetime(row.get("Hồ sơ đến"))
                if pd.isna(start_dt_for_wait):
                    start_dt_for_wait = parse_excel_datetime(row.get("Thời gian nhận email"))
            elif stage_code == "PROCESSING":
                start_dt_for_wait = parse_excel_datetime(row.get("Tiếp nhận"))
            elif stage_code in ["WAIT_SIGN", "WAIT_MANUAL_DONE"]:
                start_dt_for_wait = parse_excel_datetime(row.get("Phê duyệt"))
                if pd.isna(start_dt_for_wait):
                    start_dt_for_wait = parse_excel_datetime(row.get("Tiếp nhận"))
            elif stage_code == "WAIT_DISBURSE":
                start_dt_for_wait = parse_excel_datetime(row.get("Ký số"))
                if pd.isna(start_dt_for_wait):
                    start_dt_for_wait = parse_excel_datetime(row.get("Phê duyệt"))

            wait_mins = 0
            stage_label = stage_label_base
            if pd.notna(start_dt_for_wait) and current_status != "CLOSED":
                wait_mins = int(calc_real_elapsed_mins(start_dt_for_wait, now))
                stage_label = f"{stage_label_base} ({wait_mins}p)"

            khung_gio_bucket = ""
            arr_time = row.get("Hồ sơ đến")
            if pd.notna(arr_time) and str(arr_time).strip() != "":
                try:
                    dt_arr = pd.to_datetime(arr_time)
                    hour = dt_arr.hour
                    if hour < 8:
                        khung_gio_bucket = "<08h"
                    elif 8 <= hour <= 10:
                        khung_gio_bucket = f"0{hour}h-0{hour + 1}h" if hour < 9 else f"{hour}h-{hour + 1}h"
                    elif 11 <= hour <= 12:
                        khung_gio_bucket = "11h-13h"
                    elif 13 <= hour <= 16:
                        khung_gio_bucket = f"{hour}h-{hour + 1}h"
                    else:
                        khung_gio_bucket = ">17h"
                except Exception:
                    pass

            tg_cho_gn_bucket = ""
            if current_status == "CLOSED":
                start_gn = row.get("Ký số")
                end_gn = row.get("Giải ngân")
                if (
                    pd.notna(start_gn)
                    and pd.notna(end_gn)
                    and str(start_gn).strip() != ""
                    and str(end_gn).strip() != ""
                ):
                    mins_gn = calc_real_elapsed_mins(
                        parse_excel_datetime(start_gn),
                        parse_excel_datetime(end_gn),
                    )
                    if mins_gn <= 15:
                        tg_cho_gn_bucket = "< 15p"
                    elif mins_gn <= 30:
                        tg_cho_gn_bucket = "15-30p"
                    elif mins_gn <= 45:
                        tg_cho_gn_bucket = "30-45p"
                    elif mins_gn <= 60:
                        tg_cho_gn_bucket = "45-60p"
                    else:
                        tg_cho_gn_bucket = "> 60p"

            case_override = overrides_dict.get(case_key, {})
            customer_name = case_override.get("customer_name", str(row.get("Tên KH", "")).strip())
            cb_httd_value = str(row.get("CB HTTD", "")).replace("nan", "").strip()
            cb_httd = case_override.get("cb_httd", cb_httd_value)

            cases.append(
                {
                    "case_key": case_key,
                    "cif": cif,
                    "customer_name": customer_name,
                    "amount": float(case_override.get("amount", amount)) if "amount" in case_override else amount,
                    "currency": currency,
                    "stk": stk,
                    "room_short": case_override.get(
                        "room_short",
                        _shorten_room(str(row.get("Phòng", "")), room_display_map),
                    ),
                    "cb_httd": cb_httd,
                    "cb_id": name_to_id.get(cb_httd.upper(), cb_httd),
                    "ldp_ksv": str(row.get("LDP_KSV", "")).replace("nan", ""),
                    "stage_code": stage_code,
                    "stage_label": case_override.get("stage_label", stage_label),
                    "stage_label_base": stage_label_base,
                    "kanban_column": kanban_column,
                    "sla_status": sla_status,
                    "time_display": time_display,
                    "mins_left": mins_left,
                    "wait_mins": wait_mins,
                    "has_manual_action": case_key in active_manual_actions,
                    "overridden_fields": list(case_override.keys()),
                    "khung_gio": khung_gio_bucket,
                    "tg_cho_gn": tg_cho_gn_bucket,
                }
            )

        cases = [item for item in cases if room_allowed_for_user(item.get("room_short"), current_user)]
        cases = sorted(cases, key=lambda item: item["mins_left"])
        return {"status": "success", "data": cases}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
