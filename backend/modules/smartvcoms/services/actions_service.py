import ast
import json
from datetime import datetime

from backend.modules.smartvcoms.utils import (
    VCOMS_DB_PATH,
    _ensure_manual_actions_table,
    connect_vcoms_sqlite,
    init_vcoms_extended_tables,
)

CASE_IDENTITY_FIELDS = [
    "business_date",
    "cif",
    "ma_ho_so",
    "amount",
    "flow_type",
]

MANUAL_ACTION_SNAPSHOT_FIELDS = [
    "current_stage_code",
    "current_stage_label",
    "current_status",
    "completion_type",
    "is_open",
    "completed_time",
    "manual_completed_time",
    "manual_finish_time",
    "sign_time",
    "disbursed_time",
    "updated_at",
    "updated_by",
]

STAGE_LABEL_FALLBACK = {
    "ARRIVAL": "Hồ sơ đến",
    "WAIT_ACCEPT": "Chờ tiếp nhận",
    "PROCESSING": "Đang xử lý",
    "WAIT_SIGN": "Chờ BGĐ ký số",
    "WAIT_MANUAL_DONE": "Chờ hoàn tất thủ công",
    "WAIT_DISBURSE": "Chờ giải ngân",
    "DONE": "Hoàn thành",
}


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _table_columns(conn, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()}


def _read_case_snapshot(conn, case_key: str) -> dict | None:
    columns = _table_columns(conn, "vcoms_case_state")
    wanted_fields = [field for field in CASE_IDENTITY_FIELDS + MANUAL_ACTION_SNAPSHOT_FIELDS if field in columns]
    if not wanted_fields:
        return None
    select_sql = ", ".join(_quote_identifier(field) for field in wanted_fields)
    row = conn.execute(
        f"SELECT {select_sql} FROM vcoms_case_state WHERE case_key=?",
        (case_key,),
    ).fetchone()
    if not row:
        return None
    return dict(zip(wanted_fields, row))


