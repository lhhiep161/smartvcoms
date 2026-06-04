import sqlite3
from datetime import datetime

import pandas as pd

from backend.modules.smartvcoms.utils import (
    VCOMS_DB_PATH,
    calc_real_elapsed_mins,
    init_vcoms_extended_tables,
    parse_excel_datetime,
)
from backend.modules.smartvcoms.services.permission_scope import apply_vcoms_scope


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


def _load_sla_cfg_map() -> dict:
    try:
        conn = sqlite3.connect(VCOMS_DB_PATH)
        rows = conn.execute("SELECT key, value FROM sla_config").fetchall()
        conn.close()
        return {str(key).strip().upper(): str(value).strip() for key, value in rows}
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


def load_statistics(
    mode: str = "today",
    year: int = None,
    month: int = None,
    day: int = None,
    room: str = None,
    current_user: dict | None = None,
) -> dict:
    init_vcoms_extended_tables(VCOMS_DB_PATH)
    try:
        from ..store.sqlite_reader import load_case_state_as_dashboard

        df = load_case_state_as_dashboard(VCOMS_DB_PATH)
        if df is None or df.empty:
            return {"status": "success", "data": {}}

        df["record_date"] = df.apply(_get_record_date, axis=1)
        df["record_date_dt"] = pd.to_datetime(df["record_date"])
        available_years = sorted(df["record_date_dt"].dt.year.dropna().unique().tolist(), reverse=True)

        if mode == "today":
            operational_date = datetime.now().date()
            df_stat = df[df["record_date"] == operational_date].copy()
        else:
            df_stat = df.copy()
            if year:
                df_stat = df_stat[df_stat["record_date_dt"].dt.year == year]
            if month:
                df_stat = df_stat[df_stat["record_date_dt"].dt.month == month]
            if day:
                df_stat = df_stat[df_stat["record_date_dt"].dt.day == day]

        if df_stat.empty:
            return {
                "status": "success",
                "data": {
                    "phong_ban": [],
                    "pheu": [],
                    "khung_gio": [],
                    "tg_giai_ngan": [],
                    "available_years": [int(item) for item in available_years],
                },
            }

        if current_user:
            df_stat, _permission_meta = apply_vcoms_scope(df_stat, current_user, room_col="Phòng")

        room_display_map = _load_room_display_map()
        sla_cfg_map = _load_sla_cfg_map()
        df_stat["room_short"] = df_stat["Phòng"].apply(lambda value: _shorten_room(value, room_display_map))
        if room and str(room).strip() != "":
            df_stat = df_stat[df_stat["room_short"] == str(room).strip()]

        col_trang_thai = next(
            (col for col in df_stat.columns if str(col).lower() == "trạng thái luồng"),
            "current_status",
        )
        df_stat["Status_Group"] = df_stat[col_trang_thai].astype(str).str.upper().map(
            {"OPEN": "Đang xử lý", "CLOSED": "Đã xong"}
        )

        phong_ban = []
        for room_short in df_stat["room_short"].dropna().unique():
            sub = df_stat[df_stat["room_short"] == room_short]
            open_count = len(sub[sub["Status_Group"] == "Đang xử lý"])
            closed_count = len(sub[sub["Status_Group"] == "Đã xong"])
            phong_ban.append(
                {
                    "phong": room_short,
                    "open": open_count,
                    "closed": closed_count,
                    "total": open_count + closed_count,
                }
            )
        phong_ban = sorted(phong_ban, key=lambda item: item["total"], reverse=True)

        pheu_counts = {}
        for _, row in df_stat.iterrows():
            stage_code = str(row.get("current_stage_code", "")).upper()
            status = str(row.get(col_trang_thai, "")).upper()
            label = "Khác"
            if status == "CLOSED":
                label = "Hoàn thành"
            elif stage_code == "ARRIVAL":
                label = "Hồ sơ đến"
            elif stage_code == "WAIT_ACCEPT":
                label = "Chờ T.Nhận"
            elif stage_code == "PROCESSING":
                label = "Đang xử lý"
            elif stage_code == "WAIT_SIGN":
                label = "Chờ Ký số"
            elif stage_code == "WAIT_MANUAL_DONE":
                label = "Chờ H.Tất"
            elif stage_code == "WAIT_DISBURSE":
                label = "Chờ giải ngân"
            pheu_counts[label] = pheu_counts.get(label, 0) + 1

        pheu_order = [
            "Hồ sơ đến",
            "Chờ T.Nhận",
            "Đang xử lý",
            "Chờ Ký số",
            "Chờ H.Tất",
            "Chờ giải ngân",
            "Hoàn thành",
        ]
        pheu = [
            {"stage": stage, "count": pheu_counts.get(stage, 0)}
            for stage in pheu_order
            if pheu_counts.get(stage, 0) > 0
        ]

        buckets = ["<08h", "08h-09h", "09h-10h", "10h-11h", "11h-13h", "13h-14h", "14h-15h", "15h-16h", "16h-17h", ">17h"]
        kg_counts = {bucket: 0 for bucket in buckets}
        for _, row in df_stat.iterrows():
            arr = row.get("Hồ sơ đến")
            if pd.isna(arr):
                continue
            try:
                dt = pd.to_datetime(arr)
                hour = dt.hour
                if hour < 8:
                    bucket = "<08h"
                elif 8 <= hour <= 10:
                    bucket = f"0{hour}h-0{hour + 1}h" if hour < 9 else f"{hour}h-{hour + 1}h"
                elif 11 <= hour <= 12:
                    bucket = "11h-13h"
                elif 13 <= hour <= 16:
                    bucket = f"{hour}h-{hour + 1}h"
                else:
                    bucket = ">17h"
                kg_counts[bucket] += 1
            except Exception:
                pass
        khung_gio = [{"bucket": bucket, "count": kg_counts[bucket]} for bucket in buckets]

        gn_buckets = ["< 15p", "15-30p", "30-45p", "45-60p", "> 60p"]
        gn_counts = {bucket: 0 for bucket in gn_buckets}
        closed_df = df_stat[df_stat[col_trang_thai].astype(str).str.upper() == "CLOSED"]
        for _, row in closed_df.iterrows():
            start = row.get("Ký số")
            end = row.get("Giải ngân")
            if pd.isna(start) or pd.isna(end) or str(start).strip() == "" or str(end).strip() == "":
                continue
            mins = calc_real_elapsed_mins(parse_excel_datetime(start), parse_excel_datetime(end), sla_cfg_map)
            if mins <= 15:
                gn_counts["< 15p"] += 1
            elif mins <= 30:
                gn_counts["15-30p"] += 1
            elif mins <= 45:
                gn_counts["30-45p"] += 1
            elif mins <= 60:
                gn_counts["45-60p"] += 1
            else:
                gn_counts["> 60p"] += 1
        tg_giai_ngan = [{"bucket": bucket, "count": gn_counts[bucket]} for bucket in gn_buckets]

        return {
            "status": "success",
            "data": {
                "phong_ban": phong_ban,
                "pheu": pheu,
                "khung_gio": khung_gio,
                "tg_giai_ngan": tg_giai_ngan,
                "available_years": [int(item) for item in available_years],
            },
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
