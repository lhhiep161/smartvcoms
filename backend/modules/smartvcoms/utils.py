import os
import sqlite3
from datetime import datetime, time, timedelta

import pandas as pd

VCOMS_DB_PATH = os.getenv("VCOMS_DB_PATH", "runtime_data/smartvcoms/vcoms.db").strip()

_vcoms_tables_init = False


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


def calc_real_elapsed_mins(start_dt, end_dt):
    if pd.isna(start_dt) or pd.isna(end_dt) or start_dt >= end_dt:
        return 0
    current = start_dt
    mins = 0
    while current < end_dt:
        t = current.time()
        if ((time(8, 0) <= t < time(12, 0)) or (time(13, 0) <= t < time(19, 30))) and current.weekday() < 5:
            mins += 1
        current += timedelta(minutes=1)
    return mins


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
