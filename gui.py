"""BillSaathi desktop launcher: starts the server and shows a small control window. Standard library only (tkinter).

Run:  python gui.py      (or double-click BillSaathi.bat)
Closing the window stops BillSaathi.
"""
import os
import threading
import urllib.error
import urllib.request
import webbrowser

import app
import db

PORTS = tuple(range(8000, 8011))


def find_running(port):
    """True if a BillSaathi server already answers on this port (so we do not start a second one)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/login", timeout=1) as r:
            return str(r.headers.get("Server", "")).startswith("BillSaathi")
    except urllib.error.HTTPError as exc:  # a 4xx/5xx still carries headers
        return str(exc.headers.get("Server", "")).startswith("BillSaathi")
    except (urllib.error.URLError, OSError):
        return False


class ServerController:
    """Owns the HTTP server thread. No GUI code here, so it can be tested without a display."""

    def __init__(self, db_path=None, ports=PORTS):
        self.db_path = db_path or db.DB_PATH
        self.ports = ports
        self.srv = None
        self.port = None
        self.attached = False  # True when an existing BillSaathi server was found instead of starting one

    @property
    def url(self):
        return f"http://localhost:{self.port}" if self.port is not None else None

    @property
    def running(self):
        return self.srv is not None or self.attached

    def start(self):
        for port in self.ports:
            if port and find_running(port):
                self.port, self.attached = port, True
                return
            try:
                srv = app.make_server(port, self.db_path, quiet=True)
            except OSError:
                continue  # port busy with something else: try the next one
            self.srv, self.port = srv, srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            return
        raise OSError("No free port found (tried %s-%s)" % (self.ports[0], self.ports[-1]))

    def stop(self):
        if self.srv:
            self.srv.shutdown()
            self.srv.server_close()
            self.srv = None

    def backup_now(self):
        conn = db.connect(self.db_path)
        try:
            return db.backup_now(conn, self.backup_dir)
        finally:
            conn.close()

    @property
    def backup_dir(self):
        return os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "backups")

    def summary(self):
        """Small status line for the window; never raises."""
        try:
            conn = db.connect(self.db_path)
            try:
                if not db.get_business(conn):
                    return "First run: open BillSaathi to set up your business."
                d = db.dashboard(conn)
                return (f"This month: invoiced Rs {d['invoiced']}   collected Rs {d['collected']}\n"
                        f"Outstanding Rs {d['outstanding']}   overdue: {d['overdue_count']}")
            finally:
                conn.close()
        except Exception as exc:
            return f"(status unavailable: {exc})"


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    os.startfile(path) if hasattr(os, "startfile") else webbrowser.open("file://" + path)


def build_window(ctl):
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("BillSaathi")
    root.resizable(False, False)
    BG, NAVY = "#f4f6f9", "#17375e"
    root.configure(bg=BG)

    head = tk.Frame(root, bg=NAVY)
    head.pack(fill="x")
    tk.Label(head, text="BillSaathi", fg="#ffd166", bg=NAVY, font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=16, pady=(10, 0))
    tk.Label(head, text="GST billing for your shop", fg="white", bg=NAVY, font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=(0, 10))

    body = tk.Frame(root, bg=BG, padx=16, pady=12)
    body.pack(fill="both")
    status = tk.Label(body, text="", bg=BG, font=("Segoe UI", 11, "bold"), anchor="w")
    status.pack(fill="x")
    link = tk.Label(body, text="", bg=BG, fg="#0b5cad", cursor="hand2", font=("Segoe UI", 11, "underline"), anchor="w")
    link.pack(fill="x")
    link.bind("<Button-1>", lambda _e: ctl.url and webbrowser.open(ctl.url))
    info = tk.Label(body, text="", bg=BG, justify="left", anchor="w", font=("Segoe UI", 10), fg="#333")
    info.pack(fill="x", pady=(10, 8))

    def btn(parent, text, cmd, primary=False):
        return tk.Button(parent, text=text, command=cmd, relief="flat", cursor="hand2", padx=10, pady=6,
                         bg=NAVY if primary else "#e8edf3", fg="white" if primary else NAVY, font=("Segoe UI", 10))

    def do_open():
        if ctl.url:
            webbrowser.open(ctl.url)

    def do_backup():
        try:
            messagebox.showinfo("Backup done", "Saved:\n" + ctl.backup_now())
        except Exception as exc:
            messagebox.showerror("Backup failed", str(exc))

    def do_quit():
        ctl.stop()
        root.destroy()

    row1 = tk.Frame(body, bg=BG)
    row1.pack(fill="x")
    btn(row1, "Open BillSaathi", do_open, True).pack(side="left", padx=(0, 6))
    btn(row1, "Back up now", do_backup).pack(side="left", padx=(0, 6))
    btn(row1, "Backups folder", lambda: open_folder(ctl.backup_dir)).pack(side="left")
    row2 = tk.Frame(body, bg=BG)
    row2.pack(fill="x", pady=(8, 0))
    btn(row2, "Data folder", lambda: open_folder(os.path.dirname(os.path.abspath(ctl.db_path)))).pack(side="left", padx=(0, 6))
    btn(row2, "Stop and quit", do_quit).pack(side="left")
    tk.Label(body, text="Closing this window stops BillSaathi.", bg=BG, fg="#6b7280", font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 0))

    def refresh():
        if ctl.running:
            status.config(text="● Running" + (" (already open elsewhere)" if ctl.attached else ""), fg="#1a8d4b")
            link.config(text=ctl.url)
            info.config(text=ctl.summary())
        else:
            status.config(text="● Stopped", fg="#b3261e")
        root.after(5000, refresh)

    root.protocol("WM_DELETE_WINDOW", do_quit)
    refresh()
    return root


def main():
    import tkinter as tk
    from tkinter import messagebox

    ctl = ServerController()
    try:
        ctl.start()
    except OSError as exc:
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("BillSaathi", f"Could not start: {exc}")
        return
    webbrowser.open(ctl.url)
    build_window(ctl).mainloop()


if __name__ == "__main__":
    main()
