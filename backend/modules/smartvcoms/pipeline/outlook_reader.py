"""Outlook polling reader for SmartVCOMS shadow mode."""

from __future__ import annotations

import platform
from datetime import datetime, timedelta
from typing import Any

import pandas as pd


OUTLOOK_REQUIREMENT_MSG = (
    "Outlook COM reader requires Windows + Microsoft Outlook Classic + pywin32."
)


def is_outlook_reader_available() -> tuple[bool, str]:
    """Return availability for Outlook COM reader."""
    if platform.system().lower() != "windows":
        return False, OUTLOOK_REQUIREMENT_MSG
    try:
        import win32com.client  # noqa: F401
        import pythoncom  # noqa: F401
    except Exception:
        return False, OUTLOOK_REQUIREMENT_MSG
    return True, "available"


def _to_outlook_filter_time(dt_obj: datetime) -> str:
    # Outlook Restrict datetime format: MM/DD/YYYY HH:MM AM/PM
    return dt_obj.strftime("%m/%d/%Y %I:%M %p")


def _safe_str(v: Any) -> str:
    return str(v or "").strip()


def _recipients_to_text(mail) -> tuple[str, str, str]:
    to_text = _safe_str(getattr(mail, "To", ""))
    cc_text = _safe_str(getattr(mail, "CC", ""))
    recipients = "; ".join([x for x in [to_text, cc_text] if x]).strip("; ").strip()
    return to_text, cc_text, recipients


def _list_child_folder_names(folder) -> list[str]:
    names: list[str] = []
    try:
        children = folder.Folders
        count = int(getattr(children, "Count", 0) or 0)
        for i in range(1, count + 1):
            try:
                names.append(_safe_str(children.Item(i).Name))
            except Exception:
                continue
    except Exception:
        return []
    return names


def _list_top_level_store_names(namespace) -> list[str]:
    names: list[str] = []
    try:
        stores = namespace.Folders
        count = int(getattr(stores, "Count", 0) or 0)
        for i in range(1, count + 1):
            try:
                names.append(_safe_str(stores.Item(i).Name))
            except Exception:
                continue
    except Exception:
        return []
    return names


def _join_folder_path(folder) -> str:
    parts: list[str] = []
    cur = folder
    for _ in range(30):
        if cur is None:
            break
        name = _safe_str(getattr(cur, "Name", ""))
        if name:
            parts.append(name)
        try:
            cur = cur.Parent
        except Exception:
            break
    parts.reverse()
    return "/".join([p for p in parts if p])


def _resolve_folder(namespace, folder_path: str):
    parts = [p.strip() for p in str(folder_path).split("/") if p.strip()]
    if not parts:
        raise RuntimeError("Outlook folder path is empty.")

    default_inbox = namespace.GetDefaultFolder(6)  # olFolderInbox
    default_root = default_inbox.Parent
    requested_path = "/".join(parts)
    head = parts[0].lower()

    if head == "inbox":
        folder = default_inbox
        parts = parts[1:]
    elif head in {"root", "mailboxroot", "mailbox"}:
        folder = default_root
        parts = parts[1:]
    else:
        try:
            folder = namespace.Folders.Item(parts[0])
            parts = parts[1:]
        except Exception:
            if len(parts) == 1:
                # e.g. "VCOMS" under default mailbox root
                folder = default_root
            else:
                stores = _list_top_level_store_names(namespace)
                raise RuntimeError(
                    f"Cannot find Outlook top-level mailbox/store '{parts[0]}'. "
                    f"Requested folder_path='{requested_path}'. "
                    f"Available top-level stores={stores}"
                )

    current_path = _join_folder_path(folder)
    for token in parts:
        try:
            folder = folder.Folders.Item(token)
            current_path = _join_folder_path(folder)
        except Exception:
            children = _list_child_folder_names(folder)
            raise RuntimeError(
                f"Cannot find Outlook folder token='{token}' under path='{current_path}'. "
                f"Requested folder_path='{requested_path}'. "
                f"Available child folders={children}"
            )
    return folder, current_path


