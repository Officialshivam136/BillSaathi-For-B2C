import os
import tempfile
import unittest
import urllib.request

import db
import gui


class TestController(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "g.db")
        self.ctl = gui.ServerController(self.path, ports=(0,))  # port 0 = any free port

    def tearDown(self):
        self.ctl.stop()
        self.tmp.cleanup()

    def test_start_serve_stop(self):
        self.assertFalse(self.ctl.running)
        self.ctl.start()
        self.assertTrue(self.ctl.running and not self.ctl.attached)
        self.assertIsNotNone(self.ctl.port)
        html = urllib.request.urlopen(self.ctl.url.replace("localhost", "127.0.0.1") + "/").read().decode()
        self.assertIn("passcode", html.lower())  # first run goes to passcode setup
        self.assertTrue(gui.find_running(self.ctl.port))
        port = self.ctl.port
        self.ctl.stop()
        self.assertFalse(self.ctl.running)
        self.assertFalse(gui.find_running(port))

    def test_attaches_to_a_running_instance_instead_of_starting_another(self):
        self.ctl.start()
        second = gui.ServerController(self.path, ports=(self.ctl.port,))
        second.start()
        self.assertTrue(second.attached)
        self.assertIsNone(second.srv)
        second.stop()  # must not stop the real server
        self.assertTrue(gui.find_running(self.ctl.port))

    def test_skips_busy_port_and_errors_when_none_free(self):
        import http.server
        blocker = http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
        try:
            busy = blocker.server_address[1]
            c = gui.ServerController(self.path, ports=(busy, 0))
            c.start()
            self.assertNotEqual(c.port, busy)
            c.stop()
            with self.assertRaises(OSError):
                gui.ServerController(self.path, ports=(busy,)).start()
        finally:
            blocker.server_close()

    def test_backup_now_never_overwrites(self):
        self.ctl.start()
        a = self.ctl.backup_now()
        self.assertTrue(os.path.exists(a))
        self.assertTrue(a.startswith(self.ctl.backup_dir))
        db.connect(a).close()  # a valid database

    def test_summary(self):
        self.assertIn("First run", self.ctl.summary())
        conn = db.connect(self.path)
        db.save_business(conn, "Shop", "Delhi")
        conn.close()
        self.assertIn("Outstanding", self.ctl.summary())

    def test_window_builds_and_refreshes(self):
        """Tk must live and die on one thread, so build the window in its own process."""
        import subprocess
        import sys
        code = (
            "import sys, gui\n"
            "try:\n"
            "    import tkinter as tk; tk.Tk().destroy()\n"
            "except Exception:\n"
            "    sys.exit(77)\n"
            "c = gui.ServerController(sys.argv[1], ports=(0,)); c.start()\n"
            "w = gui.build_window(c); w.update()\n"
            "texts = [x.cget('text') for f in w.winfo_children() for x in f.winfo_children() if x.winfo_class() == 'Label']\n"
            "ok = any('Running' in t for t in texts)\n"
            "w.destroy(); c.stop()\n"
            "sys.exit(0 if ok else 1)\n")
        r = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r)\n" % os.path.dirname(os.path.abspath(__file__)) + code,
                            self.path], capture_output=True, text=True, timeout=60)
        if r.returncode == 77:
            self.skipTest("tkinter or a display is unavailable")
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
