"""AgentSeed guard engine unit tests (stdlib unittest, zero deps)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_engine as engine  # noqa: E402

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    def test_python_module_dunders_not_flagged(self):
        src = 'if __name__ == "__main__":\n    print(__file__, __doc__)\n'
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


class TestConformance(unittest.TestCase):
    def test_self_conformant(self):
        r = engine.check_plugin_conformance(PLUGIN_ROOT)
        self.assertTrue(r["ok"], r)

    def test_rejects_bad_repository_type(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "plugin.json"), "w", encoding="utf-8") as fh:
                fh.write('{"$schema":"https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",'
                         '"name":"badplugin","repository":{"type":"git","url":"x"}}')
            r = engine.check_plugin_conformance(d)
            self.assertFalse(r["ok"])
            self.assertTrue(any("repository" in e for e in r["errors"]))


class TestSandboxRun(unittest.TestCase):
    def test_runs_command(self):
        r = engine.sandbox_run(["python3", "-c", "print(6*7)"], 10)
        self.assertEqual(r["exit_code"], 0)
        self.assertIn("42", r["stdout"])

    def test_timeout_safety(self):
        r = engine.sandbox_run(["python3", "-c", "import time; time.sleep(30)"], 1)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
