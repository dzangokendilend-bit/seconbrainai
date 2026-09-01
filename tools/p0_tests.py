# -*- coding: utf-8 -*-
"""tools/p0_tests.py — тесты P0 Production Readiness (stdlib unittest).

Запуск:  python tools/p0_tests.py
Часть тестов — HTTP против запущенного сервера (127.0.0.1:8900);
если сервер не запущен, они помечаются skip (unit-тесты выполняются всегда).
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import config  # noqa: E402

BASE = "http://127.0.0.1:%d" % config.PORT
PY = sys.executable


def run_py(code, env_extra=None, cwd=None):
    """python -c в окружении с MONICA_* переменными; возвращает (code, out)."""
    env = dict(os.environ)
    env.update(env_extra or {})
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([PY, "-c", code], capture_output=True, text=True,
                       env=env, cwd=cwd or ROOT, timeout=120)
    return p.returncode, p.stdout + p.stderr


def server_up():
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=2):
            return True
    except Exception:
        return False


class TestSecretsLayer(unittest.TestCase):
    def test_env_override_machine_secret(self):
        """Секрет из env виден серверу (config.MACHINE_SECRET)."""
        rc, out = run_py(
            "import sys;sys.path.insert(0,'app');import config;"
            "print(config.MACHINE_SECRET)",
            {"MONICA_MACHINE_SECRET": "env-secret-value-123"})
        self.assertEqual(rc, 0)
        self.assertIn("env-secret-value-123", out)

    def test_dotenv_parser(self):
        d = config.parse_dotenv(
            "# comment\nA=1\nB = \"quoted value\" \nC=\nD='x y'\n")
        self.assertEqual(d, {"A": "1", "B": "quoted value", "D": "x y"})

    def test_env_priority_over_dotenv(self):
        """env приоритетнее .env: env('PORT') перекрывает значение .env."""
        self.assertEqual(config.env("P0_TEST_VAR", "fallback"), "fallback")
        os.environ["P0_TEST_VAR"] = "from-env"
        try:
            self.assertEqual(config.env("P0_TEST_VAR", "fallback"), "from-env")
        finally:
            del os.environ["P0_TEST_VAR"]

    def test_data_dir_validation_rejects_root(self):
        saved = config.DATA_DIR
        try:
            config.DATA_DIR = config.ROOT
            self.assertIsNotNone(config.data_dir_problem())
            config.DATA_DIR = os.path.join(config.ROOT, "app")
            self.assertIsNotNone(config.data_dir_problem())
        finally:
            config.DATA_DIR = saved

    def test_monica_data_dir_changes_storage(self):
        """MONICA_DATA_DIR меняет mutable storage (временная директория)."""
        with tempfile.TemporaryDirectory() as td:
            rc, out = run_py(
                "import sys;sys.path.insert(0,'app');import config,os;"
                "print(config.DATA_DIR);print(os.path.isdir(config.DATA_DIR))",
                {"MONICA_DATA_DIR": td})
            self.assertEqual(rc, 0)
            self.assertIn(td, out)
            self.assertIn("True", out)


class TestProviders(unittest.TestCase):
    def test_mock_mode_never_calls_real_provider(self):
        """mock_llm=true: реальный провайдер не вызывается (urlopen сломан)."""
        import providers
        saved = config.CFG.get("mock_llm")
        config.CFG["mock_llm"] = True
        orig = __import__("urllib.request", fromlist=["urlopen"]).urlopen

        def _boom(*a, **kw):
            raise AssertionError("реальный провайдер вызван в mock-режиме")
        __import__("urllib.request", fromlist=["urlopen"]).urlopen = _boom
        try:
            reply = providers.chat("glm", None, None,
                                   [{"role": "user", "content": "привет"}])
            self.assertIn("reply", reply)
        finally:
            __import__("urllib.request", fromlist=["urlopen"]).urlopen = orig
            if saved is None:
                config.CFG.pop("mock_llm", None)
            else:
                config.CFG["mock_llm"] = saved

    def test_real_mode_without_key_raises(self):
        """real mode без ключа не запускает запрос (RuntimeError до urlopen)."""
        import providers
        saved = config.CFG.get("mock_llm")
        config.CFG["mock_llm"] = False
        try:
            with self.assertRaises(RuntimeError):
                providers.chat("glm", "", None,
                               [{"role": "user", "content": "x"}])
        finally:
            if saved is None:
                config.CFG.pop("mock_llm", None)
            else:
                config.CFG["mock_llm"] = saved

    def test_resolve_key_user_priority_and_fallback(self):
        import providers
        self.assertEqual(providers.resolve_key("user-key", "glm"), "user-key")
        saved = config.ENV_LLM_KEYS.get("glm")
        config.ENV_LLM_KEYS["glm"] = "env-fallback"
        try:
            self.assertEqual(providers.resolve_key("", "glm"), "env-fallback")
        finally:
            config.ENV_LLM_KEYS["glm"] = saved or ""


class TestDigestGate(unittest.TestCase):
    def test_digest_without_llm_flag_spends_no_tokens(self):
        """digest_llm_enabled=false (default): digest структурный, токены 0,
        даже при mock_llm=false."""
        with tempfile.TemporaryDirectory() as td:
            code = (
                "import sys,os,json;sys.path.insert(0,'app');"
                "import config,auth,jobs,budget;"
                "uid='u_p0digest';"
                "os.makedirs(auth.user_dir(uid),exist_ok=True);"
                "auth.save_profile(uid,{'user_id':uid,'username':'p0',"
                "'onboarding':{'prefs':{'digest_enabled':True}},'modules':{}});"
                "config.CFG['mock_llm']=False;"
                "rel,processed,tokens=jobs._generate_digest(uid,'2026-09-01',[]);"
                "st=budget.status(uid);"
                "print('RESULT',tokens,st['used_total'])")
            rc, out = run_py(code, {"MONICA_DATA_DIR": td})
            self.assertEqual(rc, 0, out)
            self.assertIn("RESULT 0 0", out)


class TestMigration(unittest.TestCase):
    def test_migrate_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as src, \
                tempfile.TemporaryDirectory() as dstroot:
            os.makedirs(os.path.join(src, "users", "u1"))
            with open(os.path.join(src, "users", "u1", "profile.json"),
                      "w", encoding="utf-8") as f:
                f.write("{}")
            target = os.path.join(dstroot, "newdata")
            rc, out = run_py(
                "import sys;sys.path.insert(0,'tools');"
                "sys.argv=['migrate_data.py','--to',r'" + target +
                "','--dry-run'];"
                "import runpy;runpy.run_path('tools/migrate_data.py',"
                "run_name='__main__')",
                {"MONICA_DATA_DIR": src})
            self.assertEqual(rc, 0, out)
            self.assertFalse(os.path.exists(target))
            self.assertIn("DRY-RUN", out)


class TestBackupRestore(unittest.TestCase):
    def _make_data(self, td):
        udir = os.path.join(td, "users", "u_p0")
        os.makedirs(os.path.join(udir, "vault"))
        with open(os.path.join(udir, "profile.json"), "w",
                  encoding="utf-8") as f:
            f.write('{"username": "p0"}')
        with open(os.path.join(udir, "keys.enc"), "wb") as f:
            f.write(b"\x01" * 48)
        os.makedirs(os.path.join(td, "telegram"))
        with open(os.path.join(td, "telegram", "links.json"), "w",
                  encoding="utf-8") as f:
            f.write("{}")
        # маркер-секрет, который НЕ должен попасть в архив
        with open(os.path.join(td, "users", "u_p0", "vault",
                               "note.md"), "w", encoding="utf-8") as f:
            f.write("заметка без секретов")

    def _backup(self, td, outdir):
        rc, out = run_py(
            "import sys;sys.argv=['backup_restore.py','backup','--out',r'"
            + outdir + "','--keep','3'];"
            "import runpy;runpy.run_path('tools/backup_restore.py',"
            "run_name='__main__')",
            {"MONICA_DATA_DIR": td})
        return rc, out

    def _find_zip(self, outdir):
        return os.path.join(outdir, sorted(
            f for f in os.listdir(outdir)
            if f.startswith("monica_backup_") and f.endswith(".zip"))[-1])

    def test_backup_manifest_checksum_and_no_secrets(self):
        with tempfile.TemporaryDirectory() as td, \
                tempfile.TemporaryDirectory() as outdir:
            self._make_data(td)
            rc, out = self._backup(td, outdir)
            self.assertEqual(rc, 0, out)
            zp = self._find_zip(outdir)
            with zipfile.ZipFile(zp) as z:
                names = z.namelist()
                m = json.loads(z.read("manifest.json").decode("utf-8"))
            # секретные файлы окружения не попадают в архив
            self.assertNotIn(".env", names)
            self.assertNotIn("config.json", names)
            self.assertFalse(any(n.endswith(".lock") or n.endswith(".tmp")
                                 for n in names))
            # manifest: формат, области, checksum каждого файла
            self.assertEqual(m["format"], "monica-backup")
            self.assertIn("users", m["areas"])
            self.assertTrue(any(f["path"].endswith("keys.enc")
                                for f in m["files"]))
            for f in m["files"]:
                self.assertEqual(len(f["sha256"]), 64)
            # checksum корректен
            with zipfile.ZipFile(zp) as z:
                for f in m["files"]:
                    h = hashlib.sha256(z.read(f["path"])).hexdigest()
                    self.assertEqual(h, f["sha256"])

    def test_restore_dry_run_changes_nothing(self):
        import backup_restore
        with tempfile.TemporaryDirectory() as td, \
                tempfile.TemporaryDirectory() as outdir, \
                tempfile.TemporaryDirectory() as dstroot:
            self._make_data(td)
            rc, out = self._backup(td, outdir)
            self.assertEqual(rc, 0, out)
            zp = self._find_zip(outdir)
            target = os.path.join(dstroot, "restored")
            rc, out = run_py(
                "import sys;sys.argv=['backup_restore.py','restore',r'" + zp +
                "','--to',r'" + target + "','--dry-run'];"
                "import runpy;runpy.run_path('tools/backup_restore.py',"
                "run_name='__main__')")
            self.assertEqual(rc, 0, out)
            self.assertFalse(os.path.exists(target))
            self.assertIn("DRY-RUN", out)

    def test_restore_only_into_new_dir(self):
        with tempfile.TemporaryDirectory() as td, \
                tempfile.TemporaryDirectory() as outdir, \
                tempfile.TemporaryDirectory() as dstroot:
            self._make_data(td)
            rc, _ = self._backup(td, outdir)
            self.assertEqual(rc, 0)
            zp = self._find_zip(outdir)
            # непустая директория → отказ
            target = os.path.join(dstroot, "notempty")
            os.makedirs(target)
            with open(os.path.join(target, "x.txt"), "w") as f:
                f.write("x")
            rc, out = run_py(
                "import sys;sys.argv=['backup_restore.py','restore',r'" + zp +
                "','--to',r'" + target + "','--yes'];"
                "import runpy;runpy.run_path('tools/backup_restore.py',"
                "run_name='__main__')")
            self.assertEqual(rc, 2, out)
            # пустая директория → успех, содержимое совпадает
            target2 = os.path.join(dstroot, "restored")
            rc, out = run_py(
                "import sys;sys.argv=['backup_restore.py','restore',r'" + zp +
                "','--to',r'" + target2 + "','--yes'];"
                "import runpy;runpy.run_path('tools/backup_restore.py',"
                "run_name='__main__')",
                {"MONICA_DATA_DIR": td})
            self.assertEqual(rc, 0, out)
            self.assertTrue(os.path.exists(os.path.join(
                target2, "users", "u_p0", "keys.enc")))


class TestDoctor(unittest.TestCase):
    def test_doctor_hides_secrets(self):
        token = "SUPERSECRET-TOKEN-abc123"
        rc, out = run_py("import runpy;runpy.run_path('tools/doctor.py',"
                         "run_name='__main__')",
                         {"TELEGRAM_BOT_TOKEN": token})
        self.assertNotIn(token, out)
        self.assertNotIn(token.replace("SUPERSECRET-", ""), out)
        self.assertIn("[OK]", out)

    def test_doctor_detects_polling_webhook_conflict(self):
        rc, out = run_py(
            "import runpy;runpy.run_path('tools/doctor.py',"
            "run_name='__main__')",
            {"TELEGRAM_BOT_TOKEN": "t",
             "TELEGRAM_DEV_POLLING": "1",
             "TELEGRAM_WEBHOOK_SECRET": "s",
             "PUBLIC_APP_URL": "https://example.org"})
        self.assertIn("ERROR", out)
        self.assertIn("одновременно", out)


class TestHttpEndpoints(unittest.TestCase):
    """Требуется запущенный сервер (иначе skip)."""

    def setUp(self):
        if not server_up():
            self.skipTest("сервер не запущен на " + BASE)

    def test_health_minimal_no_sensitive_data(self):
        with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
            body = r.read().decode("utf-8")
        data = json.loads(body)
        self.assertEqual(data.get("status"), "ok")
        low = body.lower()
        for marker in ("token", "secret", "machine", "key", "path",
                       str(config.DATA_DIR).lower()):
            self.assertNotIn(marker, low)

    def test_api_me_guest_has_no_secrets(self):
        with urllib.request.urlopen(BASE + "/api/me", timeout=5) as r:
            body = r.read().decode("utf-8")
        self.assertNotIn(config.MACHINE_SECRET[:12], body)
        self.assertNotIn("machine_secret", body.lower())
        self.assertNotIn(config.TG_TOKEN[:12] if config.TG_TOKEN else "§§§",
                         body)

    def test_api_tg_status_no_token(self):
        body = ""
        try:
            with urllib.request.urlopen(BASE + "/api/tg/link/status",
                                        timeout=5) as r:
                body = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            # 401 без сессии — тоже безопасно: токен не отдаётся
            body = e.read().decode("utf-8", "replace")
        if config.TG_TOKEN:
            self.assertNotIn(config.TG_TOKEN[:12], body)
        self.assertNotIn("bot_token", body.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
