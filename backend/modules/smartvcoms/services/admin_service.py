from datetime import datetime

import pandas as pd

from backend.modules.smartvcoms.utils import VCOMS_DB_PATH, connect_vcoms_sqlite, init_vcoms_extended_tables


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


def _load_room_config() -> list[dict]:
    try:
        conn = connect_vcoms_sqlite(VCOMS_DB_PATH)
        rows = conn.execute(
            "SELECT id, room_name, is_restricted, display_name FROM vcoms_room_config"
        ).fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "room_name": row[1],
                "is_restricted": row[2],
                "display_name": row[3] if len(row) > 3 and row[3] else "",
            }
            for row in rows
        ]
    except Exception:
        return []


def _enrich_cb_metrics(cb_df: pd.DataFrame, df_state: pd.DataFrame) -> pd.DataFrame:
    if df_state.empty or cb_df.empty:
        return cb_df

    df_state["record_date"] = df_state.apply(_get_record_date, axis=1)
    op_date = datetime.now().date()
    df_today = df_state[df_state["record_date"] == op_date].copy()
    if df_today.empty:
        return cb_df

    col_trang_thai = next(
        (col for col in df_today.columns if str(col).lower() == "trạng thái luồng"),
        "current_status",
    )
    cb_col = next((col for col in df_today.columns if "CB" in str(col).upper()), "CB HTTD")
    if cb_col not in df_today.columns or "ID_CB" not in cb_df.columns:
        return cb_df

    cb_df = cb_df.copy()
    cb_df["ID_CB"] = cb_df["ID_CB"].astype(str).str.strip()
    cb_df["Tên Cán bộ"] = cb_df["Tên Cán bộ"].astype(str).str.strip()
    df_today[cb_col] = df_today[cb_col].astype(str).str.strip()
    name_to_id = {
        str(row.get("Tên Cán bộ") or "").strip().upper(): str(row.get("ID_CB") or "").strip()
        for _, row in cb_df.iterrows()
        if str(row.get("Tên Cán bộ") or "").strip() and str(row.get("ID_CB") or "").strip()
    }
    id_set = {
        str(row.get("ID_CB") or "").strip().upper()
        for _, row in cb_df.iterrows()
        if str(row.get("ID_CB") or "").strip()
    }

    def _normalize_cb(value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        upper = raw.upper()
        if upper in id_set:
            return raw
        return name_to_id.get(upper, raw)

    df_today[cb_col] = df_today[cb_col].map(_normalize_cb)

    df_open = df_today[df_today[col_trang_thai].astype(str).str.upper() == "OPEN"]
    cb_counts = df_open.groupby(cb_col).size()
    cb_df["Đang xử lý"] = cb_df.apply(
        lambda row: int(cb_counts.get(row["ID_CB"], 0)),
        axis=1,
    )

    sla_col = next(
        (col for col in df_today.columns if str(col).lower() in ["sla_minutes", "thời gian sla"]),
        None,
    )
    if sla_col:
        df_today[sla_col] = pd.to_numeric(df_today[sla_col], errors="coerce").fillna(0)
        cb_sla_sum = df_today.groupby(cb_col)[sla_col].sum()
        cb_df["Tổng phút SLA"] = cb_df.apply(
            lambda row: float(cb_sla_sum.get(row["ID_CB"], 0.0)),
            axis=1,
        )

    cb_df["Phút Bù Trừ"] = pd.to_numeric(cb_df["Phút Bù Trừ"], errors="coerce").fillna(0.0).astype(float)
    cb_df["Điểm Phân Giao"] = cb_df.get("Tổng phút SLA", 0.0) + cb_df["Phút Bù Trừ"]
    return cb_df


def load_admin_config() -> dict:
    init_vcoms_extended_tables(VCOMS_DB_PATH)
    try:
        from ..store.config_admin import ensure_default_sla_config, load_config_for_admin
        from ..store.sqlite_reader import load_case_state_as_dashboard

        try:
            ensure_default_sla_config(VCOMS_DB_PATH)
            cb_df, ld_df, sla_df = load_config_for_admin(VCOMS_DB_PATH)
            cb_df = cb_df.fillna("") if cb_df is not None else pd.DataFrame()
            ld_df = ld_df.fillna("") if ld_df is not None else pd.DataFrame()
            sla_df = sla_df.fillna("") if sla_df is not None else pd.DataFrame()
            if not sla_df.empty:
                sla_df = sla_df.rename(columns={"label": "Tiêu chí", "value": "Giá trị"})
        except Exception:
            cb_df, ld_df, sla_df = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        try:
            df_state = load_case_state_as_dashboard(VCOMS_DB_PATH)
            cb_df = _enrich_cb_metrics(cb_df, df_state)
        except Exception:
            pass

        return {
            "status": "success",
            "data": {
                "cb_config": cb_df.to_dict("records") if not cb_df.empty else [],
                "ld_config": ld_df.to_dict("records") if not ld_df.empty else [],
                "sla_config": sla_df.to_dict("records") if not sla_df.empty else [],
                "room_config": _load_room_config(),
            },
        }
    except Exception as exc:
        return {"status": "error", "message": f"Lỗi tải cấu hình: {exc}"}


def update_cb_config(rows: list[dict], current_user: dict) -> dict:
    try:
        from ..store.config_admin import load_config_for_admin, upsert_config_cb

        try:
            old_cb_df, _, _ = load_config_for_admin(VCOMS_DB_PATH)
            old_status_map = {
                str(row.get("ID_CB", "")).strip(): str(row.get("Trạng thái", "")).strip().lower()
                for _, row in old_cb_df.iterrows()
            }
        except Exception:
            old_status_map = {}

        compensation_messages = []
        for row in rows:
            cb_id = str(row.get("ID_CB", "")).strip()
            new_status = str(row.get("Trạng thái", "")).strip().lower()
            old_status = old_status_map.get(cb_id, new_status)
            if old_status != "ready" and new_status == "ready":
                compensation_messages.append(cb_id)

        upsert_config_cb(VCOMS_DB_PATH, pd.DataFrame(rows), user=str(current_user.get("username", "ui")))

        message = "Đã lưu cấu hình Cán bộ."
        if compensation_messages:
            message += f" (Tự động bù trừ điểm cho: {', '.join(compensation_messages)})"
        return {"status": "success", "message": message}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def update_room_config(rows: list[dict]) -> dict:
    try:
        conn = connect_vcoms_sqlite(VCOMS_DB_PATH)
        conn.execute("DELETE FROM vcoms_room_config")
        for row in rows:
            if row.get("room_name"):
                conn.execute(
                    """
                    INSERT INTO vcoms_room_config (room_name, is_restricted, display_name)
                    VALUES (?, ?, ?)
                    """,
                    (
                        str(row.get("room_name")).strip(),
                        row.get("is_restricted", 1),
                        str(row.get("display_name", "")).strip(),
                    ),
                )
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Đã lưu cấu hình Phòng ban."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def update_ld_config(rows: list[dict], current_user: dict) -> dict:
    try:
        from ..store.config_admin import upsert_config_ld

        upsert_config_ld(VCOMS_DB_PATH, pd.DataFrame(rows), user=str(current_user.get("username", "ui")))
        return {"status": "success", "message": "Đã lưu cấu hình LĐP/KSV."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def update_sla_config(rows: list[dict], current_user: dict) -> dict:
    try:
        from ..store.config_admin import upsert_sla_config

        df_to_save = pd.DataFrame(rows)
        if "Tiêu chí" in df_to_save.columns:
            df_to_save = df_to_save.rename(columns={"Tiêu chí": "label"})
        if "Giá trị" in df_to_save.columns:
            df_to_save = df_to_save.rename(columns={"Giá trị": "value"})

        upsert_sla_config(VCOMS_DB_PATH, df_to_save, user=str(current_user.get("username", "ui")))
        return {"status": "success", "message": "Đã cập nhật cấu hình SLA."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
