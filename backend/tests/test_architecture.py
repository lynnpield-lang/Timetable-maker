"""04_conventions.md 2장 import 규칙 검사."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # backend/
FRONTEND = ROOT.parent / "frontend"  # 화면 코드: frontend/ui/
NETWORK_LIBS = {"requests", "httpx", "urllib", "anthropic", "openai", "aiohttp"}
NETWORK_ALLOWED = {"kkul/loader/skku_client.py", "kkul/loader/syllabus.py", "kkul/llm.py"}
ENV_ALLOWED = {"kkul/llm.py", "main.py"}


def py_files(folder: str):
    base = (FRONTEND if folder == "ui" else ROOT) / folder
    return sorted(p for p in base.rglob("*.py")) if base.exists() else []


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def rel(p: Path) -> str:
    base = FRONTEND if p.is_relative_to(FRONTEND) else ROOT
    return p.relative_to(base).as_posix()


def test_kkul_does_not_import_ui_layers():
    for p in py_files("kkul"):
        for m in imports(p):
            top = m.split(".")[0]
            assert top not in {"nicegui", "fastapi", "api", "ui"}, f"{rel(p)} imports {m}"


def test_ui_only_uses_api_service_and_schemas():
    allowed = {"api.service", "api.schemas", "api.backend", "api"}
    for p in py_files("ui"):
        for m in imports(p):
            assert not m.startswith("kkul"), f"{rel(p)} imports {m}"
            if m.startswith("api"):
                assert m in allowed, f"{rel(p)} imports {m}"


def test_network_only_in_allowed_files():
    for folder in ("kkul", "api", "ui"):
        for p in py_files(folder):
            bad = {m for m in imports(p) if m.split(".")[0] in NETWORK_LIBS}
            if bad:
                assert rel(p) in NETWORK_ALLOWED, f"{rel(p)} imports {bad}"


def test_environ_only_in_allowed_files():
    for folder in ("kkul", "api", "ui"):
        for p in py_files(folder):
            if "os.environ" in p.read_text(encoding="utf-8"):
                assert rel(p) in ENV_ALLOWED, rel(p)


def test_no_print_outside_cli_main():
    for folder in ("kkul", "api"):
        for p in py_files(folder):
            tree = ast.parse(p.read_text(encoding="utf-8"))
            mains = {
                id(n)
                for fn in ast.walk(tree)
                if isinstance(fn, ast.FunctionDef) and fn.name == "main"
                for n in ast.walk(fn)
            }
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "print"
                    and id(node) not in mains
                ):
                    raise AssertionError(f"{rel(p)}:{node.lineno} print 사용")
