"""Dynamic SQL identifiers come only from fixed lists, never from a request (security review finding 3).

Some modules build SQL with table and column names in f-strings (bound values are always parameters). This lint
reads their source and follows every value that reaches ``text(...)`` back to where it comes from. A value is
trusted only when it is a literal, a module constant, a loop or comprehension variable over trusted values, a
reviewed database-catalogue function (table names read from the database itself), or a function parameter that
every caller in the module fills with trusted values. Anything else (a request field, a query parameter, an
attribute or a call result) fails the test with the line that uses it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "backend/app/data_plane_router.py",
    "backend/app/stage3_router.py",
    "backend/app/tenant_export.py",
    "backend/app/tenant_purge.py",
)
# Functions that return table names read from the database catalogue (information_schema / pg_catalog), reviewed.
CATALOGUE = {"tenant_purge": {"tenant_tables"}, "tenant_export": {"_tables"}}
SAFE_CALLS = {"list", "tuple", "sorted", "set", "frozenset", "str"}
# A method call is trusted only when its receiver and every argument are trusted too.
SAFE_METHODS = {"items", "keys", "values", "join", "strip", "split", "upper", "lower", "format"}


class _Lint:
    def __init__(self, source: str, catalogue: set[str] = frozenset()):
        self.tree = ast.parse(source)
        self.catalogue = set(catalogue)
        self.functions = {node.name: node for node in ast.walk(self.tree) if isinstance(node, ast.FunctionDef)}
        self.constants = {
            target.id: node.value
            for node in self.tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            if isinstance(target, ast.Name)
        }
        self.parents = {child: parent for parent in ast.walk(self.tree) for child in ast.iter_child_nodes(parent)}

    def _scope(self, node) -> ast.AST:
        """The outermost function containing ``node`` (nested functions and comprehensions share its names)."""
        scope = self.tree
        while node in self.parents:
            node = self.parents[node]
            if isinstance(node, ast.FunctionDef):
                scope = node
        return scope

    def expr(self, node, scope, seen) -> bool:
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, ast.JoinedStr):
            return all(
                self.expr(part.value, scope, seen) for part in node.values if isinstance(part, ast.FormattedValue)
            )
        if isinstance(node, ast.Name):
            return self.name(node.id, scope, seen)
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return all(self.expr(item, scope, seen) for item in node.elts)
        if isinstance(node, ast.Starred):
            return self.expr(node.value, scope, seen)
        if isinstance(node, ast.Dict):
            return all(self.expr(item, scope, seen) for item in [*node.keys, *node.values] if item is not None)
        if isinstance(node, ast.IfExp):
            return self.expr(node.body, scope, seen) and self.expr(node.orelse, scope, seen)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.expr(node.left, scope, seen) and self.expr(node.right, scope, seen)
        if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            return self.expr(node.elt, scope, seen)
        if isinstance(node, ast.Call):
            args = [*node.args, *(keyword.value for keyword in node.keywords)]
            if isinstance(node.func, ast.Name) and node.func.id in self.catalogue:
                return True
            if isinstance(node.func, ast.Name) and node.func.id in SAFE_CALLS:
                return all(self.expr(arg, scope, seen) for arg in args)
            if isinstance(node.func, ast.Attribute) and node.func.attr in SAFE_METHODS:
                return self.expr(node.func.value, scope, seen) and all(self.expr(arg, scope, seen) for arg in args)
        return False  # attributes, subscripts, other calls: could carry request input

    def name(self, name: str, scope, seen) -> bool:
        key = (id(scope), name)
        if key in seen:
            return True  # already being checked further up (a loop variable fed from itself)
        seen = seen | {key}
        bindings = []
        for node in ast.walk(scope):
            if isinstance(node, (ast.For, ast.comprehension)) and name in _names(node.target):
                bindings.append(lambda node=node: self.expr(node.iter, scope, seen))
            elif isinstance(node, ast.Assign) and any(name in _names(target) for target in node.targets):
                bindings.append(lambda node=node: self.expr(node.value, scope, seen))
            elif isinstance(node, ast.AugAssign) and name in _names(node.target):
                bindings.append(lambda node=node: self.expr(node.value, scope, seen))
        if isinstance(scope, ast.FunctionDef):
            params = [arg.arg for arg in (*scope.args.posonlyargs, *scope.args.args, *scope.args.kwonlyargs)]
            if name in params:
                bindings.append(lambda: self.callers(scope, params.index(name), name, seen))
        if bindings:
            return all(check() for check in bindings)
        if name in self.constants:
            return self.expr(self.constants[name], self.tree, seen)
        return False

    def callers(self, function: ast.FunctionDef, index: int, name: str, seen) -> bool:
        calls = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == function.name
        ]
        if not calls:
            return False  # called from elsewhere: its callers are not reviewed here
        for call in calls:
            argument = next((kw.value for kw in call.keywords if kw.arg == name), None)
            if argument is None and index < len(call.args):
                argument = call.args[index]
            if argument is not None and not self.expr(argument, self._scope(call), seen):
                return False
        return True

    def violations(self) -> list[int]:
        """Lines where a value of unknown origin reaches ``text(...)``."""
        return sorted(
            node.lineno
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "text"
            and not all(self.expr(arg, self._scope(node), frozenset()) for arg in node.args)
        )


def _names(target) -> set[str]:
    """Names a target binds (``deleted[table] = ...`` binds nothing: ``table`` is only read there)."""
    return {node.id for node in ast.walk(target) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)}


@pytest.mark.parametrize("module", MODULES)
def test_every_dynamic_sql_identifier_comes_from_a_fixed_list(module):
    path = ROOT / module
    lint = _Lint(path.read_text(encoding="utf-8"), CATALOGUE.get(path.stem, set()))
    assert lint.violations() == [], f"{module}: SQL built from a value that is not a fixed list, at lines"


SAFE = """
TABLES = {"products": "products", "evidence": "evidence"}
CLAUSE = "status = 'OPEN'"
TEMPLATE = "product_version_id {}"

