import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import server

HERE = os.path.dirname(os.path.abspath(__file__))


def texts(items):
    return [i["text"] for i in items]


class ParseTrackerTests(unittest.TestCase):
    def test_example_tracker(self):
        with open(os.path.join(HERE, "trackers", "example-project.html"), encoding="utf-8") as fh:
            items = server.parse_tracker(fh.read(), "example-project.html")
        self.assertEqual(texts(items), [
            "Draft the kickoff deck",
            "Chase sign-off from finance",
            "Book user research sessions",
            "Review vendor contract",
            "Expense the conference tickets (goes to Admin)",
            "Update the risk register",
            "Confirm launch date with marketing",
        ])
        by_text = {i["text"]: i for i in items}
        self.assertTrue(by_text["Chase sign-off from finance"]["urgent"])
        self.assertTrue(by_text["Review vendor contract"]["urgent"])
        self.assertFalse(by_text["Draft the kickoff deck"]["urgent"])
        self.assertEqual(by_text["Expense the conference tickets (goes to Admin)"]["category"], "Admin")
        self.assertEqual(by_text["Draft the kickoff deck"]["category"], "Example Project")
        self.assertTrue(all(i["src"] == "example-project.html" for i in items))

    def test_unclosed_li_and_nested_checkbox(self):
        html = """<ol class="todos" data-category="Q4">
          <li>First thing
          <li><input type=checkbox> Second <b>bold</b> thing
          <li><input type=checkbox checked> Already done
        </ol>"""
        items = server.parse_tracker(html, "x.html")
        self.assertEqual(texts(items), ["First thing", "Second bold thing"])
        self.assertTrue(all(i["category"] == "Q4" for i in items))

    def test_duplicates_and_scripts_ignored(self):
        html = """<ul class="todo"><li>Same</li><li>same</li></ul>
          <div data-todo>Thing<script>var x = "nope";</script></div>
          <div><input type="checkbox" id="a"><label for="a">Sibling label</label></div>"""
        items = server.parse_tracker(html, "x.html")
        self.assertEqual(texts(items), ["Same", "Thing", "Sibling label"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "trackers"))
        shutil.copy(os.path.join(HERE, "trackers", "example-project.html"),
                    os.path.join(self.root, "trackers"))
        self.httpd = server.make_server(self.root, 0)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.root)

    def req(self, path, method="GET", body=None, host=None, origin=None):
        r = urllib.request.Request(self.base + path, data=body, method=method)
        if host:
            r.add_header("Host", host)
        if origin:
            r.add_header("Origin", origin)
        with urllib.request.urlopen(r) as resp:
            return resp.read().decode("utf-8")

    def test_todos_round_trip_with_backup(self):
        self.assertEqual(self.req("/api/todos"), "")
        first = "## Admin\n- [ ] ⭐ Book leave  <!-- id:a1 added:2026-10-26 -->\n"
        self.req("/api/todos", "PUT", first.encode("utf-8"))
        self.assertEqual(self.req("/api/todos"), first)
        self.req("/api/todos", "PUT", b"## Empty\n")
        self.assertEqual(self.req("/api/todos"), "## Empty\n")
        with open(os.path.join(self.root, "todos.md.bak"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), first)

    def test_trackers_and_pull(self):
        self.assertEqual(json.loads(self.req("/api/trackers")),
                         [{"file": "example-project.html", "name": "Example Project"}])
        self.assertEqual(len(json.loads(self.req("/api/pull"))), 7)

    def test_foreign_host_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req("/api/todos", host="evil.example:80")
        self.assertEqual(ctx.exception.code, 403)
        ctx.exception.close()

    def test_cross_site_write_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.req("/api/todos", "POST", b"pwned", origin="https://evil.example")
        self.assertEqual(ctx.exception.code, 403)
        ctx.exception.close()
        self.assertEqual(self.req("/api/todos"), "")
        self.req("/api/todos", "POST", b"## Ok\n", origin=self.base)
        self.assertEqual(self.req("/api/todos"), "## Ok\n")


if __name__ == "__main__":
    unittest.main()
