"""Integration tests: verify _meta.pyi typing across type checkers.

The __getattr__ on CompositeEnumMeta in _meta.pyi makes dynamically injected
members (e.g. TokenType.UNION) visible to type checkers without generated
stubs.  These tests verify that each checker sees the correct types.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Checker infrastructure
# ---------------------------------------------------------------------------

COMPOSITE_ENUM_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class CheckerConfig:
    cmd: list[str]
    env_key: str | None = None
    success: str | None = None

    def build_cmd(self, usage_path: Path) -> list[str]:
        fmt = {"python": sys.executable, "path": str(usage_path)}
        return [tok.format(**fmt) for tok in self.cmd]

    def build_env(self, usage_path: Path) -> dict[str, str]:
        paths = f"{COMPOSITE_ENUM_ROOT}:{usage_path.parent}"
        match self.env_key:
            case "MYPYPATH":
                return {**os.environ, "MYPYPATH": paths}
            case _:
                return {**os.environ, "PYTHONPATH": paths}

    def is_clean(self, output: str, returncode: int) -> bool:
        match self.success:
            case str(pattern):
                return pattern in output
            case _:
                return returncode == 0


CHECKER_CONFIGS: dict[str, CheckerConfig] = {
    "mypy": CheckerConfig(
        cmd=["{python}", "-m", "mypy", "--strict", "--no-error-summary", "{path}"],
        env_key="MYPYPATH",
    ),
    "pyright": CheckerConfig(
        cmd=["{python}", "-m", "pyright", "--pythonpath", "{python}", "{path}"],
    ),
    "basedpyright": CheckerConfig(
        cmd=["{python}", "-m", "basedpyright", "--pythonpath", "{python}", "{path}"],
        success="0 errors",
    ),
    "pyrefly": CheckerConfig(
        cmd=["pyrefly", "check", "--preset", "strict", "{path}"],
        success="0 errors",
    ),
    "ty": CheckerConfig(
        cmd=["ty", "check", "{path}"],
    ),
}

CHECKERS = list(CHECKER_CONFIGS)


def _is_available(name: str) -> bool:
    match name:
        case "pyrefly" | "ty":
            return shutil.which(name) is not None
        case _:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", name, "--version"],
                    capture_output=True,
                    timeout=30,
                )
                return result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return False


_available: dict[str, bool] = {}


def _checker_available(name: str) -> bool:
    if name not in _available:
        _available[name] = _is_available(name)
    return _available[name]


def _skip_unless(checker: str) -> None:
    if not _checker_available(checker):
        pytest.skip(f"{checker} not installed")


def _run(checker: str, usage_path: Path) -> subprocess.CompletedProcess[str]:
    cfg = CHECKER_CONFIGS[checker]
    return subprocess.run(
        cfg.build_cmd(usage_path),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=usage_path.parent,
        env=cfg.build_env(usage_path),
    )


def _assert_clean(checker: str, usage_path: Path) -> None:
    _skip_unless(checker)
    proc = _run(checker, usage_path)
    output = proc.stdout + proc.stderr
    cfg = CHECKER_CONFIGS[checker]
    assert cfg.is_clean(output, proc.returncode), f"{checker} failed:\n{output}"


def _assert_has_error(checker: str, usage_path: Path, needle: str) -> None:
    _skip_unless(checker)
    proc = _run(checker, usage_path)
    output = proc.stdout + proc.stderr
    assert needle in output, f"{checker} should mention '{needle}':\n{output}"


# ---------------------------------------------------------------------------
# Module / script setup helpers
# ---------------------------------------------------------------------------


def _setup_module(
    tmp_path: Path,
    module_src: str,
    usage_src: str,
) -> Path:
    """Write a module and a usage file.  Returns usage_path."""
    pkg = tmp_path / "pkg"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(module_src))
    usage = tmp_path / "check_usage.py"
    usage.write_text(textwrap.dedent(usage_src))
    return usage


@pytest.fixture(scope="class")
def shared_usage(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Write module+usage files once per test class, reuse across checker params."""
    cls = request.cls
    assert cls is not None
    module_src = getattr(cls, "MODULE", None)
    usage_src = getattr(cls, "USAGE", None)
    if module_src is None or usage_src is None:
        pytest.fail(f"{cls.__name__} must define MODULE and USAGE class attrs")
    d = tmp_path_factory.mktemp(cls.__name__)
    return _setup_module(d, module_src, usage_src)


