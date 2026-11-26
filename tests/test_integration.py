"""集成测试:HTTP 服务、模型层、CLI 三条链路各跑一遍真实路径。

单测只测规则函数;这里关心的是「接上之后还能不能正常工作」——
HTTP 真的起服务、模型返回真的按本仓 schema 解析、CLI 真的走子进程。
"""

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from jiadian import agent, llm, web
from jiadian import db as dbmod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AC = ("客厅空调挂机,2021年买的,去年还能用,今年开机半小时还是不凉,"
      "外机噪音大,出风口有异味,新机价 2900,高层壁挂")


class TestHttpLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = dbmod.Database(os.path.join(ROOT, "data", "_test_http.db"))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                        web._handler(cls.db, {"api_key": None}, True))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path):
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.port, path), timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def _post(self, path, payload):
        import urllib.error
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_page_served(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("家电", body)
        # 页面必须自己就把「先自查、安全禁忌、报修前体检」摆出来
        self.assertIn("安全禁忌", body)
        self.assertIn("报修前体检", body)

    def test_status_mock(self):
        status, body = self._get("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"mock": True, "model": None})

    def test_diagnose_numbers(self):
        status, r = self._post("/api/diagnose", {"text": AC})
        self.assertEqual(status, 200)
        self.assertEqual(r["mode"], "offline")
        self.assertEqual(r["decision"]["verdict"], "换新")
        self.assertEqual(r["estimate"]["low"], 80)
        self.assertEqual(r["estimate"]["high"], 600)
        self.assertEqual(r["residual"], 146)
        self.assertEqual(r["warranty"]["age"], 5)
        # 整机/主要部件已过保,但压缩机 10 年还在——所以整机不算「全过保」
        self.assertFalse(r["warranty"]["expired"])
        items = {i["name"]: i["active"] for i in r["warranty"]["items"]}
        self.assertFalse(items["整机保修"])
        self.assertTrue(items["压缩机/电机"])

    def test_diagnose_buy_year_override(self):
        status, r = self._post("/api/diagnose", {"text": "空调不制冷", "buy_year": "2024"})
        self.assertEqual(status, 200)
        self.assertEqual(r["purchase_year"], 2024)
        self.assertEqual(r["warranty"]["age"], 2)

    def test_diagnose_saved_to_db(self):
        status, r = self._post("/api/diagnose", {"text": "电视黑屏,新机价 3000"})
        self.assertEqual(status, 200)
        self.assertIsInstance(r["saved_id"], int)
        self.assertTrue(any(row["id"] == r["saved_id"] for row in self.db.latest(5)))

    def test_unknown_path_404(self):
        status, r = self._post("/api/nope", {})
        self.assertEqual(status, 404)
        self.assertIn("error", r)

    def test_unknown_post_path_drains_body(self):
        # 分两段发 40KB:服务端若没读完 body 就回 404 并关连接,
        # Windows 会给在途数据回 RST,客户端拿到 10053 而不是那个 404。
        import socket
        import time
        body = ('{"text": "%s"}' % ("x" * 40000)).encode("utf-8")
        s = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            s.sendall(b"POST /api/nope HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                      b"Content-Type: application/json\r\n"
                      b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n")
            time.sleep(0.05)
            s.sendall(body)
            raw = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                raw += chunk
        except OSError as e:
            self.fail("服务端没读完请求体就关连接，客户端收到 %r" % (e,))
        finally:
            s.close()
        self.assertTrue(raw.startswith(b"HTTP/1."), raw[:60])
        self.assertIn(b"404", raw.split(b"\r\n")[0])
        self.assertIn(b"not found", raw)


class FakeLLM:
    """按本仓 schema 回:{"summary": "", "risks": [], "questions": []}。"""

    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def __call__(self, messages, **kwargs):
        self.prompts.append(messages)
        return json.dumps(self.payload, ensure_ascii=False)


class TestModelLayer(unittest.TestCase):
    cfg = {"api_key": "test-key", "base_url": "http://127.0.0.1:9", "model": "fake"}

    def _run(self, payload, text=AC, force_mock=False):
        fake = FakeLLM(payload)
        with mock.patch.object(llm, "chat", fake):
            r = agent.diagnose(text, config=self.cfg, force_mock=force_mock)
        return r, fake

    def test_schema_fields(self):
        r, fake = self._run({"summary": "外机散热不好", "risks": ["继续开可能烧压缩机"],
                             "questions": ["上门费多少?"]})
        self.assertEqual(r["mode"], "model")
        self.assertEqual(r["summary"], "外机散热不好")
        self.assertEqual(r["risks"], ["继续开可能烧压缩机"])
        self.assertEqual(r["questions"], ["上门费多少?"])
        self.assertTrue(fake.prompts)

    def test_prompt_carries_local_facts(self):
        r, fake = self._run({"summary": "x", "risks": [], "questions": []})
        prompt = fake.prompts[0][1]["content"]
        self.assertIn("空调", prompt)
        self.assertIn("换新", prompt)
        self.assertIn("安全禁忌", prompt)

    def test_money_is_stripped(self):
        r, _ = self._run({"summary": "大概 600 元能修好", "risks": ["别接受 800 元报价"],
                          "questions": []})
        self.assertNotIn("600", r["summary"])
        self.assertIn("该费用", r["summary"])
        self.assertNotIn("800", r["risks"][0])

    def test_force_mock_wins_over_key(self):
        r, fake = self._run({"summary": "x"}, force_mock=True)
        self.assertEqual(r["mode"], "offline")
        self.assertFalse(fake.prompts)
        self.assertTrue(r["summary"])


class TestCliLayer(unittest.TestCase):
    def _run(self, args, stdin=None):
        return subprocess.run(
            [sys.executable, "-m", "jiadian"] + args,
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", input=stdin,
        )

    def test_diagnose_file_end_to_end(self):
        r = self._run(["--mock", "diagnose", "--file", "examples/case-02.txt"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("先走保修", r.stdout)
        self.assertIn("✅ 在保 主要部件(3 年)", r.stdout)
        self.assertIn("合计参考:300–900 元", r.stdout)

    def test_residual_none_is_explained(self):
        # 没写购机年份时残值算不出来,不能把 None 直接印给用户看
        r = self._run(["--mock", "diagnose", "--file", "examples/case-04.txt"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("残值约 算不出(缺购机年份) 元", r.stdout)
        self.assertNotIn("None", r.stdout)

    def test_missing_file_exit_2(self):
        r = self._run(["--mock", "diagnose", "--file", "examples/_not_here.txt"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("读不到文件", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_empty_text_exit_2(self):
        r = self._run(["--mock", "diagnose", "--text", "   "])
        self.assertEqual(r.returncode, 2)
        self.assertIn("没有描述", r.stderr)

    def test_json_is_machine_readable(self):
        r = self._run(["--mock", "--json", "diagnose", "--file", "examples/case-01.txt"])
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data["estimate"]["high"], 600)
        self.assertEqual(data["residual"], 146)

    def test_faults_grep(self):
        r = self._run(["faults", "--grep", "空调"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("不制冷", r.stdout)

    def test_warranty_command(self):
        r = self._run(["warranty"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("压缩机/电机:10 年", r.stdout)


if __name__ == "__main__":
    unittest.main()
