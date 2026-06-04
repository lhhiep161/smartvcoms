import os
import sqlite3
from datetime import datetime, time, timedelta

import pandas as pd

VCOMS_DB_PATH = os.getenv("VCOMS_DB_PATH", "runtime_data/smartvcoms/vcoms.db").strip()

_vcoms_tables_init = False
DEFAULT_WORK_WINDOWS = [(time(8, 0), time(12, 0)), (time(13, 0), time(19, 30))]
DEFAULT_SLA_WINDOWS = [(time(8, 0), time(12, 0)), (time(13, 0), time(19, 30))]


def init_vcoms_extended_tables(db_path):
    global _vcoms_tables_init
    if _vcoms_tables_init or not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS vcoms_manual_overrides (
        id INTEGER PRIMARY KEY AUTOINCREMENT, case_key TEXT, field_name TEXT, manual_value TEXT, created_by TEXT, created_at TEXT,
        UNIQUE(case_key, field_name)
    )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS vcoms_routing_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT, keyword TEXT, flow_type TEXT, is_active INTEGER DEFAULT 1
    )"""
    )
    try:
        conn.execute("ALTER TABLE vcoms_routing_rules ADD COLUMN auto_close_at_stage TEXT")
    except Exception:
        pass

    conn.execute(
        """CREATE TABLE IF NOT EXISTS vcoms_assignment_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT, flow_type TEXT, room_name TEXT, assigned_officers TEXT, is_active INTEGER DEFAULT 1
    )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS vcoms_room_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT, room_name TEXT, is_restricted INTEGER DEFAULT 1, display_name TEXT,
        UNIQUE(room_name)
    )"""
    )
    try:
        conn.execute("ALTER TABLE vcoms_room_config ADD COLUMN display_name TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()
    _vcoms_tables_init = True


def _coerce_timestamp(value):
    if pd.isna(value) or value is None:
        return pd.NaT
    try:
        return pd.to_datetime(value, errors="coerce")
    except Exception:
        return pd.NaT


def _parse_clock(raw_value, default_value: time) -> time:
    raw = str(raw_value or "").strip()
    if not raw:
        return default_value
    parsed = pd.to_datetime(raw, errors="coerce")
    if pd.isna(parsed):
        return default_value
    ts = pd.Timestamp(parsed)
    return time(ts.hour, ts.minute, ts.second)


def _resolve_calendar_windows(sla_cfg_map: dict | None, calendar_type: str) -> list[tuple[time, time]]:
    cfg = sla_cfg_map or {}
    prefix = "SLA" if str(calendar_type).upper() == "SLA" else "WORK"
    defaults = DEFAULT_SLA_WINDOWS if prefix == "SLA" else DEFAULT_WORK_WINDOWS
    morning_start = _parse_clock(cfg.get(f"{prefix}_MORNING_START"), defaults[0][0])
    morning_end = _parse_clock(cfg.get(f"{prefix}_MORNING_END"), defaults[0][1])
    afternoon_start = _parse_clock(cfg.get(f"{prefix}_AFTERNOON_START"), defaults[1][0])
    afternoon_end = _parse_clock(cfg.get(f"{prefix}_AFTERNOON_END"), defaults[1][1])
    windows = []
    if morning_start < morning_end:
        windows.append((morning_start, morning_end))
    if afternoon_start < afternoon_end:
        windows.append((afternoon_start, afternoon_end))
    return windows or defaults


def _normalize_sla_deadline_date(start_dt, end_dt):
    start_ts = _coerce_timestamp(start_dt)
    end_ts = _coerce_timestamp(end_dt)
    if pd.isna(start_ts) or pd.isna(end_ts):
        return end_ts
    if end_ts.date() > start_ts.date():
        next_day = start_ts.date() + timedelta(days=1)
        return pd.Timestamp(datetime.combine(next_day, end_ts.time()))
    return end_ts


def calc_calendar_elapsed_mins(start_dt, end_dt, sla_cfg_map: dict | None = None, calendar_type: str = "WORK", normalize_sla_deadline: bool = False):
    start_ts = _coerce_timestamp(start_dt)
    end_ts = _coerce_timestamp(end_dt)
    if pd.isna(start_ts) or pd.isna(end_ts):
        return 0
    if normalize_sla_deadline:
        end_ts = _normalize_sla_deadline_date(start_ts, end_ts)
    if start_ts >= end_ts:
        return 0
    current = pd.Timestamp(start_ts).to_pydatetime()
    end_value = pd.Timestamp(end_ts).to_pydatetime()
    mins = 0
    windows = _resolve_calendar_windows(sla_cfg_map, calendar_type)
    while current < end_value:
        current_time = current.time()
        if current.weekday() < 5 and any(window_start <= current_time < window_end for window_start, window_end in windows):
            mins += 1
        current += timedelta(minutes=1)
    return mins


def calc_real_elapsed_mins(start_dt, end_dt, sla_cfg_map: dict | None = None):
    return calc_calendar_elapsed_mins(start_dt, end_dt, sla_cfg_map=sla_cfg_map, calendar_type="WORK")


def calc_sla_elapsed_mins(start_dt, end_dt, sla_cfg_map: dict | None = None):
    return calc_calendar_elapsed_mins(
        start_dt,
        end_dt,
        sla_cfg_map=sla_cfg_map,
        calendar_type="SLA",
        normalize_sla_deadline=True,
    )


def calculate_sla_minutes_common(arrival_time, sla_deadline, flow_type, sla_cfg_map: dict | None = None):
    flow_up = str(flow_type or "").upper()
    cfg = sla_cfg_map or {}
    if "LC" in flow_up:
        try:
            return float(cfg.get("LC_SLA", 60.0))
        except Exception:
            return 60.0
    if "BL" in flow_up or "BẢO LÃNH" in flow_up or "BAO LANH" in flow_up:
        try:
            return float(cfg.get("BL_SLA", 60.0))
        except Exception:
            return 60.0

    try:
        o2_max = float(cfg.get("O2", 180.0))
    except Exception:
        o2_max = 180.0
    try:
        o1_max = float(cfg.get("O1", 45.0))
    except Exception:
        o1_max = 45.0

    if not arrival_time or pd.isna(arrival_time) or not sla_deadline or pd.isna(sla_deadline):
        return o1_max if flow_up == "GN_ONLINE_KHCN" else o2_max

    diff_mins = calc_sla_elapsed_mins(arrival_time, sla_deadline, cfg)
    if flow_up == "GN_ONLINE_KHCN":
        return float(min(diff_mins, o1_max))
    return float(min(diff_mins, o2_max))


def parse_excel_datetime(value):
    if pd.isna(value) or not value:
        return pd.NaT
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value)
    try:
        return pd.to_datetime(value, errors="coerce")
    except Exception:
        return pd.NaT


def _ensure_manual_actions_table(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vcoms_manual_case_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, case_key TEXT, business_date TEXT, cif TEXT, ma_ho_so TEXT, amount REAL,
            flow_type TEXT, action_type TEXT, action_time TEXT, action_by TEXT, note TEXT, created_at TEXT, is_active INTEGER DEFAULT 1
        )
    """
    )
