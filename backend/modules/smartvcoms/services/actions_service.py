import ast
from datetime import datetime

from backend.modules.smartvcoms.utils import (
    VCOMS_DB_PATH,
    _ensure_manual_actions_table,
    connect_vcoms_sqlite,
    init_vcoms_extended_tables,
)


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
    try:
        now = datetime.now().isoformat(timespec="seconds")
        action_up = str(action_type).upper().strip()
        user = current_user.get("nameStr", "System")
        if action_up not in {"MANUAL_WAIT_DISBURSE", "MANUAL_DONE"}:
            raise ValueError(f"Unsupported action_type: {action_up}")

        conn = connect_vcoms_sqlite(VCOMS_DB_PATH)
        old = conn.execute(
            """
            SELECT business_date, cif, ma_ho_so, amount, flow_type, current_stage_code
            FROM vcoms_case_state WHERE case_key=?
            """,
            (case_key,),
        ).fetchone()
        if not old:
            conn.close()
            return {"status": "error", "message": "Không tìm thấy hồ sơ"}

        _ensure_manual_actions_table(conn)
        conn.execute(
            """
            INSERT INTO vcoms_manual_case_actions(
                case_key,business_date,cif,ma_ho_so,amount,flow_type,action_type,action_time,action_by,note,created_at,is_active
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)
            """,
            (case_key, old[0], old[1], old[2], old[3], old[4], action_up, now, user, note, now),
        )

        if action_up == "MANUAL_WAIT_DISBURSE":
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

        conn.execute(
            """
            INSERT INTO vcoms_case_audit(case_key, action, old_value, new_value, changed_by, changed_at, note)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_key,
                action_up,
                str({"current_stage_code": old[5]}),
                str({"current_stage_code": "WAIT_DISBURSE" if action_up == "MANUAL_WAIT_DISBURSE" else "DONE"}),
                user,
                now,
                note,
            ),
        )
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Cập nhật trạng thái thủ công thành công."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def remove_manual_action(case_key: str) -> dict:
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
            try:
                old_val_dict = ast.literal_eval(old_val_row[0])
                if isinstance(old_val_dict, dict):
                    stage_code = old_val_dict.get("current_stage_code", "")
                    status = old_val_dict.get("current_status", "OPEN")
                    comp_type = old_val_dict.get("completion_type", "")
                    is_open = int(old_val_dict.get("is_open", 1))
                    mapping = {
                        "ARRIVAL": "Hồ sơ đến",
                        "WAIT_ACCEPT": "Chờ tiếp nhận",
                        "PROCESSING": "Đang xử lý",
                        "WAIT_SIGN": "Chờ BGĐ ký số",
                        "WAIT_MANUAL_DONE": "Chờ hoàn tất thủ công",
                        "WAIT_DISBURSE": "Chờ giải ngân",
                        "DONE": "Hoàn thành",
                    }
                    stage_label = mapping.get(stage_code, stage_code)
                    conn.execute(
                        """
                        UPDATE vcoms_case_state
                        SET current_stage_code=?, current_stage_label=?, current_status=?, completion_type=?, is_open=?
                        WHERE case_key=?
                        """,
                        (stage_code, stage_label, status, comp_type, is_open, case_key),
                    )
            except Exception:
                pass

        conn.commit()
        conn.close()
        return {"status": "success", "message": "Đã hủy thao tác luân chuyển. Hồ sơ quay về luồng tự động."}
    except Exception as exc:
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