def _dump_audit_value(value: dict) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _parse_audit_value(raw_value) -> dict:
    if not raw_value:
        return {}
    if isinstance(raw_value, dict):
        return raw_value
    raw_text = str(raw_value).strip()
    if not raw_text:
        return {}
    try:
        parsed = json.loads(raw_text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    try:
        parsed = ast.literal_eval(raw_text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _restore_case_state_snapshot(conn, case_key: str, snapshot: dict) -> bool:
    if not snapshot:
        return False

    columns = _table_columns(conn, "vcoms_case_state")
    restore_values = {}

    for field in MANUAL_ACTION_SNAPSHOT_FIELDS:
        if field in columns and field in snapshot:
            restore_values[field] = snapshot.get(field)

    stage_code = str(snapshot.get("current_stage_code") or "").strip()
    if stage_code and "current_stage_code" in columns:
        restore_values.setdefault("current_stage_code", stage_code)
    if stage_code and "current_stage_label" in columns:
        restore_values.setdefault("current_stage_label", STAGE_LABEL_FALLBACK.get(stage_code, stage_code))

    # Backward-compatible fallback for older audit rows that only stored current_stage_code.
    if stage_code:
        if "current_status" in columns:
            restore_values.setdefault("current_status", "OPEN")
        if "completion_type" in columns:
            restore_values.setdefault("completion_type", "")
        if "is_open" in columns:
            restore_values.setdefault("is_open", 1)

    restore_values = {field: value for field, value in restore_values.items() if field in columns}
    if not restore_values:
        return False

    assignments = ", ".join(f"{_quote_identifier(field)}=?" for field in restore_values.keys())
    conn.execute(
        f"UPDATE vcoms_case_state SET {assignments} WHERE case_key=?",
        [*restore_values.values(), case_key],
    )
    return True


def save_rule_engine_config(routing: list[dict], assignment: list[dict]) -> dict:
    try:
        init_vcoms_extended_tables(VCOMS_DB_PATH)
        conn = connect_vcoms_sqlite(VCOMS_DB_PATH)
        conn.execute("DELETE FROM vcoms_routing_rules")
        for row in routing:
            conn.execute(
                """
                INSERT INTO vcoms_routing_rules (keyword, flow_type, is_active, auto_close_at_stage)
                VALUES (?, ?, ?, ?)
                """,
                (
                    row.get("keyword", ""),
                    row.get("flow_type", ""),
                    row.get("is_active", 1),
                    row.get("auto_close_at_stage", ""),
                ),
            )

        conn.execute("DELETE FROM vcoms_assignment_rules")
        for row in assignment:
            conn.execute(
                """
                INSERT INTO vcoms_assignment_rules (flow_type, room_name, assigned_officers, is_active)
                VALUES (?, ?, ?, ?)
                """,
                (
                    row.get("flow_type", ""),
                    row.get("room_name", ""),
                    row.get("assigned_officers", ""),
                    row.get("is_active", 1),
                ),
            )

        conn.commit()
        conn.close()
        return {"status": "success", "message": "Đã cập nhật Rule Engine thành công."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def load_rule_engine_config() -> dict:
    try:
        init_vcoms_extended_tables(VCOMS_DB_PATH)
        conn = connect_vcoms_sqlite(VCOMS_DB_PATH)
        routing_rows = conn.execute(
            """
            SELECT keyword, flow_type, auto_close_at_stage, is_active
            FROM vcoms_routing_rules
            ORDER BY id
            """
        ).fetchall()
        assignment_rows = conn.execute(
            """
            SELECT flow_type, room_name, assigned_officers, is_active
            FROM vcoms_assignment_rules
            ORDER BY id
            """
        ).fetchall()
        conn.close()
        return {
            "status": "success",
            "data": {
                "routing": [
                    {
                        "keyword": row[0] or "",
                        "flow_type": row[1] or "",
                        "auto_close_at_stage": row[2] or "",
                        "is_active": row[3] if row[3] is not None else 1,
                    }
                    for row in routing_rows
                ],
                "assignment": [
                    {
                        "flow_type": row[0] or "",
                        "room_name": row[1] or "",
                        "assigned_officers": row[2] or "",
                        "is_active": row[3] if row[3] is not None else 1,
                    }
                    for row in assignment_rows
                ],
            },
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def apply_manual_action(case_key: str, action_type: str, note: str, current_user: dict) -> dict:
    conn = None
    try:
        now = datetime.now().isoformat(timespec="seconds")
        action_up = str(action_type).upper().strip()
        user = current_user.get("nameStr", "System")
        if action_up not in {"MANUAL_WAIT_DISBURSE", "MANUAL_DONE"}:
            raise ValueError(f"Unsupported action_type: {action_up}")

        conn = connect_vcoms_sqlite(VCOMS_DB_PATH)
        old_snapshot = _read_case_snapshot(conn, case_key)
        if not old_snapshot:
            conn.close()
            return {"status": "error", "message": "Không tìm thấy hồ sơ"}

        _ensure_manual_actions_table(conn)
        conn.execute(
            """
            INSERT INTO vcoms_manual_case_actions(
                case_key,business_date,cif,ma_ho_so,amount,flow_type,action_type,action_time,action_by,note,created_at,is_active
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)
            """,
            (
                case_key,
                old_snapshot.get("business_date"),
                old_snapshot.get("cif"),
                old_snapshot.get("ma_ho_so"),
                old_snapshot.get("amount"),
                old_snapshot.get("flow_type"),
                action_up,
                now,
                user,
                note,
                now,
            ),
        )

        if action_up == "MANUAL_WAIT_DISBURSE":
            next_snapshot = {
                "current_stage_code": "WAIT_DISBURSE",
                "current_stage_label": "Chờ giải ngân",
                "current_status": "OPEN",
                "is_open": 1,
                "completion_type": "",
                "updated_at": now,
                "updated_by": user,
            }
            conn.execute(
                """
                UPDATE vcoms_case_state
                SET current_stage_code='WAIT_DISBURSE', current_stage_label='Chờ giải ngân', current_status='OPEN',
                    is_open=1, completion_type='', updated_at=?, updated_by=?
                WHERE case_key=?
                """,
                (now, user, case_key),
            )
        else:
            next_snapshot = {
                "current_stage_code": "DONE",
                "current_stage_label": "Hoàn thành",
                "current_status": "CLOSED",
                "is_open": 0,
                "manual_completed_time": now,
                "manual_finish_time": now,
                "completed_time": now,
                "completion_type": "MANUAL_DONE",
                "updated_at": now,
                "updated_by": user,
            }
            conn.execute(
                """
                UPDATE vcoms_case_state
                SET current_stage_code='DONE', current_stage_label='Hoàn thành', current_status='CLOSED',
                    is_open=0, manual_completed_time=?, manual_finish_time=?, completed_time=?,
                    completion_type='MANUAL_DONE', updated_at=?, updated_by=?
                WHERE case_key=?
                """,
                (now, now, now, now, user, case_key),
            )

        audit_old_value = {field: old_snapshot.get(field) for field in MANUAL_ACTION_SNAPSHOT_FIELDS if field in old_snapshot}
        conn.execute(
            """
            INSERT INTO vcoms_case_audit(case_key, action, old_value, new_value, changed_by, changed_at, note)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_key,
                action_up,
                _dump_audit_value(audit_old_value),
                _dump_audit_value(next_snapshot),
                user,
                now,
                note,
            ),
        )
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Cập nhật trạng thái thủ công thành công."}
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return {"status": "error", "message": str(exc)}


def remove_manual_action(case_key: str) -> dict:
    conn = None
    try:
        conn = connect_vcoms_sqlite(VCOMS_DB_PATH)
        conn.execute(
            "UPDATE vcoms_manual_case_actions SET is_active = 0 WHERE case_key = ?",
            (case_key,),
        )

        old_val_row = conn.execute(
            """
            SELECT old_value FROM vcoms_case_audit
            WHERE case_key = ? AND action LIKE 'MANUAL%'
            ORDER BY id DESC LIMIT 1
            """,
            (case_key,),
        ).fetchone()
        if old_val_row and old_val_row[0]:
            old_val_dict = _parse_audit_value(old_val_row[0])
            _restore_case_state_snapshot(conn, case_key, old_val_dict)

        conn.commit()
        conn.close()
        return {"status": "success", "message": "Đã hủy thao tác luân chuyển. Hồ sơ quay về luồng tự động."}
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return {"status": "error", "message": str(exc)}


def _normalize_cb_input(manual_value: str) -> tuple[str, str]:
    raw = str(manual_value or "").strip()
    if not raw:
        return "", ""
    try:
        from ..store.config_admin import load_config_for_admin

        cb_df, _, _ = load_config_for_admin(VCOMS_DB_PATH)
        if cb_df.empty:
            return "", ""
        cb_df = cb_df.copy()
        cb_df["ID_CB"] = cb_df["ID_CB"].astype(str).str.strip()
        cb_df["Tên Cán bộ"] = cb_df["Tên Cán bộ"].astype(str).str.strip()
        hit = cb_df[cb_df["ID_CB"].str.upper() == raw.upper()]
        if hit.empty:
            hit = cb_df[cb_df["Tên Cán bộ"].str.upper() == raw.upper()]
        if hit.empty:
            return "", ""
        cb_id = str(hit.iloc[0].get("ID_CB") or "").strip()
        cb_name = str(hit.iloc[0].get("Tên Cán bộ") or "").strip()
        return cb_id, cb_name
    except Exception:
        return "", ""


def set_manual_override(case_key: str, field_name: str, manual_value: str, current_user: dict) -> dict:
    try:
        normalized_value = str(manual_value or "").strip()
        audit_note = normalized_value
        if field_name == "cb_httd":
            cb_id, cb_name = _normalize_cb_input(manual_value)
            if not cb_id:
                return {"status": "error", "message": "Không map được cán bộ sang ID_CB."}
            normalized_value = cb_id
            audit_note = f"{cb_id}{' - ' + cb_name if cb_name else ''}"

        conn = connect_vcoms_sqlite(VCOMS_DB_PATH)
        conn.execute(
            "DELETE FROM vcoms_manual_overrides WHERE case_key = ? AND field_name = ?",
            (case_key, field_name),
        )
        now = datetime.now().isoformat(timespec="seconds")
        user = current_user.get("nameStr", "System")
        conn.execute(
            """
            INSERT INTO vcoms_manual_overrides (case_key, field_name, manual_value, created_by, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (case_key, field_name, normalized_value, user, now),
        )

        if field_name == "cb_httd":
            conn.execute(
                """
                UPDATE vcoms_case_state
                SET assigned_officer=?, updated_at=?, updated_by=?
                WHERE case_key=?
                """,
                (normalized_value, now, user, case_key),
            )
            conn.execute(
                """
                INSERT INTO vcoms_case_audit(case_key, action, old_value, new_value, changed_by, changed_at, note)
                VALUES(?, 'ADMIN_UPDATE', '', ?, ?, ?, 'Cập nhật cán bộ HTTD')
                """,
                (case_key, audit_note, user, now),
            )

        conn.commit()
        conn.close()
        return {"status": "success", "message": "Ghi đè thủ công thành công"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def delete_manual_override(case_key: str, field_name: str) -> dict:
    try:
        conn = connect_vcoms_sqlite(VCOMS_DB_PATH)
        conn.execute(
            "DELETE FROM vcoms_manual_overrides WHERE case_key = ? AND field_name = ?",
            (case_key, field_name),
        )
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Mở khóa dữ liệu thành công"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