def list_outlook_folders(max_depth: int = 3) -> list[str]:
    ok, reason = is_outlook_reader_available()
    if not ok:
        raise RuntimeError(reason)

    import pythoncom
    import win32com.client

    def walk(folder, depth: int, prefix: str) -> list[str]:
        lines = [f"{prefix}{_safe_str(getattr(folder, 'Name', ''))}"]
        if depth <= 0:
            return lines
        try:
            children = folder.Folders
            count = int(getattr(children, "Count", 0) or 0)
        except Exception:
            return lines
        for i in range(1, count + 1):
            try:
                child = children.Item(i)
            except Exception:
                continue
            lines.extend(walk(child, depth - 1, prefix + "  "))
        return lines

    pythoncom.CoInitialize()
    try:
        app = win32com.client.Dispatch("Outlook.Application")
        ns = app.GetNamespace("MAPI")
        stores = ns.Folders
        count = int(getattr(stores, "Count", 0) or 0)
        lines: list[str] = []
        for i in range(1, count + 1):
            try:
                store = stores.Item(i)
            except Exception:
                continue
            lines.extend(walk(store, max_depth, ""))
        return lines
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def poll_outlook_folder(
    *,
    folder_path: str,
    since: datetime,
    max_items: int = 300,
    subject_keyword: str = "VCOMS_",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Poll one Outlook folder incrementally using Restrict (no full folder scan)."""
    ok, reason = is_outlook_reader_available()
    if not ok:
        raise RuntimeError(reason)

    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    scanned = 0
    matched = 0
    records: list[dict[str, Any]] = []
    try:
        app = win32com.client.Dispatch("Outlook.Application")
        ns = app.GetNamespace("MAPI")
        folder, resolved_path = _resolve_folder(ns, folder_path)
        items = folder.Items
        items.Sort("[ReceivedTime]", True)  # newest first

        filter_expr = f"[ReceivedTime] >= '{_to_outlook_filter_time(since)}'"
        restricted = items.Restrict(filter_expr)

        total = int(getattr(restricted, "Count", 0) or 0)
        n = min(total, max_items)
        for i in range(1, n + 1):
            mail = restricted.Item(i)
            scanned += 1
            subject = _safe_str(getattr(mail, "Subject", ""))
            if subject_keyword and subject_keyword.lower() not in subject.lower():
                continue
            sender_email = _safe_str(
                getattr(mail, "SenderEmailAddress", "")
            )
            sender_name = _safe_str(getattr(mail, "SenderName", ""))
            received = getattr(mail, "ReceivedTime", None)
            to_text, cc_text, recipients = _recipients_to_text(mail)
            body = _safe_str(getattr(mail, "Body", ""))
            entry_id = _safe_str(getattr(mail, "EntryID", ""))
            internet_message_id = _safe_str(getattr(mail, "ConversationTopic", ""))
            conversation_id = _safe_str(getattr(mail, "ConversationID", ""))
            rec = {
                "entry_id": entry_id,
                "internet_message_id": internet_message_id,
                "conversation_id": conversation_id,
                "subject": subject,
                "body": body,
                "received_time": pd.to_datetime(received).isoformat() if received else "",
                "sender_email": sender_email,
                "sender_name": sender_name,
                "to_recipients": to_text,
                "cc_recipients": cc_text,
                "recipients_text": recipients,
                "folder_path": folder_path,
                "subject_matched": True,
                "sender_matched": True,
                "source": "outlook_com",
                "is_valid": 1 if (subject and body and entry_id) else 0,
                "parse_warning": "",
            }
            matched += 1
            records.append(rec)
        records = sorted(
            records,
            key=lambda r: (
                pd.to_datetime(r.get("received_time"), errors="coerce"),
                _safe_str(r.get("entry_id")),
            ),
        )
        return records, {
            "scanned_count": scanned,
            "matched_count": matched,
            "resolved_folder_path": resolved_path,
        }
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def compute_since_from_state(
    state: dict[str, Any] | None,
    *,
    days_back: int = 1,
    overlap_minutes: int = 5,
) -> datetime:
    """Compute incremental since time with overlap window."""
    now = datetime.now()
    if state and state.get("last_received_time"):
        last = pd.to_datetime(state.get("last_received_time"), errors="coerce")
        if pd.notna(last):
            return (last.to_pydatetime() - timedelta(minutes=overlap_minutes))
    return now - timedelta(days=max(days_back, 1))
