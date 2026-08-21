"""AgentSeed guard engine unit tests (stdlib unittest, zero deps)."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_engine as engine  # noqa: E402

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# sys.executable works on every platform; the literal "python3" does not
# exist on many Windows installs (the WindowsApps alias is a Store stub).
PY = sys.executable


class TestUndefinedSymbols(unittest.TestCase):
    def test_catches_hallucinated_call(self):
        r = engine.detect_undefined_symbols("def f():\n    return magic_unknown()\n")
        self.assertIn("magic_unknown", r["suspects"])

    def test_clean_code_passes(self):
        r = engine.detect_undefined_symbols("import math\nprint(math.sqrt(4))\n")
        self.assertEqual(r["suspects"], [])

    def test_syntax_error_reported(self):
        r = engine.detect_undefined_symbols("def f(:\n")
        self.assertEqual(r["suspects"], [])
        self.assertIn("syntax", r["note"])

    def test_ts_catches_hallucinated_call(self):
        src = "import fs from 'fs';\nfunction read(path) { return fs.readFileSync(path); }\nreadFile('../x');\n"
        r = engine.detect_undefined_symbols(src, "typescript")
        self.assertIn("readFile", r["suspects"])

    def test_ts_clean_imports(self):
        src = "import { join } from 'path';\nimport fs from 'fs';\nconsole.log(join('a', 'b'));\nfs.readFileSync('x');\n"
        r = engine.detect_undefined_symbols(src, "typescript")
        self.assertEqual(r["suspects"], [])

    def test_ts_keywords_not_flagged(self):
        src = "function f(x: number) {\n  if (x > 0) return x;\n  return 0;\n}\n"
        r = engine.detect_undefined_symbols(src, "typescript")
        self.assertEqual(r["suspects"], [])

    def test_ts_call_args_are_not_definitions(self):
        # `wrap(helper)` must not define `helper`; `helper()` must be flagged
        src = "helper();\nwrap(helper);\n"
        r = engine.detect_undefined_symbols(src, "typescript")
        self.assertIn("helper", r["suspects"])
        self.assertIn("wrap", r["suspects"])

    def test_ts_multi_declaration_collected(self):
        src = "const a = 1, b = 2;\nconsole.log(a + b);\n"
        r = engine.detect_undefined_symbols(src, "typescript")
        self.assertEqual(r["suspects"], [])

    def test_python_module_dunders_not_flagged(self):
        src = 'if __name__ == "__main__":\n    print(__file__, __doc__)\n'
        r = engine.detect_undefined_symbols(src, "python")
        self.assertEqual(r["suspects"], [])

    def test_python_local_assignment_not_flagged(self):
        src = "def f():\n    total = len([1, 2])\n    return total\n"
        r = engine.detect_undefined_symbols(src, "python")
        self.assertEqual(r["suspects"], [])

    def test_python_for_with_except_targets_not_flagged(self):
        src = (
            "def f(items, path):\n"
            "    out = []\n"
            "    for it in items:\n"
            "        out.append(it)\n"
            "    try:\n"
            "        with open(path) as fh:\n"
            "            out.append(fh.read())\n"
            "    except OSError as exc:\n"
            "        out.append(str(exc))\n"
            "    return out\n"
        )
        r = engine.detect_undefined_symbols(src, "python")
        self.assertEqual(r["suspects"], [])

    def test_python_walrus_and_augassign_not_flagged(self):
        src = "def f(n):\n    count = 0\n    count += n\n    if (big := count * 2) > 10:\n        return big\n    return count\n"
        r = engine.detect_undefined_symbols(src, "python")
        self.assertEqual(r["suspects"], [])

    def test_python_comprehension_and_global_not_flagged(self):
        src = (
            "counter = 0\n"
            "def f(vals):\n"
            "    global counter\n"
            "    counter += 1\n"
            "    return [v * 2 for v in vals]\n"
        )
        r = engine.detect_undefined_symbols(src, "python")
        self.assertEqual(r["suspects"], [])


class TestHallucinationScan(unittest.TestCase):
    def test_stub_group(self):
        r = engine.scan_hallucination_words("def run():\n    return stub_result  # TODO\n")
        self.assertFalse(r["clean"])
        groups = {h["group"] for h in r["hits"]}
        self.assertIn("stub_code", groups)

    def test_oversold_group(self):
        r = engine.scan_hallucination_words("The feature is production ready, all tests pass.")
        self.assertFalse(r["clean"])
        groups = {h["group"] for h in r["hits"]}
        self.assertIn("oversold", groups)

    def test_fabricated_group(self):
        r = engine.scan_hallucination_words("this is a simulated example")
        self.assertFalse(r["clean"])
        groups = {h["group"] for h in r["hits"]}
        self.assertIn("fabricated", groups)

    def test_clean(self):
        r = engine.scan_hallucination_words("import os\nprint(os.getcwd())\n")
        self.assertTrue(r["clean"])

    def test_unittest_mock_not_flagged(self):
        src = "from unittest.mock import Mock\nm = Mock()\nm.fake_method.return_value = 1\n"
        r = engine.scan_hallucination_words(src)
        self.assertTrue(r["clean"], r["hits"])

    def test_dotted_path_not_flagged(self):
        r = engine.scan_hallucination_words("import unittest.mock\nresult = unittest.mock.call(x)\n")
        self.assertTrue(r["clean"], r["hits"])

    def test_real_stub_still_flagged(self):
        src = "def run():\n    return stub_result  # TODO: replace with real call\n"
        r = engine.scan_hallucination_words(src)
        self.assertFalse(r["clean"])

    def test_allowlist_override(self):
        src = "m = Mock()\nthis is a fake thing\n"
        strict = engine.scan_hallucination_words(src, allowlist=[])
        self.assertFalse(strict["clean"])
        relaxed = engine.scan_hallucination_words(src)
        self.assertTrue(any(h["word"] == "fake" for h in relaxed["hits"]))
        self.assertTrue(all(h["word"] != "mock" for h in relaxed["hits"]))

    def test_default_severities(self):
        src = "# TODO: later\nall tests pass, guaranteed\ndefinitely simulated\n"
        r = engine.scan_hallucination_words(src)
        sev_by_group = {h["group"]: h["severity"] for h in r["hits"]}
        self.assertEqual(sev_by_group["stub_code"], "warning")
        self.assertEqual(sev_by_group["oversold"], "error")
        self.assertEqual(sev_by_group["fabricated"], "error")
        self.assertTrue(r["blocking"])
        self.assertFalse(r["clean"])

    def test_severity_override_downgrades_to_info(self):
        src = "guaranteed to work\n"
        r = engine.scan_hallucination_words(src, severities={"oversold": "info"})
        self.assertEqual(r["hits"][0]["severity"], "info")
        self.assertFalse(r["blocking"])

    def test_warning_only_does_not_block(self):
        src = "# TODO: finish this section\n"
        r = engine.scan_hallucination_words(src)
        self.assertFalse(r["clean"])
        self.assertFalse(r["blocking"])


class TestConformance(unittest.TestCase):
    def test_self_conformant(self):
        r = engine.check_plugin_conformance(PLUGIN_ROOT)
        self.assertTrue(r["ok"], r)

    def test_frontmatter_with_dashes_in_body(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            skill_dir = os.path.join(d, "skills", "demo-skill")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
                fh.write("---\nname: demo-skill\ndescription: ok\n---\n\n---\nnot frontmatter\n")
            # body containing a '---' line must not corrupt the parse
            r = engine.check_plugin_conformance(d)
            self.assertEqual(
                [e for e in r["errors"] if "demo-skill" in e], [], r["errors"]
            )

    def test_rejects_bad_repository_type(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "plugin.json"), "w", encoding="utf-8") as fh:
                fh.write('{"$schema":"https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",'
                         '"name":"badplugin","repository":{"type":"git","url":"x"}}')
            r = engine.check_plugin_conformance(d)
            self.assertFalse(r["ok"])
            self.assertTrue(any("repository" in e for e in r["errors"]))

    @staticmethod
    def _write_plugin(tmp, plugin_json, mcp_json):
        with open(os.path.join(tmp, "plugin.json"), "w", encoding="utf-8") as fh:
            fh.write(plugin_json)
        with open(os.path.join(tmp, "mcp.json"), "w", encoding="utf-8") as fh:
            fh.write(mcp_json)

    PJ = ('{"$schema":"https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",'
          '"name":"t"}')
    MJ = ('{"$schema":"https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",'
          '"mcpServers":{"s":%s}}')

    def test_mcp_unknown_field_in_variant(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            # 'url' belongs to the http variants, not stdio
            self._write_plugin(d, self.PJ, self.MJ % '{"type":"stdio","command":"srv","url":"https://x"}')
            r = engine.check_plugin_conformance(d)
            self.assertFalse(r["ok"])
            self.assertTrue(any("unknown field 'url'" in e for e in r["errors"]))

    def test_mcp_reserved_env_keys(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._write_plugin(d, self.PJ,
                               self.MJ % '{"type":"stdio","command":"srv","env":{"PLUGIN_DATA":"/x"}}')
            r = engine.check_plugin_conformance(d)
            self.assertFalse(r["ok"])
            self.assertTrue(any("reserved" in e for e in r["errors"]))

    def test_mcp_http_non_loopback_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._write_plugin(d, self.PJ, self.MJ % '{"type":"streamable-http","url":"http://example.com/mcp"}')
            r = engine.check_plugin_conformance(d)
            self.assertFalse(r["ok"])
            self.assertTrue(any("HTTPS" in e for e in r["errors"]))

    def test_mcp_loopback_http_allowed_and_fragment_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._write_plugin(d, self.PJ, self.MJ % '{"type":"sse","url":"http://localhost:3000/sse#frag"}')
            r = engine.check_plugin_conformance(d)
            self.assertFalse(r["ok"])
            self.assertFalse(any("HTTPS" in e for e in r["errors"]))
            self.assertTrue(any("fragment" in e for e in r["errors"]))

    def test_mcp_valid_remote_entry_passes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._write_plugin(
                d, self.PJ,
                self.MJ % '{"type":"streamable-http","url":"https://api.example.com/mcp",'
                          '"headers":{"X-Tenant":"public"}}')
            r = engine.check_plugin_conformance(d)
            self.assertEqual([e for e in r["errors"] if "mcp.json" in e], [], r["errors"])


class TestSandboxRun(unittest.TestCase):
    def test_runs_command(self):
        r = engine.sandbox_run([PY, "-c", "print(6*7)"], 10)
        self.assertEqual(r["exit_code"], 0)
        self.assertIn("42", r["stdout"])

    def test_timeout_safety(self):
        r = engine.sandbox_run([PY, "-c", "import time; time.sleep(30)"], 1)
        self.assertTrue(r["timed_out"])


class TestSchemaValidate(unittest.TestCase):
    def test_valid(self):
        schema = {"type": "object", "required": ["name"],
                  "properties": {"name": {"type": "string"}}}
        r = engine.schema_validate({"name": "agentseed"}, schema)
        self.assertTrue(r["valid"])

    def test_invalid(self):
        schema = {"type": "object", "required": ["name"],
                  "properties": {"name": {"type": "string"}}}
        r = engine.schema_validate({"name": 123}, schema)
        self.assertFalse(r["valid"])
        self.assertTrue(any("name" in e for e in r["errors"]))

    def test_required_without_properties(self):
        schema = {"type": "object", "required": ["name"]}
        r = engine.schema_validate({}, schema)
        self.assertFalse(r["valid"])
        self.assertTrue(any("name" in e for e in r["errors"]))

    def test_const_null_validated(self):
        r = engine.schema_validate(None, {"const": None})
        self.assertTrue(r["valid"])
        r = engine.schema_validate("x", {"const": None})
        self.assertFalse(r["valid"])

    def test_enum_bool_not_equal_int(self):
        r = engine.schema_validate(False, {"enum": [0]})
        self.assertFalse(r["valid"])
        r = engine.schema_validate(True, {"enum": [1]})
        self.assertFalse(r["valid"])
        r = engine.schema_validate(0, {"enum": [0]})
        self.assertTrue(r["valid"])

    def test_type_array(self):
        schema = {"type": ["string", "null"]}
        self.assertTrue(engine.schema_validate(None, schema)["valid"])
        self.assertTrue(engine.schema_validate("s", schema)["valid"])
        r = engine.schema_validate(5, schema)
        self.assertFalse(r["valid"])
        self.assertTrue(any("expected type" in e for e in r["errors"]))


class TestConfig(unittest.TestCase):
    def test_load_config_missing_returns_empty(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            os.chdir(d)
            try:
                self.assertEqual(engine.load_config(), {})
            finally:
                os.chdir(old)

    def test_load_config_plugin_data(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, engine.CONFIG_FILENAME)
            with open(cfg, "w", encoding="utf-8") as fh:
                fh.write('{"severities": {"stub_code": "info"}, "timeout": 15}')
            env = {k: v for k, v in os.environ.items()
                   if k not in ("AGENTSEED_CONFIG",)}
            env["PLUGIN_DATA"] = d
            import subprocess
            out = subprocess.run(
                [sys.executable, "-c",
                 "import json, sys; sys.path.insert(0, r'%s');"
                 "import guard_engine as e; print(json.dumps(e.load_config()))" %
                 os.path.dirname(os.path.abspath(__file__))],
                capture_output=True, text=True, env=env, check=True,
            )
            self.assertEqual(json.loads(out.stdout)["timeout"], 15)

    def test_load_config_invalid_json_ignored(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            self.assertEqual(engine.load_config(bad), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