def _count(db, table, clause):
    return db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :t AND {clause}"))

def route(db, request):
    for name, table in TABLES.items():
        _count(db, table, CLAUSE)
        _count(db, table, TEMPLATE.format("IS NOT NULL"))
    where = " OR ".join(f"{field} ILIKE :p" for field in ("name", "title"))
    return db.execute(text(f"SELECT * FROM products WHERE {where}"), {"p": request.query_params["q"]})
"""


def test_the_lint_accepts_fixed_lists_and_bound_values():
    assert _Lint(SAFE).violations() == []


@pytest.mark.parametrize(
    "unsafe",
    [
        # A request value used as a table name.
        'def route(db, request):\n    table = request.query_params["table"]\n    db.execute(text(f"SELECT * FROM {table}"))',
        # A route parameter (filled by the request, no caller in the module).
        'def route(db, sort: str):\n    db.execute(text(f"SELECT * FROM products ORDER BY {sort}"))',
        # A helper whose caller passes request input.
        "def _rows(db, table):\n    return db.execute(text(f'SELECT * FROM {table}'))\n"
        "def route(db, payload):\n    return _rows(db, payload.table)",
        # A loop over request input.
        'def route(db, payload):\n    for column in payload.columns:\n        db.execute(text(f"SELECT {column} FROM products"))',
        # SQL text handed over whole.
        "def route(db, query: str):\n    db.execute(text(query))",
        # A fixed template filled with request input.
        'CLAUSE = "status {}"\ndef route(db, op: str):\n    db.execute(text(CLAUSE.format(op)))',
    ],
)
def test_the_lint_refuses_request_input_in_an_identifier(unsafe):
    assert _Lint(unsafe).violations(), unsafe