def _write_script(tmp_path: Path, code: str) -> Path:
    script = tmp_path / "check_script.py"
    script.write_text(textwrap.dedent(code))
    return script


# ---------------------------------------------------------------------------
# pyre helpers
# ---------------------------------------------------------------------------


def _setup_pyre_dir(
    tmp_path: Path,
    probe_code: str,
    *,
    include_meta_pyi: bool = True,
) -> Path:
    pyre_dir = tmp_path / "pyre_probe"
    pyre_dir.mkdir(exist_ok=True)
    script = pyre_dir / "probe.py"
    script.write_text(textwrap.dedent(probe_code))
    if include_meta_pyi:
        (pyre_dir / "composite_enum").symlink_to(
            COMPOSITE_ENUM_ROOT / "composite_enum",
        )
    else:
        ce_dir = pyre_dir / "composite_enum"
        ce_dir.mkdir()
        for f in (COMPOSITE_ENUM_ROOT / "composite_enum").iterdir():
            if f.name == "_meta.pyi":
                continue
            if f.is_file():
                shutil.copy2(f, ce_dir / f.name)
            elif f.is_dir():
                shutil.copytree(f, ce_dir / f.name)
    config = {"source_directories": ["."]}
    (pyre_dir / ".pyre_configuration").write_text(json.dumps(config))
    return script


