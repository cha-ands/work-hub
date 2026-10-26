"""Work Hub local server.

Run:  python server.py [port] [--no-browser]
Serves index.html + trackers/, and reads/writes todos.md. Python stdlib only.
"""
import html.parser
import http.server
import json
import os
import re
import shutil
import sys
import threading
import webbrowser
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = 8765
MAX_BODY = 5 * 1024 * 1024

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "source", "track", "wbr"}
NO_TEXT_TAGS = {"script", "style", "template"}
URGENT_PREFIX = re.compile(r"^(⭐️?|!)\s*")


def nice_name(filename):
    base = os.path.splitext(filename)[0]
    return re.sub(r"[-_]+", " ", base).strip().title() or filename


def _is_done(attrs):
    classes = attrs.get("class", "").split()
    return "data-done" in attrs or "done" in classes or "checked" in attrs


class TrackerParser(html.parser.HTMLParser):
    """Pulls to-dos out of a tracker page.

    Picks up: elements with data-todo, <li> inside .todo/.todos, and
    unchecked checkboxes (text = surrounding label or parent element).
    """

    def __init__(self, src, default_category):
        super().__init__(convert_charrefs=True)
        self.src = src
        self.default_category = default_category
        self.stack = []      # open elements: {tag, todo_list, category}
        self.capture = None  # current to-do being read: {depth, parts, fixed, skip, category, urgent}
        self.items = []
        self._seen = set()

    def _category(self, attrs):
        if attrs.get("data-category", "").strip():
            return attrs["data-category"].strip()
        for entry in reversed(self.stack):
            if entry["category"]:
                return entry["category"]
        return self.default_category

    def _start_capture(self, depth, attrs, preset=None):
        self.capture = {
            "depth": depth,
            "parts": [preset] if preset else [],
            "fixed": bool(preset),
            "skip": _is_done(attrs),
            "category": self._category(attrs),
            "urgent": "data-urgent" in attrs,
        }

    def _finish_capture(self):
        cap, self.capture = self.capture, None
        text = " ".join("".join(cap["parts"]).split())
        urgent = cap["urgent"]
        if URGENT_PREFIX.match(text):
            urgent = True
            text = URGENT_PREFIX.sub("", text)
        key = (cap["category"], text.lower())
        if text and not cap["skip"] and key not in self._seen:
            self._seen.add(key)
            self.items.append({"text": text, "category": cap["category"],
                               "src": self.src, "urgent": urgent})

    def _close_to(self, index):
        while len(self.stack) > index:
            self.stack.pop()
            if self.capture and self.capture["depth"] >= len(self.stack):
                self._finish_capture()

    def handle_starttag(self, tag, attr_list):
        attrs = {k: (v or "") for k, v in attr_list}

        if tag == "li":  # an unclosed <li> ends when the next one starts
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i]["tag"] in ("ul", "ol"):
                    break
                if self.stack[i]["tag"] == "li":
                    self._close_to(i)
                    break

        if tag in VOID_TAGS:
            if tag == "input" and attrs.get("type", "").lower() == "checkbox":
                if self.capture:
                    self.capture["skip"] = self.capture["skip"] or "checked" in attrs
                elif self.stack:
                    depth = len(self.stack) - 1
                    for i in range(len(self.stack) - 1, -1, -1):
                        if self.stack[i]["tag"] == "label":
                            depth = i
                            break
                    self._start_capture(depth, attrs)
            return

        classes = set(attrs.get("class", "").split())
        in_todo_list = any(e["todo_list"] for e in self.stack)
        self.stack.append({
            "tag": tag,
            "todo_list": bool(classes & {"todo", "todos"}),
            "category": attrs.get("data-category", "").strip() or None,
        })
        if self.capture:
            return
        depth = len(self.stack) - 1
        if "data-todo" in attrs:
            self._start_capture(depth, attrs, attrs["data-todo"].strip() or None)
        elif tag == "li" and in_todo_list:
            self._start_capture(depth, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                self._close_to(i)
                return

    def handle_data(self, data):
        if self.stack and self.stack[-1]["tag"] in NO_TEXT_TAGS:
            return
        if self.capture and not self.capture["fixed"]:
            self.capture["parts"].append(data)

    def close(self):
        super().close()
        self._close_to(0)


def parse_tracker(html_text, filename):
    parser = TrackerParser(filename, nice_name(filename))
    parser.feed(html_text)
    parser.close()
    return parser.items


def list_trackers(root):
    folder = os.path.join(root, "trackers")
    if not os.path.isdir(folder):
        return []
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".html", ".htm")))
    return [{"file": f, "name": nice_name(f)} for f in files]


def pull_all(root):
    items = []
    for t in list_trackers(root):
        path = os.path.join(root, "trackers", t["file"])
        with open(path, encoding="utf-8", errors="replace") as fh:
            items.extend(parse_tracker(fh.read(), t["file"]))
    return items


def read_todos(root):
    path = os.path.join(root, "todos.md")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_todos(root, text):
    path = os.path.join(root, "todos.md")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    os.replace(tmp, path)


def make_handler(root):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root, **kwargs)

        def log_message(self, *args):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _host_ok(self):
            # Blocks DNS-rebinding: only answer requests addressed to this machine.
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            return host in ("127.0.0.1", "localhost")

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_HEAD(self):
            if not self._host_ok():
                return self._send(403, '{"error":"forbidden host"}')
            super().do_HEAD()

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, '{"error":"forbidden host"}')
            path = urlparse(self.path).path
            if path == "/api/todos":
                return self._send(200, read_todos(root), "text/markdown; charset=utf-8")
            if path == "/api/trackers":
                return self._send(200, json.dumps(list_trackers(root)))
            if path == "/api/pull":
                return self._send(200, json.dumps(pull_all(root)))
            super().do_GET()

        def _origin_ok(self):
            # Browsers send Origin on writes; reject ones from other sites (CSRF).
            origin = self.headers.get("Origin")
            return origin is None or urlparse(origin).netloc == self.headers.get("Host")

        def do_PUT(self):
            if not self._host_ok() or not self._origin_ok():
                return self._send(403, '{"error":"forbidden"}')
            if urlparse(self.path).path != "/api/todos":
                return self._send(404, '{"error":"not found"}')
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._send(413, '{"error":"too large"}')
            text = self.rfile.read(length).decode("utf-8")
            write_todos(root, text)
            self._send(200, '{"ok":true}')

        do_POST = do_PUT  # navigator.sendBeacon can only POST

    return Handler


def make_server(root=HERE, port=DEFAULT_PORT):
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(root))


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    port = int(args[0]) if args else DEFAULT_PORT
    try:
        server = make_server(HERE, port)
    except OSError:
        print(f"Port {port} is busy. Work Hub may already be running: http://127.0.0.1:{port}")
        if "--no-browser" not in argv:
            webbrowser.open(f"http://127.0.0.1:{port}/")
        return 1
    url = f"http://127.0.0.1:{port}/"
    print(f"Work Hub running at {url}  (Ctrl+C to stop)")
    if "--no-browser" not in argv:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
