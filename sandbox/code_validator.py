from __future__ import annotations

import ast
from dataclasses import dataclass, field

from sandbox.ast_rules import ALLOWED_IMPORTS, APPROVED_ROOTS, DISALLOWED_CALLS, DISALLOWED_IMPORTS


@dataclass
class CodeValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "errors": self.errors}


class GeneratedCodeValidator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.errors: list[str] = []

    def validate(self, code: str) -> CodeValidationResult:
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return CodeValidationResult(False, [f"syntax error: {exc}"])
        self.visit(tree)
        return CodeValidationResult(not self.errors, self.errors)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._check_import(node.module or "")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in DISALLOWED_CALLS:
            self.errors.append(f"disallowed call: {node.func.id}")
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in {"system", "popen", "spawn", "run", "Popen", "remove", "unlink", "rmdir"}:
                self.errors.append(f"disallowed method call: {node.func.attr}")
            if node.func.attr in {"getenv", "environ"}:
                self.errors.append("environment access is disallowed")
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            self._check_open_path(node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in {"environ", "__dict__", "__class__", "__subclasses__", "__globals__"}:
            self.errors.append(f"disallowed attribute: {node.attr}")
        self.generic_visit(node)

    def _check_import(self, module: str) -> None:
        root = module.split(".")[0]
        if root in DISALLOWED_IMPORTS:
            self.errors.append(f"disallowed import: {root}")
        elif root not in ALLOWED_IMPORTS:
            self.errors.append(f"import is not allowlisted: {root}")

    def _check_open_path(self, node: ast.Call) -> None:
        if not node.args:
            self.errors.append("open requires an explicit approved path")
            return
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            if not first.value.startswith(APPROVED_ROOTS):
                self.errors.append(f"open path is outside approved roots: {first.value}")
        else:
            self.errors.append("open path must be a literal approved sandbox path")