def _run_pyre(usage_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["pyre", "check"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=usage_path.parent,
    )


def _assert_pyre_clean(usage_path: Path) -> None:
    proc = _run_pyre(usage_path)
    output = proc.stdout + proc.stderr
    real_errors = [
        ln for ln in output.splitlines() if ln.strip() and not ln.startswith("ƛ")
    ]
    assert not real_errors, f"pyre errors:\n{output}"


# ---------------------------------------------------------------------------
# pytype helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pytype_python() -> str | None:
    """Find a Python <=3.12 interpreter for pytype."""
    for minor in (12, 11, 10):
        path = shutil.which(f"python3.{minor}")
        if path:
            return path
    return None


def _has_pytype() -> bool:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytype", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _has_pyre() -> bool:
    if shutil.which("pyre") is None:
        return False
    try:
        proc = subprocess.run(
            ["pyre", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return "Client version" in (proc.stdout + proc.stderr)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_pytype(
    usage_path: Path,
    python_exe: str,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": f"{COMPOSITE_ENUM_ROOT}:{usage_path.parent}",
        "PATH": f"{Path(python_exe).parent}:{os.environ.get('PATH', '')}",
    }
    return subprocess.run(
        [sys.executable, "-m", "pytype", str(usage_path), "--python-version", "3.12"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=usage_path.parent,
        env=env,
    )


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------


MODULE_BASIC = """\
    from enum import Enum
    from composite_enum import CompositeEnum

    class Operator(Enum):
        UNION = "|"
        INTERSECT = "&"

    class TokenType(CompositeEnum, includes=Operator):
        IDENT = "IDENT"
        ASSIGN = "="
"""

USAGE_BASIC = """\
    from pkg.mod import TokenType, Operator

    u: TokenType = TokenType.UNION
    i: TokenType = TokenType.INTERSECT
    ident: TokenType = TokenType.IDENT
    assign: TokenType = TokenType.ASSIGN
    v: str = TokenType.UNION.value
    op: Operator = Operator.UNION
"""

MODULE_METHODS = """\
    from enum import Enum
    from composite_enum import CompositeEnum

    class Op(Enum):
        ADD = "+"

    class Token(CompositeEnum, includes=Op):
        NUM = "NUM"

        def is_operator(self) -> bool:
            return self.source_enum is not None

        @staticmethod
        def count() -> int:
            return 42
"""

USAGE_METHODS = """\
    from pkg.mod import Token

    t: Token = Token.ADD
    flag: bool = t.is_operator()
    n: int = Token.count()
"""

MODULE_MULTI_SOURCE = """\
    from enum import Enum
    from composite_enum import CompositeEnum

    class Ops(Enum):
        ADD = "+"
        SUB = "-"

    class Keywords(Enum):
        IF = "if"
        ELSE = "else"

    class AllTokens(CompositeEnum, includes=[Ops, Keywords]):
        IDENT = "IDENT"
"""

USAGE_MULTI_SOURCE = """\
    from pkg.mod import AllTokens

    a: AllTokens = AllTokens.ADD
    s: AllTokens = AllTokens.SUB
    i: AllTokens = AllTokens.IF
    e: AllTokens = AllTokens.ELSE
    ident: AllTokens = AllTokens.IDENT
"""

MODULE_INT_ENUM = """\
    from enum import IntEnum
    from composite_enum import CompositeEnumMeta

    class Priority(IntEnum):
        LOW = 1
        HIGH = 2

    class ExtPriority(IntEnum, metaclass=CompositeEnumMeta, includes=Priority):
        CRITICAL = 3
"""

USAGE_INT_ENUM = """\
    from pkg.mod import ExtPriority

    p: ExtPriority = ExtPriority.LOW
    h: ExtPriority = ExtPriority.HIGH
    c: ExtPriority = ExtPriority.CRITICAL
    x: int = ExtPriority.LOW + ExtPriority.HIGH
"""

MODULE_NESTED = """\
    from enum import Enum
    from composite_enum import CompositeEnum

    class Base(Enum):
        A = "a"

    class Mid(CompositeEnum, includes=Base):
        B = "b"

    class Top(CompositeEnum, includes=Mid):
        C = "c"
"""

USAGE_NESTED = """\
    from pkg.mod import Top

    a: Top = Top.A
    b: Top = Top.B
    c: Top = Top.C
"""

MODULE_MIXED_CONTENT = """\
    from enum import Enum
    from composite_enum import CompositeEnum

    VERSION: str = "1.0"

    class Color(Enum):
        RED = "red"

    class Palette(CompositeEnum, includes=Color):
        CUSTOM = "custom"

    def describe(p: Palette) -> str:
        return p.value
"""

USAGE_MIXED_CONTENT = """\
    from pkg.mod import Palette, describe, VERSION

    p: Palette = Palette.RED
    c: Palette = Palette.CUSTOM
    d: str = describe(p)
    v: str = VERSION
"""

MODULE_TUPLE_VALUES = """\
    from enum import Enum
    from composite_enum import CompositeEnum

    class Pair(Enum):
        XY = (1, 2)
        AB = ("a", "b")

    class Extended(CompositeEnum, includes=Pair):
        CD = (3, 4)
"""

USAGE_TUPLE_VALUES = """\
    from pkg.mod import Extended

    e: Extended = Extended.XY
    f: Extended = Extended.AB
    g: Extended = Extended.CD
"""

MODULE_AUTO = """\
    from enum import Enum, auto
    from composite_enum import CompositeEnum

    class Source(Enum):
        A = auto()
        B = auto()

    class Target(CompositeEnum, includes=Source):
        C = auto()
"""

USAGE_AUTO = """\
    from pkg.mod import Target

    a: Target = Target.A
    b: Target = Target.B
    c: Target = Target.C
"""


# ---------------------------------------------------------------------------
# Parametrized tests across all 5 main checkers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("checker", CHECKERS)
class TestBasicAccess:
    MODULE = MODULE_BASIC
    USAGE = USAGE_BASIC

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


@pytest.mark.parametrize("checker", CHECKERS)
class TestMethodSignatures:
    MODULE = MODULE_METHODS
    USAGE = USAGE_METHODS

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


@pytest.mark.parametrize("checker", CHECKERS)
class TestMultipleSources:
    MODULE = MODULE_MULTI_SOURCE
    USAGE = USAGE_MULTI_SOURCE

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


@pytest.mark.parametrize("checker", CHECKERS)
class TestMetaclassIntEnum:
    MODULE = MODULE_INT_ENUM
    USAGE = USAGE_INT_ENUM

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


@pytest.mark.parametrize("checker", CHECKERS)
class TestNestedComposition:
    MODULE = MODULE_NESTED
    USAGE = USAGE_NESTED

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


@pytest.mark.parametrize("checker", CHECKERS)
class TestMixedContent:
    MODULE = MODULE_MIXED_CONTENT
    USAGE = USAGE_MIXED_CONTENT

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


@pytest.mark.parametrize("checker", CHECKERS)
class TestTupleValues:
    MODULE = MODULE_TUPLE_VALUES
    USAGE = USAGE_TUPLE_VALUES

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


@pytest.mark.parametrize("checker", CHECKERS)
class TestAutoValues:
    MODULE = MODULE_AUTO
    USAGE = USAGE_AUTO

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


# ---------------------------------------------------------------------------
# _meta.pyi library API + injected members
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("checker", CHECKERS)
class TestMetaPyiTyping:
    """Library API (source_enum, to_source, etc.) plus injected members are
    all visible via _meta.pyi + __getattr__.
    """

    USAGE = """\
        from pkg.mod import TokenType, Operator
        from enum import Enum

        se: type[Enum] | None = TokenType.IDENT.source_enum
        ts: Enum | None = TokenType.IDENT.to_source()
        ie: tuple[type[Enum], ...] = TokenType.included_enums()
        mf: frozenset[TokenType] = TokenType.members_from(Operator)
        ie2: bool = TokenType.includes_enum(Operator)
        fs: TokenType | None = TokenType.from_source(Operator.UNION)
        u: TokenType = TokenType.UNION
    """

    MODULE = """\
        from enum import Enum
        from composite_enum import CompositeEnum

        class Operator(Enum):
            UNION = "|"

        class TokenType(CompositeEnum, includes=Operator):
            IDENT = "IDENT"
    """

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


# ---------------------------------------------------------------------------

REVEAL_CHECKERS = ["pyright", "mypy", "basedpyright", "ty"]
# pyrefly does not output reveal_type results, so it is excluded.


class TestMetaPyiShadowsMetaPy:
    """Verify _meta.pyi is actually being used by probing reveal_type."""

    @pytest.mark.parametrize("checker", REVEAL_CHECKERS)
    def test_source_enum_is_property(
        self,
        tmp_path: Path,
        checker: str,
    ) -> None:
        _skip_unless(checker)
        script = _write_script(
            tmp_path,
            """\
            from composite_enum import CompositeEnum
            reveal_type(CompositeEnum.source_enum)
            """,
        )
        proc = _run(checker, script)
        output = proc.stdout + proc.stderr
        assert "property" in output.lower() or "Enum" in output, (
            f"{checker} should see source_enum typed via _meta.pyi:\n{output}"
        )


# ---------------------------------------------------------------------------
# includes= argument boundary tests
# ---------------------------------------------------------------------------


_INCLUDES_NON_ENUM = """\
    from composite_enum import CompositeEnum

    class Dummy(CompositeEnum, includes=42):
        A = 1
"""


class TestIncludesRejectsNonEnum:
    """ty rejects non-enum includes (type-checks the metaclass __new__ signature)."""

    def test_ty_rejects(self, tmp_path: Path) -> None:
        _skip_unless("ty")
        script = _write_script(tmp_path, _INCLUDES_NON_ENUM)
        proc = _run("ty", script)
        output = proc.stdout + proc.stderr
        assert proc.returncode != 0, f"ty should reject includes=42:\n{output}"
        assert "invalid-argument-type" in output or "includes" in output


@pytest.mark.tripwire
@pytest.mark.parametrize("checker", [c for c in CHECKERS if c != "ty"])
class TestIncludesNonEnumAccepted:
    """Tripwire: other checkers still accept non-enum includes."""

    def test_accepted(self, tmp_path: Path, checker: str) -> None:
        _skip_unless(checker)
        script = _write_script(tmp_path, _INCLUDES_NON_ENUM)
        proc = _run(checker, script)
        output = proc.stdout + proc.stderr
        cfg = CHECKER_CONFIGS[checker]
        assert cfg.is_clean(output, proc.returncode), (
            f"{checker} now rejects non-enum includes, boundary change:\n{output}"
        )


# ---------------------------------------------------------------------------
# Metaclass-only: source_enum invisible, class methods visible
# ---------------------------------------------------------------------------


MODULE_METACLASS_ONLY = """\
    from enum import IntEnum
    from composite_enum import CompositeEnumMeta

    class Priority(IntEnum):
        LOW = 1

    class ExtPriority(IntEnum, metaclass=CompositeEnumMeta, includes=Priority):
        CRITICAL = 3
"""


@pytest.mark.parametrize("checker", CHECKERS)
class TestMetaclassSourceEnumInvisible:
    """source_enum / to_source are invisible on metaclass-only classes."""

    MODULE = MODULE_METACLASS_ONLY
    USAGE = """\
        from pkg.mod import ExtPriority
        from enum import Enum

        se: type[Enum] | None = ExtPriority.CRITICAL.source_enum
        ts: Enum | None = ExtPriority.CRITICAL.to_source()
    """

    def test_errors(self, shared_usage: Path, checker: str) -> None:
        _assert_has_error(checker, shared_usage, "source_enum")


@pytest.mark.parametrize("checker", CHECKERS)
class TestMetaclassClassMethodsWork:
    """Class-level methods work on metaclass-only classes via _meta.pyi."""

    MODULE = MODULE_METACLASS_ONLY
    USAGE = """\
        from pkg.mod import ExtPriority, Priority
        from enum import Enum

        ie: tuple[type[Enum], ...] = ExtPriority.included_enums()
        ib: bool = ExtPriority.includes_enum(Priority)
    """

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


# ---------------------------------------------------------------------------


@pytest.mark.parametrize("checker", REVEAL_CHECKERS)
class TestMetaclassReturnsEnum:
    """On metaclass-only classes, from_source and members_from return
    Enum (not Self)."""

    def test_from_source_returns_enum(self, tmp_path: Path, checker: str) -> None:
        _skip_unless(checker)
        usage = _setup_module(
            tmp_path,
            MODULE_INT_ENUM,
            """\
            from pkg.mod import ExtPriority, Priority
            from enum import Enum

            r = ExtPriority.from_source(Priority.LOW)
            if r is not None:
                reveal_type(r)
            """,
        )
        proc = _run(checker, usage)
        output = proc.stdout + proc.stderr
        assert "Enum" in output, (
            f"{checker} should reveal Enum for metaclass from_source:\n{output}"
        )

    def test_members_from_returns_enum(self, tmp_path: Path, checker: str) -> None:
        _skip_unless(checker)
        usage = _setup_module(
            tmp_path,
            MODULE_INT_ENUM,
            """\
            from pkg.mod import ExtPriority, Priority
            from enum import Enum

            mf = ExtPriority.members_from(Priority)
            reveal_type(mf)
            """,
        )
        proc = _run(checker, usage)
        output = proc.stdout + proc.stderr
        assert "Enum" in output, (
            f"{checker} should reveal frozenset[Enum] for "
            f"metaclass members_from:\n{output}"
        )


# ---------------------------------------------------------------------------
# includes= keyword accepted on both patterns
# ---------------------------------------------------------------------------


INCLUDES_COMPOSITE = """\
    from enum import Enum
    from composite_enum import CompositeEnum

    class Op(Enum):
        X = 1

    class TT(CompositeEnum, includes=Op):
        Y = 2
"""

INCLUDES_METACLASS = """\
    from enum import IntEnum
    from composite_enum import CompositeEnumMeta

    class Op(IntEnum):
        X = 1

    class TT(IntEnum, metaclass=CompositeEnumMeta, includes=Op):
        Y = 2
"""


@pytest.mark.parametrize("checker", CHECKERS)
class TestIncludesKeywordAccepted:
    @pytest.mark.parametrize(
        "code",
        [INCLUDES_COMPOSITE, INCLUDES_METACLASS],
        ids=["composite_base", "metaclass"],
    )
    def test_accepted(self, tmp_path: Path, checker: str, code: str) -> None:
        script = _write_script(tmp_path, code)
        _assert_clean(checker, script)


# ---------------------------------------------------------------------------
# Iteration and from_source return type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("checker", CHECKERS)
class TestIterationTyped:
    MODULE = MODULE_BASIC
    USAGE = """\
        from pkg.mod import TokenType

        for t in TokenType:
            v: str = t.value
    """

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


@pytest.mark.parametrize("checker", CHECKERS)
class TestFromSourceReturnType:
    """from_source on a CompositeEnum subclass returns Self | None."""

    MODULE = MODULE_BASIC
    USAGE = """\
        from pkg.mod import TokenType, Operator

        result = TokenType.from_source(Operator.UNION)
        if result is not None:
            v: str = result.value
            name: str = result.name
    """

    def test_clean(self, shared_usage: Path, checker: str) -> None:
        _assert_clean(checker, shared_usage)


# ---------------------------------------------------------------------------
# __getattr__ TypeVar binding (verify the concrete type is returned)
# ---------------------------------------------------------------------------


GETATTR_COMPOSITE = """\
    from enum import Enum
    from composite_enum import CompositeEnum

    class Op(Enum):
        X = 1

    class TT(CompositeEnum, includes=Op):
        Y = 2

    reveal_type(TT.X)
"""

GETATTR_METACLASS = """\
    from enum import IntEnum
    from composite_enum import CompositeEnumMeta

    class Priority(IntEnum):
        LOW = 1

    class ExtPriority(IntEnum, metaclass=CompositeEnumMeta, includes=Priority):
        CRITICAL = 3

    reveal_type(ExtPriority.LOW)
"""


@pytest.mark.parametrize("checker", CHECKERS)
class TestGetAttrTyping:
    """Verify __getattr__ returns the concrete subclass type."""

    @pytest.mark.parametrize(
        "code,expected",
        [(GETATTR_COMPOSITE, "TT"), (GETATTR_METACLASS, "ExtPriority")],
        ids=["composite_base", "metaclass"],
    )
    def test_reveal_type(
        self,
        tmp_path: Path,
        checker: str,
        code: str,
        expected: str,
    ) -> None:
        _skip_unless(checker)
        script = _write_script(tmp_path, code)
        proc = _run(checker, script)
        output = proc.stdout + proc.stderr
        assert expected in output, f"{checker} should type as {expected}:\n{output}"


# ---------------------------------------------------------------------------
# pyre (requires symlinked source and .pyre_configuration)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_pyre(), reason="pyre not installed")
class TestPyreGrid:
    def test_includes_keyword_accepted(self, tmp_path: Path) -> None:
        script = _setup_pyre_dir(tmp_path, INCLUDES_COMPOSITE)
        _assert_pyre_clean(script)

    def test_includes_non_enum_flagged(self, tmp_path: Path) -> None:
        script = _setup_pyre_dir(
            tmp_path,
            """\
            from enum import Enum
            from composite_enum import CompositeEnum

            class Dummy(CompositeEnum, includes=42):
                A = 1
            """,
        )
        proc = _run_pyre(script)
        output = proc.stdout + proc.stderr
        assert "Incompatible parameter type" in output or "includes" in output, (
            f"pyre should reject includes=42: {output}"
        )

    def test_unknown_keyword_not_flagged(self, tmp_path: Path) -> None:
        script = _setup_pyre_dir(
            tmp_path,
            """\
            from enum import Enum
            from composite_enum import CompositeEnum

            class Op(Enum):
                X = 1

            class TT(CompositeEnum, includes=Op, totally_unknown=42):
                Y = 2
            """,
        )
        _assert_pyre_clean(script)

    def test_injected_member_accepted(self, tmp_path: Path) -> None:
        script = _setup_pyre_dir(
            tmp_path,
            """\
            from enum import Enum
            from composite_enum import CompositeEnum

            class Op(Enum):
                UNION = "|"

            class TokenType(CompositeEnum, includes=Op):
                IDENT = "IDENT"

            u: TokenType = TokenType.UNION
            """,
        )
        _assert_pyre_clean(script)

    def test_library_api_typed(self, tmp_path: Path) -> None:
        script = _setup_pyre_dir(
            tmp_path,
            """\
            from enum import Enum
            from composite_enum import CompositeEnum

            class Op(Enum):
                X = 1

            class TT(CompositeEnum, includes=Op):
                Y = 2

            t = TT.Y
            se = t.source_enum
            ts = t.to_source()
            """,
        )
        _assert_pyre_clean(script)

    def test_without_meta_pyi_rejected(self, tmp_path: Path) -> None:
        script = _setup_pyre_dir(
            tmp_path,
            """\
            from enum import Enum
            from composite_enum import CompositeEnum

            class Op(Enum):
                X = 1

            class TT(CompositeEnum, includes=Op):
                Y = 2
            """,
            include_meta_pyi=False,
        )
        proc = _run_pyre(script)
        output = proc.stdout + proc.stderr
        assert "Unexpected keyword" in output, (
            f"pyre should reject includes= without _meta.pyi: {output}"
        )

    def test_basic_access(self, tmp_path: Path) -> None:
        script = _setup_pyre_dir(
            tmp_path,
            """\
            from enum import Enum
            from composite_enum import CompositeEnum

            class Operator(Enum):
                UNION = "|"
                INTERSECT = "&"

            class TokenType(CompositeEnum, includes=Operator):
                IDENT = "IDENT"
                ASSIGN = "="

            u: TokenType = TokenType.UNION
            i: TokenType = TokenType.INTERSECT
            ident: TokenType = TokenType.IDENT
            v: str = TokenType.UNION.value
            """,
        )
        _assert_pyre_clean(script)

    def test_metaclass_int_enum_rejects_includes(self, tmp_path: Path) -> None:
        """
        Pyre rejects `includes` on metaclass-only classes
        Checks __init_subclass__, not metaclass __new__.
        """
        script = _setup_pyre_dir(
            tmp_path,
            """\
            from enum import IntEnum
            from composite_enum import CompositeEnumMeta

            class Priority(IntEnum):
                LOW = 1
                HIGH = 2

            class ExtPriority(IntEnum, metaclass=CompositeEnumMeta, includes=Priority):
                CRITICAL = 3

            p: ExtPriority = ExtPriority.LOW
            h: ExtPriority = ExtPriority.HIGH
            c: ExtPriority = ExtPriority.CRITICAL
            x: int = ExtPriority.LOW + ExtPriority.HIGH
            """,
        )
        proc = _run_pyre(script)
        output = proc.stdout + proc.stderr
        assert "Unexpected keyword" in output, (
            f"pyre should reject includes= on metaclass-only pattern: {output}"
        )

    def test_multiple_sources(self, tmp_path: Path) -> None:
        script = _setup_pyre_dir(
            tmp_path,
            """\
            from enum import Enum
            from composite_enum import CompositeEnum

            class Ops(Enum):
                ADD = "+"
                SUB = "-"

            class Keywords(Enum):
                IF = "if"
                ELSE = "else"

            class AllTokens(CompositeEnum, includes=[Ops, Keywords]):
                IDENT = "IDENT"

            a: AllTokens = AllTokens.ADD
            i: AllTokens = AllTokens.IF
            ident: AllTokens = AllTokens.IDENT
            """,
        )
        _assert_pyre_clean(script)

    def test_nested_composition(self, tmp_path: Path) -> None:
        script = _setup_pyre_dir(
            tmp_path,
            """\
            from enum import Enum
            from composite_enum import CompositeEnum

            class Base(Enum):
                A = "a"

            class Mid(CompositeEnum, includes=Base):
                B = "b"

            class Top(CompositeEnum, includes=Mid):
                C = "c"

            a: Top = Top.A
            b: Top = Top.B
            c: Top = Top.C
            """,
        )
        _assert_pyre_clean(script)

    def test_getattr_returns_concrete_type(self, tmp_path: Path) -> None:
        script = _setup_pyre_dir(
            tmp_path,
            """\
            from enum import Enum
            from composite_enum import CompositeEnum

            class Op(Enum):
                X = 1

            class TT(CompositeEnum, includes=Op):
                Y = 2

            reveal_type(TT.X)
            """,
        )
        proc = _run_pyre(script)
        output = proc.stdout + proc.stderr
        assert "TT" in output, f"pyre should type TT.X as TT:\n{output}"


# ---------------------------------------------------------------------------
# pytype (needs Python <=3.12 interpreter)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.version_info >= (3, 13) or not _has_pytype(),
    reason="pytype not available or needs Python <=3.12",
)
class TestPytypeGrid:
    """pytype degrades composite classes to Any via the metaclass."""

    def test_includes_keyword_accepted(
        self,
        tmp_path: Path,
        pytype_python: str | None,
    ) -> None:
        if not pytype_python:
            pytest.skip("no Python <=3.12 in PATH")
        script = _write_script(tmp_path, INCLUDES_COMPOSITE)
        proc = _run_pytype(script, pytype_python)
        output = proc.stdout + proc.stderr
        assert "Success" in output or "error" not in output.lower(), (
            f"pytype should accept includes=: {output}"
        )

    def test_injected_member_not_caught(
        self,
        tmp_path: Path,
        pytype_python: str | None,
    ) -> None:
        if not pytype_python:
            pytest.skip("no Python <=3.12 in PATH")
        script = _write_script(
            tmp_path,
            """\
            from enum import Enum
            from composite_enum import CompositeEnum

            class Op(Enum):
                UNION = "|"

            class TokenType(CompositeEnum, includes=Op):
                IDENT = "IDENT"

            u = TokenType.UNION
            """,
        )
        proc = _run_pytype(script, pytype_python)
        output = proc.stdout + proc.stderr
        assert "Success" in output, (
            f"pytype should pass (vacuous) on composite member access. "
            f"If this fails, pytype may have gained metaclass support: {output}"
        )

    def test_trust_check_plain_enum(
        self,
        tmp_path: Path,
        pytype_python: str | None,
    ) -> None:
        """pytype DOES catch missing attrs on plain enums."""
        if not pytype_python:
            pytest.skip("no Python <=3.12 in PATH")
        script = _write_script(
            tmp_path,
            """\
            from enum import Enum

            class Color(Enum):
                RED = 1

            x = Color.NOPE
            """,
        )
        proc = _run_pytype(script, pytype_python)
        output = proc.stdout + proc.stderr
        assert "NOPE" in output or "attribute-error" in output, (
            f"pytype should catch Color.NOPE: {output}"
        )

    def test_basic_access(
        self,
        tmp_path: Path,
        pytype_python: str | None,
    ) -> None:
        if not pytype_python:
            pytest.skip("no Python <=3.12 in PATH")
        script = _write_script(
            tmp_path,
            """\
            from enum import Enum
            from composite_enum import CompositeEnum

            class Operator(Enum):
                UNION = "|"
                INTERSECT = "&"

            class TokenType(CompositeEnum, includes=Operator):
                IDENT = "IDENT"

            u = TokenType.UNION
            i = TokenType.INTERSECT
            ident = TokenType.IDENT
            """,
        )
        proc = _run_pytype(script, pytype_python)
        output = proc.stdout + proc.stderr
        assert "Success" in output, f"pytype failed on basic access: {output}"

    def test_metaclass_int_enum(
        self,
        tmp_path: Path,
        pytype_python: str | None,
    ) -> None:
        if not pytype_python:
            pytest.skip("no Python <=3.12 in PATH")
        script = _write_script(
            tmp_path,
            """\
            from enum import IntEnum
            from composite_enum import CompositeEnumMeta

            class Priority(IntEnum):
                LOW = 1

            class ExtPriority(IntEnum, metaclass=CompositeEnumMeta, includes=Priority):
                CRITICAL = 3

            p = ExtPriority.LOW
            c = ExtPriority.CRITICAL
            """,
        )
        proc = _run_pytype(script, pytype_python)
        output = proc.stdout + proc.stderr
        assert "Success" in output, f"pytype failed on metaclass IntEnum: {output}"


# ---------------------------------------------------------------------------
# Tripwire: detect when pytype/pyre gain Python 3.15 support
# ---------------------------------------------------------------------------


@pytest.mark.tripwire
class TestVersionTripwires:
    @pytest.mark.skipif(
        sys.version_info < (3, 15), reason="only meaningful on Python 3.15+",
    )
    def test_pytype_lacks_python_315_support(self) -> None:
        if not _has_pytype():
            pytest.skip("pytype not installed")
        proc = subprocess.run(
            [sys.executable, "-m", "pytype", "--python-version", "3.15", "-V"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = proc.stdout + proc.stderr
        assert (
            "not yet supported" in output.lower()
            or proc.returncode != 0
            or "3.15" not in output
        ), f"pytype may now support Python 3.15: {output}"

    def test_pyre_resolves_builtins_on_current_python(
        self,
        tmp_path: Path,
    ) -> None:
        if not _has_pyre():
            pytest.skip("pyre not installed")
        probe = tmp_path / "pyre_tripwire"
        probe.mkdir()
        (probe / "test.py").write_text("x: int = 1\n")
        (probe / ".pyre_configuration").write_text(
            json.dumps(
                {
                    "source_directories": ["."],
                }
            )
        )
        proc = subprocess.run(
            ["pyre", "check"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=probe,
        )
        output = proc.stdout + proc.stderr
        assert "Undefined or invalid type" not in output or "int" not in output, (
            f"pyre cannot resolve builtins on Python {sys.version_info}: {output}"
        )
