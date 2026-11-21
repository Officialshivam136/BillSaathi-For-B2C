"""Backups: list, check, restore, prune, and copy to a second folder (a USB drive, or a OneDrive / Google Drive folder that syncs).

Restoring never destroys the current data first: a 'before-restore' copy is written before anything is replaced.
"""
import datetime
import os
import re
import shutil
import sqlite3

import db

DAILY = re.compile(r"^billsaathi-\d{4}-\d{2}-\d{2}\.db$")
ANY = re.compile(r"^billsaathi-[A-Za-z0-9-]+\.db$")
KEEP_DAILY = 60


def kind_of(name):
    if DAILY.match(name):
        return "Daily"
    if name.startswith("billsaathi-before-restore-"):
        return "Before restore"
    return "Manual"


def list_backups(dirs):
    """dirs: list of (label, path). Newest first. Only files named like BillSaathi backups are listed."""
    rows = []
    for label, folder in dirs:
        if not folder or not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if ANY.match(name) and os.path.isfile(path):
                st = os.stat(path)
                rows.append({"name": name, "path": path, "where": label, "size": st.st_size, "kind": kind_of(name),
                             "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    return sorted(rows, key=lambda r: r["mtime"], reverse=True)


def check_backup(path):
    """Open a backup read-only and look inside. Returns {'ok', 'message', 'invoices', 'customers', 'version'}."""
    info = {"ok": False, "message": "", "invoices": 0, "customers": 0, "version": 0}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        info["message"] = f"Cannot open the file: {exc}"
        return info
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            info["message"] = "The file is damaged (integrity check failed)"
            return info
        info["version"] = con.execute("PRAGMA user_version").fetchone()[0]
        if info["version"] > len(db.MIGRATIONS):
            info["message"] = "This backup was made by a newer version of BillSaathi"
            return info
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"business", "customer", "invoice", "payment"} <= tables:
            info["message"] = "This is not a BillSaathi database"
            return info
        info["invoices"] = con.execute("SELECT COUNT(*) FROM invoice").fetchone()[0]
        info["customers"] = con.execute("SELECT COUNT(*) FROM customer").fetchone()[0]
        info["ok"] = True
        info["message"] = f"{info['invoices']} invoices, {info['customers']} customers"
        return info
    except sqlite3.Error as exc:
        info["message"] = f"Cannot read the file: {exc}"
        return info
    finally:
        con.close()


def restore(conn, path, backup_dir):
    """Replace the live database with the backup at path. Returns the path of the 'before-restore' safety copy."""
    info = check_backup(path)
    if not info["ok"]:
        raise ValueError(info["message"])
    safety = db.backup_now(conn, backup_dir, label="before-restore")
    src = sqlite3.connect(path)
    try:
        src.backup(conn)
    except sqlite3.OperationalError as exc:
        raise ValueError(f"The database is busy, try again in a moment ({exc})")
    finally:
        src.close()
    db.migrate(conn)  # an older backup is upgraded to the current layout
    return safety


def prune(folder, keep=KEEP_DAILY):
    """Delete the oldest *daily* backups beyond `keep`. Manual and before-restore copies are never deleted."""
    if not folder or not os.path.isdir(folder):
        return []
    daily = sorted(n for n in os.listdir(folder) if DAILY.match(n))
    gone = []
    for name in daily[:-keep] if keep else daily:
        try:
            os.remove(os.path.join(folder, name))
            gone.append(name)
        except OSError:
            pass
    return gone


def sync_extra(conn, backup_dir):
    """Copy backups that are missing from the second folder into it. Records the outcome in settings so the Backups page can show it.
    Returns the status text, or None when no second folder is set."""
    folder = db.get_setting(conn, "extra_backup_dir")
    if not folder:
        return None
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        if not os.path.isdir(folder):
            raise OSError("folder not found (is the drive plugged in?)")
        copied = 0
        for row in list_backups([("here", backup_dir)]):
            if row["kind"] == "Before restore":
                continue
            dest = os.path.join(folder, row["name"])
            if not os.path.exists(dest) or os.path.getsize(dest) != row["size"]:
                shutil.copy2(row["path"], dest)
                copied += 1
        photos = os.path.join(os.path.dirname(os.path.abspath(backup_dir)), "bill_photos")  # scanned bill photos live outside the database
        if os.path.isdir(photos):
            dest_photos = os.path.join(folder, "bill_photos")
            os.makedirs(dest_photos, exist_ok=True)
            for name in os.listdir(photos):
                src = os.path.join(photos, name)
                if os.path.isfile(src) and not os.path.exists(os.path.join(dest_photos, name)):
                    shutil.copy2(src, os.path.join(dest_photos, name))
                    copied += 1
        prune(folder)
        status = f"OK at {stamp}: {copied} file(s) copied"
    except OSError as exc:
        status = f"FAILED at {stamp}: {exc}"
    db.set_setting(conn, "extra_backup_status", status)
    return status


def set_extra_dir(conn, folder):
    """Save the second backup folder. It must exist and be writable."""
    folder = (folder or "").strip().strip('"')
    if not folder:
        conn.execute("DELETE FROM settings WHERE key IN ('extra_backup_dir', 'extra_backup_status')")
        return ""
    if not os.path.isdir(folder):
        raise ValueError("That folder does not exist")
    probe = os.path.join(folder, ".billsaathi-write-test")
    try:
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
    except OSError as exc:
        raise ValueError(f"Cannot write to that folder: {exc}")
    db.set_setting(conn, "extra_backup_dir", folder)
    return folder
