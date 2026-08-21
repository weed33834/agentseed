#!/usr/bin/env node
/**
 * agentseed-mcp launcher.
 *
 * The AgentSeed server itself is Python (stdlib-only). This shim exists so
 * npm-based clients can spawn it the standard way:
 *
 *   npx agentseed-mcp
 *
 * Requires Python 3.9+ on PATH (override with the PYTHON env var).
 */
"use strict";

const { spawn } = require("child_process");
const path = require("path");

const py = process.env.PYTHON || "python3";
const server = path.join(__dirname, "..", "server", "guard_server.py");

const child = spawn(py, [server], { stdio: "inherit" });

child.on("error", (err) => {
  if (err.code === "ENOENT") {
    console.error(
      `[agentseed-mcp] Python interpreter "${py}" not found on PATH.\n` +
        `Install Python 3.9+ or set PYTHON=/path/to/python.`
    );
    process.exit(1);
  }
  throw err;
});

child.on("exit", (code) => process.exit(code == null ? 1 : code));

for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => child.kill(sig));
}
