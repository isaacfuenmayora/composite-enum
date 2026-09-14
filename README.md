# composite-enum

[![CI](https://github.com/isaacfuenmayora/composite-enum/actions/workflows/ci.yml/badge.svg)](https://github.com/isaacfuenmayora/composite-enum/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/composite-enum)](https://pypi.org/project/composite-enum/)
[![Python](https://img.shields.io/pypi/pyversions/composite-enum)](https://pypi.org/project/composite-enum/)
[![Checked with pyright](https://microsoft.github.io/pyright/img/pyright_badge.svg)](https://microsoft.github.io/pyright/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Build superset enums by composing members from other enums. Included
members become real first-class members of the new enum, with introspection
back to their origin.

```python
from enum import Enum
from composite_enum import CompositeEnum

class Operator(Enum):
    UNION = "|"
    INTERSECT = "&"
    DIFF = "-"
    SYM_DIFF = "^"

class TokenType(CompositeEnum, includes=Operator):
    IDENT = "IDENT"
    STRING = "STRING"
    ASSIGN = "="
    LPAREN = "("
    RPAREN = ")"

# TokenType has all 9 members: 4 from Operator + 5 of its own
list(TokenType)
# [UNION, INTERSECT, DIFF, SYM_DIFF, IDENT, STRING, ASSIGN, LPAREN, RPAREN]

# Included members are real members
TokenType.UNION          # <TokenType.UNION: '|'>
TokenType.UNION.value    # '|'
TokenType("|")           # <TokenType.UNION: '|'>
TokenType["UNION"]       # <TokenType.UNION: '|'>

# But they know where they came from
TokenType.UNION.source_enum                 # <enum 'Operator'>
TokenType.UNION.to_source()                 # <Operator.UNION: '|'>
TokenType.from_source(Operator.UNION)       # <TokenType.UNION: '|'>
TokenType.IDENT.source_enum                 # None (defined directly)
TokenType.members_from(Operator)            # frozenset({UNION, INTERSECT, DIFF, SYM_DIFF})
```

## Install

```bash
pip install composite-enum
```

### Development

```bash
git clone https://github.com/isaacfuenmayora/composite-enum
cd composite-enum
```

With uv:

```bash
uv sync
uv run pytest
```

With pip:

```bash
pip install -e . && pip install pytest
pytest
```

## Why

Python's `Enum` doesn't allow subclassing an enum that already has members.
This is intentional ([docs](https://docs.python.org/3/howto/enum.html#restricted-enum-subclassing)),
but it means you can't express "TokenType is Operator plus some extra token
types" through inheritance. You end up duplicating the values and hoping
they stay in sync.

This restriction exists for good reason.
[`flufl.enum`](https://gitlab.com/flufl/flufl.enum), the precursor to
Python's stdlib `enum`, supported member inheritance natively. That
feature was dropped in [PEP 435](https://peps.python.org/pep-0435/) because it conflicts with members being
instances of their enum class. CPython core developer Alyssa Coghlan
[later speculated](https://python-notes.curiousefficiency.org/en/latest/python3/enum_creation.html#support-for-alternate-declaration-syntaxes)
that extensible enums would require aggregating members from multiple
independent enumerations, sketching a hypothetical syntax:

```python
class MoreColors(AggregateEnum, extends=Color):
    cyan = ...
    magenta = ...
```

This was never implemented in the stdlib. `composite-enum` takes a
similar approach using `includes` instead of `extends`.

`composite-enum` solves this with a metaclass that injects source enum
members into the new enum's namespace during class creation.

## Usage

The opening example covers the basics. Here's what else you can do.

### Multiple sources

```python
class Delimiter(Enum):
    COMMA = ","
    SEMICOLON = ";"

class TokenType(CompositeEnum, includes=(Operator, Delimiter)):
    IDENT = "IDENT"
    STRING = "STRING"
    ASSIGN = "="
    LPAREN = "("
    RPAREN = ")"

TokenType.included_enums()  # (Operator, Delimiter)

# Included members appear first, in includes order, then class body
list(TokenType)
# [UNION, INTERSECT, DIFF, SYM_DIFF, COMMA, SEMICOLON, IDENT, STRING, ASSIGN, LPAREN, RPAREN]
```

### With StrEnum / IntEnum

`CompositeEnum` can't be used alongside `StrEnum` or `IntEnum`
(Python's enum inheritance rules). Use the metaclass directly:

```python
from enum import StrEnum  # 3.11+
from composite_enum import CompositeEnumMeta

class TokenType(StrEnum, metaclass=CompositeEnumMeta, includes=Operator):
    IDENT = "IDENT"

isinstance(TokenType.UNION, str)  # True
```

The metaclass validates that included values match the target's data
type. All introspection methods work the same either way.

The same metaclass approach works for any data type mixin, not just
`StrEnum` and `IntEnum`. Use `(float, Enum)`, `(bytes, Enum)`, or
any custom type:

```python
class Voltage(Enum):
    LOW = 3.3
    HIGH = 5.0

class Signal(float, Enum, metaclass=CompositeEnumMeta, includes=Voltage):
    GROUND = 0.0

isinstance(Signal.LOW, float)  # True
```

> **Note:** The metaclass-only path has type checker limitations.
> See [Type Checker Compatibility](#type-checker-compatibility) below.
> Subclassing `CompositeEnum` is the type-checker-friendly path.

### Nested composition

Composing from an already-composite enum works. `source_enum` points
to the immediate source, not the original:

```python
class Base(CompositeEnum, includes=Operator):
    IDENT = "IDENT"

class Extended(CompositeEnum, includes=Base):
    EXTRA = "extra"

Extended.UNION.source_enum  # <enum 'Base'>, not Operator
```

## API Reference

### `CompositeEnum`

Base class for composition. Extend this instead of `Enum`.

### `CompositeEnumMeta`

The metaclass powering composition. Use directly when you need
`StrEnum`, `IntEnum`, etc. as the base type.

#### `includes` (class keyword)

```python
class TokenType(CompositeEnum, includes=Operator):               # single source
class TokenType(CompositeEnum, includes=(Operator, Delimiter)):  # multiple sources
```

A single `Enum` type or a sequence of them whose members should be included.

#### `member.source_enum`

```python
TokenType.UNION.source_enum  # <enum 'Operator'>
TokenType.IDENT.source_enum  # None
```

The source enum this member was included from, or `None`.

#### `member.to_source()`

```python
TokenType.UNION.to_source()  # Operator.UNION
TokenType.IDENT.to_source()  # None
```

Convert a composite member back to its source enum member. Returns
`None` for members defined directly on the composite.

#### `cls.from_source(member)`

```python
TokenType.from_source(Operator.UNION) # TokenType.UNION
```

Convert a source enum member to its composite equivalent. Returns
`None` when there's no match.

#### `cls.members_from(source)`

```python
TokenType.members_from(Operator)
# frozenset({TokenType.UNION, TokenType.INTERSECT, ...})
```

Returns a `frozenset` of members that originated from `source`.

#### `cls.included_enums()` / `cls.includes_enum(source)`

```python
TokenType.included_enums()        # (Operator, Delimiter)
TokenType.includes_enum(Operator) # True
```

Introspect which source enums were composed in.

## Supported Enum Types

| Base type | Python | Supported | How |
|---|---|---|---|
| `Enum` | 3.10+ | Yes | `CompositeEnum` base class |
| `StrEnum` | 3.11+ | Yes | `metaclass=CompositeEnumMeta` |
| `IntEnum` | 3.10+ | Yes | `metaclass=CompositeEnumMeta` |
| `str, Enum` mixin | 3.10+ | Yes | `metaclass=CompositeEnumMeta` |
| `int, Enum` mixin | 3.10+ | Yes | `metaclass=CompositeEnumMeta` |
| `Flag` | any | No | Bitwise semantics across unrelated Flags are ambiguous |
| `IntFlag` | any | No | Same as Flag |

### Source enum types

Source enums (the ones in `includes`) can be any `Enum`, `StrEnum`, or
`IntEnum`. Their values must be compatible with the target's data type:

| Target type | Accepted source values |
|---|---|
| `Enum` (plain) | Anything |
| `StrEnum` / `str, Enum` | Must be `str` |
| `IntEnum` / `int, Enum` | Must be `int` |

## Type Checker Compatibility

`composite-enum` ships a hand-written `.pyi` stub with a `__getattr__`
on the metaclass so that type checkers see dynamically injected members
(e.g. `TokenType.UNION`) typed as the correct enum subclass. The
trade-off is typos like `TokenType.TYPO` are silently accepted. Any
attribute access is allowed.

The tables below summarize how each type checker behaves with the
`_meta.pyi` stub. All features work correctly at runtime regardless.
The pyrefly column reflects `strict` mode, its default `basic` preset
silently accepts everything.

### `CompositeEnum` base class

| Feature | pyright | mypy | basedpyright | pyrefly | ty | pyre | pytype |
|---|---|---|---|---|---|---|---|
| `includes=` keyword | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Injected member typed correctly | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅¹ |
| Typo detection (`TT.NOPE`) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `source_enum` / `to_source()` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅¹ |
| `from_source()` → `Self` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌¹ |
| `members_from()` → `frozenset[Self]` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌¹ |
| `includes=42` rejected | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |

### `metaclass=CompositeEnumMeta` (IntEnum, StrEnum, etc.)

| Feature | pyright | mypy | basedpyright | pyrefly | ty | pyre | pytype |
|---|---|---|---|---|---|---|---|
| `includes=` keyword | ✅ | ✅ | ✅ | ✅ | ✅ | ❌² | ✅ |
| Injected member typed correctly | ✅ | ✅ | ✅ | ✅ | ✅ | —² | ✅¹ |
| Typo detection (`TT.NOPE`) | ❌ | ❌ | ❌ | ❌ | ❌ | —² | ❌ |
| `source_enum` / `to_source()` | ❌³ | ❌³ | ❌³ | ❌³ | ❌³ | —² | ❌³ |
| `from_source()` → `Enum`⁴ | ✅ | ✅ | ✅ | ✅ | ✅ | —² | ❌¹ |
| `members_from()` → `frozenset[Enum]`⁴ | ✅ | ✅ | ✅ | ✅ | ✅ | —² | ❌¹ |
| `includes=42` rejected | ❌ | ❌ | ❌ | ❌ | ✅ | —² | ❌ |

**Notes:**

1. pytype resolves composite classes to `Any` via the metaclass, so access succeeds vacuously with no real type narrowing.
2. Pyre checks `__init_subclass__`, not the metaclass `__new__`, so it rejects the `includes=` keyword on metaclass-only classes. Suppress with `# pyre-ignore[28]` on the class definition.
3. `source_enum` and `to_source()` are injected at runtime by `CompositeEnumMeta.__new__` and work on both paths. The `.pyi` stub declares them on `CompositeEnum` only, so type checkers can't see them on the metaclass-only path. Suppress with `# type: ignore[attr-defined]` (mypy) or `# pyright: ignore[reportAttributeAccessIssue]`.
4. On the `CompositeEnum` path, `from_source()` returns `Self | None` and `members_from()` returns `frozenset[Self]`. On the metaclass path they return `Enum | None` and `frozenset[Enum]` instead . The return type is the base `Enum` rather than the concrete subclass. Cast or `# type: ignore[assignment]` when assigning to the concrete type.

## Caveats

**Implementation detail dependency.** The metaclass injects members via
`_EnumDict.__setitem__`, which is an implementation detail of CPython's
enum module. It's been stable since Python 3.6 and is unlikely to
change, but it's not a guaranteed public API. Tested on 3.10 through
3.15.

**Source members are not `in` the composite.** `Enum.__contains__`
uses `isinstance`, so `Operator.UNION in TokenType` is `False` even
though `TokenType.UNION` exists with the same value. Use
`TokenType.from_source(Operator.UNION)` to check membership.

**Reserved member names.** The names `source_enum`, `included_enums`,
`includes_enum`, `members_from`, `to_source`, and `from_source` are
reserved by the metaclass. Using any of them as a member name raises `TypeError` at class creation.

**Source methods don't transfer.** Only member names and values are
composed. Methods, properties, and custom `__init__` defined on a
source enum are not carried over to the composite.

**Source enum aliases are preserved.** If a source enum has aliases
(multiple names for the same value), they transfer as aliases in the
composite too:

```python
class Source(Enum):
    PRIMARY = 1
    ALIAS = 1  # alias of PRIMARY

class Target(CompositeEnum, includes=Source):
    EXTRA = "extra"

Target.PRIMARY          # <Target.PRIMARY: 1>
Target["ALIAS"]         # <Target.PRIMARY: 1> (alias, same as source)
```

**Value aliases across sources.** If two included sources share a value
(different name, same value), the second name becomes an alias of the
first. This is standard enum behavior, not composite-specific, but it
has implications for introspection:

```python
class A(Enum):
    X = 1

class B(Enum):
    Y = 1

class Combined(CompositeEnum, includes=(A, B)):
    Z = 2

Combined.Y                              # <Combined.X: 1> (Y is an alias)
Combined.from_source(B.Y)               # <Combined.X: 1>
Combined.from_source(B.Y).source_enum   # <enum 'A'> (not B)
Combined.from_source(B.Y).to_source()   # <A.X: 1>   (not B.Y)
Combined.members_from(A)                # frozenset({<Combined.X: 1>})
Combined.members_from(B)                # frozenset({<Combined.X: 1>}) (same member)
```

Because `Y` is an alias for `X`, the canonical member's `source_enum`
always points to whichever source provided the canonical name (`A`),
regardless of which source you used in `from_source()`. Likewise,
`members_from()` returns the canonical member for both sources.

## How It Works

The metaclass overrides `__prepare__` and `__new__`:

1. **`__prepare__`** runs before the class body executes. It creates the
   standard `_EnumDict` namespace, then injects each source enum's
   members via `namespace[name] = value`. `_EnumDict.__setitem__`
   registers these as member candidates. This means included members
   appear first in iteration order.

2. The **class body** executes next, adding its own members. If a name
   collides with an already-injected member, `_EnumDict` raises
   `TypeError` immediately.

3. **`__new__`** builds the actual enum class via `super().__new__()`,
   then attaches metadata for introspection.

The result is a normal stdlib `Enum`. Standard tools like `isinstance`,
`pickle`, `match/case`, and `list()` all work exactly as they would
with any hand-written enum. The only additions are the introspection
methods (`source_enum`, `to_source`, etc.).

## Alternatives

- **[flufl.enum](https://fluflenum.readthedocs.io/en/stable/using.html#extending-an-enumeration-through-subclassing)**
  is the original Python enum package (predating the stdlib) and still
  supports member inheritance natively. If you want true subclassing
  where parent and child share member identity, and you don't need to
  stay on the stdlib `enum`, `flufl.enum` is actively maintained and
  battle-tested since 2004.

- **[aenum](https://github.com/ethanfurman/aenum)** by the stdlib `enum`
  maintainer provides `extend_enum()` for adding members to an existing enum
  at runtime. If you need to modify enums you don't control,
  `aenum` is the mature, well-established choice.

- **[extendable-enum](https://pypi.org/project/extendable-enum/)** takes a decorator approach: `@inheritable_enum` makes an existing enum subclassable (so `class Derived(Base):` works directly), while `@copy_enum_members` copies members from one enum into a new, distinct class.

- **[unionenum.py](https://gist.github.com/plammens/ab1a2f236b5c6d748f193eb12eefa6dd)**
  is a clever gist that creates union enums where members retain their
  original type identity rather than becoming members of the new class.

`composite-enum` occupies a slightly different niche: declarative
composition of one or more source enums at class-definition time, with
source tracking and type compatibility checks. If one of the above fits
your use case better, use it.

## License

MIT
