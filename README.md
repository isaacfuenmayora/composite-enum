# composite-enum

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

class TokenType(CompositeEnum, includes=(Operator,)):
    IDENT = "IDENT"
    STRING = "STRING"
    ASSIGN = "="
    LPAREN = "("
    RPAREN = ")"

# Included members are real members
TokenType.UNION          # <TokenType.UNION: '|'>
TokenType.UNION.value    # '|'
TokenType("|")           # <TokenType.UNION: '|'>
TokenType["UNION"]       # <TokenType.UNION: '|'>

# But they know where they came from
TokenType.UNION.source_enum                 # <enum 'Operator'>
TokenType.to_source(TokenType.UNION)        # <Operator.UNION: '|'>
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

`composite-enum` solves this with a metaclass that injects source enum
members into the new enum's namespace during class creation.

## Usage

### Basic: `CompositeEnum` base class

```python
from composite_enum import CompositeEnum

class TokenType(CompositeEnum, includes=(Operator,)):
    IDENT = "IDENT"
```

Gives you the `source_enum` property on each member.

### Multiple sources

```python
class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3

class Everything(CompositeEnum, includes=(Operator, Priority)):
    MISC = "misc"
```

Included members appear in iteration order: Operator members first,
then Priority, then class body members.

### With StrEnum / IntEnum

`CompositeEnum` extends `Enum`, so it can't be combined with `StrEnum`
or `IntEnum` (Python's enum inheritance rules). Use the metaclass
directly:

```python
from enum import StrEnum  # 3.11+
from composite_enum import CompositeEnumMeta

class TokenType(StrEnum, metaclass=CompositeEnumMeta, includes=(Operator,)):
    IDENT = "IDENT"

isinstance(TokenType.UNION, str)  # True
```

The metaclass validates that included values match the target's data
type. Trying to include `IntEnum` members into a `StrEnum` raises
`TypeError`.

When using the metaclass directly, you get all class-level methods
(`to_source`, `members_from`, etc.) but not the `source_enum`
instance property. Use `TokenType.to_source(member)` instead.

### Pre-3.11 mixin pattern

```python
class TokenType(str, Enum, metaclass=CompositeEnumMeta, includes=(Operator,)):
    IDENT = "IDENT"
```

Works the same as `StrEnum`.

## API Reference

### `CompositeEnum`

Base class for composition. Extend this instead of `Enum`.

### `CompositeEnumMeta`

The metaclass powering composition. Use directly when you need
`StrEnum`, `IntEnum`, etc. as the base type.

#### `includes` (class keyword)

```python
class TokenType(CompositeEnum, includes=(Operator, Delimiter)):
```

Tuple of `Enum` types whose members should be included.

#### `member.source_enum`

```python
TokenType.UNION.source_enum  # <enum 'Operator'>
TokenType.IDENT.source_enum  # None
```

The source enum this member was included from, or `None`.

#### `cls.to_source(member)` / `cls.from_source(member)`

```python
TokenType.to_source(TokenType.UNION)  # Operator.UNION
TokenType.from_source(Operator.UNION) # TokenType.UNION
```

Convert between composite and source members. Returns `None`
when there's no match.

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

### `auto()` in source enums

Works fine. `auto()` values are resolved before inclusion, so the target
enum receives concrete values (1, 2, 3, etc.).

**Caution with `auto()` in the target alongside includes:** the auto
numbering in the target's class body doesn't see the included values.
This can produce duplicate values (which Python treats as aliases).
Use explicit values in the target body when composing.

## Caveats

**Implementation detail dependency.** The metaclass injects members via
`_EnumDict.__setitem__`, which is an implementation detail of CPython's
enum module. It's been stable since Python 3.6 and is unlikely to
change, but it's not a guaranteed public API. Tested on 3.10 through
3.14.

**Member name shadowing.** If you name a member `included_enums`,
`members_from`, `to_source`, `from_source`, or `includes_enum`, it
shadows the corresponding metaclass method. Don't do that.

**Value aliases.** If two included sources share a value (different
name, same value), Python's standard alias behavior applies: the
second becomes an alias of the first. This is normal enum behavior,
not composite-specific.

**Pickling.** Works. Composite members pickle by name, same as regular
enum members.

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
   then attaches metadata (source map, includes tuple) for introspection.

The result is a normal Python enum with normal members. No runtime
proxying, no descriptor tricks, no `__getattr__` overrides.

## Alternatives

- **[aenum](https://github.com/ethanfurman/aenum)** by the stdlib `enum`
  author has `extend_enum()` for adding members to an existing enum at
  runtime. `composite-enum` is for building new enums declaratively from
  existing ones at class-definition time.

- **[extendable-enum](https://pypi.org/project/extendable-enum/)** has
  `@copy_enum_members` for copying members via a decorator. Similar goal,
  but no source tracking, no type compatibility checks, and no
  StrEnum/IntEnum awareness.

## License

MIT
