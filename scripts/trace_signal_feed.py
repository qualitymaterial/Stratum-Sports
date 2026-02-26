#!/usr/bin/env python3
"""Trace likely signal feed and Discord dispatch paths in the repository.

Usage:
    python scripts/trace_signal_feed.py
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROUTE_KEYWORDS = ("/signals", "/intel", "/feed", "/opportunities", "/alerts")
DISCORD_KEYWORDS = ("discord", "webhook", "dispatch", "send_alert")
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
QUERY_CALLS = {
    "select",
    "where",
    "join",
    "outerjoin",
    "group_by",
    "order_by",
    "limit",
    "offset",
    "execute",
    "scalars",
    "scalar",
    "mappings",
}


@dataclass
class FunctionInfo:
    name: str
    lineno: int
    calls: list[str]


@dataclass
class RouteCandidate:
    module: str
    file_path: Path
    route: str
    handler_name: str
    handler_lineno: int
    service_calls: list[str]
    score: int


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        root = _call_name(node.value)
        if root:
            return f"{root}.{node.attr}"
        return node.attr
    return None


def _string_arg(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    for keyword in call.keywords:
        if keyword.arg == "path" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    return None


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if "/__pycache__/" in str(path):
            continue
        yield path


def _module_name_for_path(repo_root: Path, path: Path) -> str:
    rel = path.relative_to(repo_root / "backend")
    return ".".join(rel.with_suffix("").parts)


def _parse_imports(tree: ast.AST) -> dict[str, str]:
    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                imports[local] = alias.name
        elif isinstance(node, ast.ImportFrom):
            if not node.module:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                imports[local] = f"{node.module}.{alias.name}"
    return imports


def _parse_functions(tree: ast.AST) -> dict[str, FunctionInfo]:
    functions: dict[str, FunctionInfo] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls: list[str] = []
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            name = _call_name(inner.func)
            if not name:
                continue
            calls.append(name)
        functions[node.name] = FunctionInfo(name=node.name, lineno=node.lineno, calls=calls)
    return functions


def _resolve_service_call(call_name: str, imports: dict[str, str]) -> str | None:
    head = call_name.split(".", 1)[0]
    import_target = imports.get(head)

    if import_target:
        if import_target.startswith("app.services"):
            if "." in call_name:
                suffix = call_name.split(".", 1)[1]
                if import_target.count(".") >= 3:
                    # imported symbol already includes function leaf
                    return import_target
                return f"{import_target}.{suffix}"
            return import_target
        return None

    direct = imports.get(call_name)
    if direct and direct.startswith("app.services"):
        return direct
    return None


def _query_hints_for_service_call(
    service_call: str,
    function_index: dict[tuple[str, str], FunctionInfo],
) -> list[str]:
    if "." not in service_call:
        return []

    module_path, _, func_name = service_call.rpartition(".")
    fn = function_index.get((module_path, func_name))
    if fn is None:
        return []

    hints: set[str] = set()
    for call in fn.calls:
        leaf = call.split(".")[-1]
        if leaf in QUERY_CALLS:
            hints.add(leaf)
    return sorted(hints)


def _load_router_prefixes(repo_root: Path) -> tuple[dict[str, str], str]:
    router_path = repo_root / "backend" / "app" / "api" / "router.py"
    api_main_path = repo_root / "backend" / "app" / "main.py"
    prefixes: dict[str, str] = {}
    api_prefix = ""

    if router_path.exists():
        tree = ast.parse(router_path.read_text(encoding="utf-8"))
        imports = _parse_imports(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "include_router":
                continue
            if not node.args:
                continue
            arg0 = node.args[0]
            module_name: str | None = None
            if isinstance(arg0, ast.Attribute) and isinstance(arg0.value, ast.Name):
                imported = imports.get(arg0.value.id)
                if imported and imported.startswith("app.api.routes"):
                    if imported.count(".") >= 4:
                        module_name = ".".join(imported.split(".")[:4])
                    else:
                        module_name = imported
            if not module_name:
                continue

            route_prefix = ""
            for keyword in node.keywords:
                if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    route_prefix = keyword.value.value
                    break
            prefixes[module_name] = route_prefix

    if api_main_path.exists():
        tree = ast.parse(api_main_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "include_router":
                continue
            if not node.args:
                continue
            if not isinstance(node.args[0], ast.Name) or node.args[0].id != "api_router":
                continue
            for keyword in node.keywords:
                if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    api_prefix = keyword.value.value
                    break

    return prefixes, api_prefix


def _normalize_path(*parts: str) -> str:
    joined = "/".join(part.strip("/") for part in parts if part)
    return f"/{joined}" if joined else "/"


def main() -> int:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent
    backend_root = repo_root / "backend" / "app"

    if not backend_root.exists():
        print("Could not find backend/app from script location.", file=sys.stderr)
        return 1

    module_imports: dict[str, dict[str, str]] = {}
    module_functions: dict[str, dict[str, FunctionInfo]] = {}
    function_index: dict[tuple[str, str], FunctionInfo] = {}

    for py_file in _iter_python_files(backend_root):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        module_name = _module_name_for_path(repo_root, py_file)
        imports = _parse_imports(tree)
        functions = _parse_functions(tree)
        module_imports[module_name] = imports
        module_functions[module_name] = functions
        for fn_name, fn in functions.items():
            function_index[(module_name, fn_name)] = fn

    router_prefixes, api_prefix = _load_router_prefixes(repo_root)

    route_candidates: list[RouteCandidate] = []
    discord_hits: list[tuple[int, str]] = []

    for py_file in _iter_python_files(backend_root):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        module_name = _module_name_for_path(repo_root, py_file)
        imports = module_imports.get(module_name, {})

        for node in tree.body if isinstance(tree, ast.Module) else []:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            calls: list[str] = []
            string_literals: list[str] = []
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    name = _call_name(inner.func)
                    if name:
                        calls.append(name)
                elif isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    string_literals.append(inner.value)

            # Discord path discovery
            haystack = " ".join(
                [module_name, node.name, " ".join(calls), " ".join(string_literals)]
            ).lower()
            discord_score = sum(1 for key in DISCORD_KEYWORDS if key in haystack)
            if discord_score:
                discord_hits.append(
                    (
                        discord_score,
                        f"DISCORD: {py_file.relative_to(repo_root)}::{node.name}()",
                    )
                )

            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                if decorator.func.attr not in HTTP_METHODS:
                    continue

                route = _string_arg(decorator)
                if not route:
                    continue
                route_lc = route.lower()
                if not any(keyword in route_lc for keyword in ROUTE_KEYWORDS):
                    continue

                service_calls: set[str] = set()
                for call in calls:
                    resolved = _resolve_service_call(call, imports)
                    if resolved:
                        service_calls.add(resolved)

                keyword_hits = sum(1 for keyword in ROUTE_KEYWORDS if keyword in route_lc)
                score = keyword_hits * 3 + len(service_calls)

                route_candidates.append(
                    RouteCandidate(
                        module=module_name,
                        file_path=py_file,
                        route=route,
                        handler_name=node.name,
                        handler_lineno=node.lineno,
                        service_calls=sorted(service_calls),
                        score=score,
                    )
                )

    route_candidates.sort(key=lambda item: (item.score, item.route.count("/")), reverse=True)
    discord_hits.sort(key=lambda item: item[0], reverse=True)

    print("Likely signal feed routes:\n")
    if not route_candidates:
        print("(none found)")
    else:
        for candidate in route_candidates[:20]:
            module_prefix = router_prefixes.get(candidate.module, "")
            full_route = _normalize_path(api_prefix, module_prefix, candidate.route)
            route_part = (
                f"ROUTE: {full_route} -> "
                f"{candidate.file_path.relative_to(repo_root)}::{candidate.handler_name}()"
            )

            if not candidate.service_calls:
                print(route_part)
                continue

            service_parts: list[str] = []
            for call in candidate.service_calls[:4]:
                module_path, _, func_name = call.rpartition(".")
                if not module_path:
                    service_parts.append(call)
                    continue
                hints = _query_hints_for_service_call(call, function_index)
                if hints:
                    service_parts.append(f"{module_path}::{func_name}() [query:{','.join(hints)}]")
                else:
                    service_parts.append(f"{module_path}::{func_name}()")

            print(f"{route_part} -> {' | '.join(service_parts)}")

    print("\nDiscord dispatch candidates:\n")
    if not discord_hits:
        print("(none found)")
    else:
        seen: set[str] = set()
        for _score, line in discord_hits:
            if line in seen:
                continue
            seen.add(line)
            print(line)
            if len(seen) >= 20:
                break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
