# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-09-08

### Added

- `CompositeEnum` base class for composing members from other enums
- `CompositeEnumMeta` metaclass for use with `StrEnum`, `IntEnum`, and custom data type mixins
- Introspection API: `source_enum`, `to_source()`, `from_source()`, `members_from()`, `included_enums()`, `includes_enum()`
- Support for nested composition (composing from an already-composite enum)
- Data type validation (e.g., rejects `int` values into a `StrEnum` target)
- `Flag` / `IntFlag` rejection with clear error message
- PEP 561 `py.typed` marker for type checker support
