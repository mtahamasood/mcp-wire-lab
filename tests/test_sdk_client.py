"""Phase 5 C9, C10: the SDK client speaks only through the SDK, and the SDK is pinned."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SDK = ROOT / "clients/sdk"
SERVER_LOCK = ROOT / "vendor/servers/package-lock.json"
PACKAGE = "node_modules/@modelcontextprotocol/client"
IMPORT = re.compile(
    r"""(?:\bfrom\s+|\bimport\s*\(\s*|\bimport\s+|require\s*\(\s*)["']([^"']+)["']"""
)
ALLOWED = ("@modelcontextprotocol/client", "@modelcontextprotocol/client/stdio")


class SourceTest(unittest.TestCase):
    def sources(self) -> list[Path]:
        found = sorted((SDK / "src").glob("*.ts"))
        self.assertTrue(found, "clients/sdk/src has no sources")
        return found

    def test_only_the_sdk_speaks(self) -> None:
        for path in self.sources():
            text = path.read_text(encoding="utf-8")
            name = path.name
            for target in IMPORT.findall(text):
                ok = target in ALLOWED or target.startswith("node:") or (
                    target.startswith("./") and target.endswith(".ts"))
                self.assertTrue(ok, f"{name} imports {target!r}")
            self.assertNotIn("jsonrpc", text.lower(), f"{name} has a jsonrpc literal")
            self.assertNotIn(".send(", text, f"{name} calls send")
            self.assertNotIn(".stdin", text, f"{name} touches a stream")

    def test_the_check_would_catch_a_violation(self) -> None:
        # The patterns above are the check; prove they match what they are meant to forbid.
        self.assertEqual(IMPORT.findall('import x from "zod";'), ["zod"])
        self.assertEqual(IMPORT.findall('import { a } from "node:fs";'), ["node:fs"])
        self.assertEqual(IMPORT.findall('const m = await import("evil");'), ["evil"])
        self.assertEqual(IMPORT.findall('import "side-effect";'), ["side-effect"])


class InstallTest(unittest.TestCase):
    def test_sdk_pinned_to_the_servers_tarball(self) -> None:
        package = json.loads((SDK / "package.json").read_text())
        self.assertEqual(package["dependencies"], {"@modelcontextprotocol/client": "2.3.1"})
        self.assertEqual(package["devDependencies"],
                         {"@types/node": "24.19.2", "typescript": "5.9.3"})
        self.assertIs(package["private"], True)
        self.assertEqual(package["type"], "module")
        ours = json.loads((SDK / "package-lock.json").read_text())["packages"]
        theirs = json.loads(SERVER_LOCK.read_text())["packages"]
        for name in (PACKAGE, PACKAGE.replace("client", "core"),
                     "node_modules/typescript", "node_modules/@types/node"):
            self.assertEqual(ours[name]["version"], theirs[name]["version"], name)
            self.assertEqual(ours[name]["integrity"], theirs[name]["integrity"], name)
        self.assertEqual(ours[PACKAGE]["version"], "2.3.1")

    def test_tsconfig_is_strict_and_erasable(self) -> None:
        options = json.loads((SDK / "tsconfig.json").read_text())["compilerOptions"]
        for key in ("strict", "noEmit", "erasableSyntaxOnly", "verbatimModuleSyntax",
                    "allowImportingTsExtensions", "skipLibCheck"):
            self.assertIs(options[key], True, key)
        self.assertEqual(options["module"], "nodenext")
        self.assertEqual(options["moduleResolution"], "nodenext")
        self.assertEqual(options["types"], ["node"])

    def test_bootstrap_installs_with_npm_ci_and_checks_the_version(self) -> None:
        text = (ROOT / "scripts/bootstrap.sh").read_text()
        self.assertIn("cd clients/sdk && npm ci --ignore-scripts", text)
        self.assertIn('want_sdk="2.3.1"', text)
        self.assertRegex(text, r'\[ "\$got" = "\$want_sdk" \] \|\| fail')


if __name__ == "__main__":
    unittest.main()
