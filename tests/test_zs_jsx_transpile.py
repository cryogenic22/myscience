"""Guard: the buildless /zs deck JSX must still transpile in the browser.

``static/zs/zs-future-state-v2.jsx`` is transpiled IN THE BROWSER by
``static/zs/index.html`` via @babel/standalone with the automatic JSX runtime —
there is no build step, so a syntax slip (a stray brace, an unterminated tag)
ships silently and white-screens the page. This test reproduces that exact
transpile and asserts it succeeds, the default export survives, and no raw JSX
leaks into the compiled output.

It installs @babel/standalone into a throwaway temp dir (the deck is NOT a Vite
package; babel is not a repo dependency) and shells out to node. If node/npm are
genuinely unavailable the test is skipped — but it FAILS LOUDLY on a real
transpile error, an install failure, or a missing default export, so it is not a
vacuous green where a toolchain exists (CI runs Node 22).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_JSX = _REPO_ROOT / "static" / "zs" / "zs-future-state-v2.jsx"

# A CommonJS driver: transpile with the same preset the page uses, then assert
# the default export survived and no raw JSX element remains in the output.
_CHECK_JS = r"""
const fs = require("fs");
const Babel = require("@babel/standalone");
const src = fs.readFileSync(process.argv[2], "utf-8");
let out;
try {
  out = Babel.transform(src, { presets: [["react", { runtime: "automatic" }]] }).code;
} catch (e) {
  console.error("TRANSPILE_FAILED: " + e.message);
  process.exit(1);
}
if (!/ZSFutureState/.test(out) || !/export default|exports\.default/.test(out)) {
  console.error("DEFAULT_EXPORT_MISSING");
  process.exit(2);
}
if (/<\/[A-Za-z]/.test(out) || /return\s+\(?\s*</.test(out)) {
  console.error("RAW_JSX_REMAINS");
  process.exit(3);
}
console.log("TRANSPILE_OK has_jsx=" + /_jsxs?\(/.test(out));
"""


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


@pytest.mark.skipif(not (_have("node") and _have("npm")), reason="node/npm not available")
def test_zs_jsx_transpiles_with_automatic_runtime(tmp_path):
    assert _JSX.is_file(), f"missing {_JSX}"

    # Resolve full paths — on Windows `npm` is `npm.cmd`, which subprocess won't
    # find without the resolved path / shell.
    npm = shutil.which("npm")
    node = shutil.which("node")

    # install @babel/standalone into a throwaway dir (not a repo dependency)
    (tmp_path / "package.json").write_text(json.dumps({"name": "zs-jsx-check", "private": True}))
    install = subprocess.run(
        [npm, "install", "@babel/standalone@7", "--no-audit", "--no-fund", "--loglevel=error"],
        cwd=tmp_path, capture_output=True, text=True, shell=False,
    )
    assert install.returncode == 0, f"npm install failed:\n{install.stdout}\n{install.stderr}"

    check = tmp_path / "check.cjs"
    check.write_text(_CHECK_JS, encoding="utf-8")
    result = subprocess.run(
        [node, str(check), str(_JSX)],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"transpile check failed:\n{result.stdout}\n{result.stderr}"
    assert "TRANSPILE_OK" in result.stdout, result.stdout
    # the deck is JSX-heavy — the compiled output must actually contain jsx calls,
    # proving the preset ran (not a no-op pass that would mask a broken runtime)
    assert "has_jsx=true" in result.stdout, result.stdout
