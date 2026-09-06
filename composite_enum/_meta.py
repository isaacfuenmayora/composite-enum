"""Metaclass and base class for composing enum types."""

from __future__ import annotations

from enum import Enum, EnumMeta, Flag
from typing import Any


def _get_data_type(bases: tuple[type, ...]) -> type | None:
    """Return the mixin data type (str, int, …) from enum bases, or None."""
    for base in bases:
        for cls in base.__mro__:
            if cls is object or isinstance(cls, EnumMeta):
                continue
            return cls
    return None


def _check_flag(source: type[Enum]) -> None:
    if issubclass(source, Flag):
        raise TypeError(
            f"{source.__name__} is a Flag enum. Flag composition is not "
            f"supported because bitwise semantics across unrelated Flag "
            f"enums are ambiguous. Use plain Enum, StrEnum, or IntEnum."
        )


def _check_data_type(
    source: type[Enum],
    member: Enum,
    expected: type | None,
    target_name: str,
) -> None:
    if expected is not None and not isinstance(member.value, expected):
        raise TypeError(
            f"{source.__name__}.{member.name} has value {member.value!r} "
            f"({type(member.value).__name__}), but {target_name} requires "
            f"{expected.__name__} values"
        )


def _get_source_enum(self: Enum) -> type[Enum] | None:
    """The source enum this member was included from, or None."""
    return self.__class__._composite_source_map_.get(self.name)  # type: ignore[attr-defined]


class CompositeEnumMeta(EnumMeta):
    """Metaclass that composes members from other enums into a new one."""

    _composite_source_map_: dict[str, type[Enum]]
    _composite_includes_: tuple[type[Enum], ...]

    @classmethod
    def __prepare__(
        mcls,
        name: str,
        bases: tuple[type, ...],
        includes: tuple[type[Enum], ...] = (),
        **kwds: Any,
    ):
        namespace = super().__prepare__(name, bases, **kwds)

        data_type = _get_data_type(bases)
        seen: dict[str, type[Enum]] = {}

        for source in includes:
            if not isinstance(source, EnumMeta):
                raise TypeError(
                    f"includes expects Enum types, got "
                    f"{type(source).__name__}: {source!r}"
                )
            _check_flag(source)

            for member in source:
                if member.name in seen:
                    raise ValueError(
                        f"Name '{member.name}' exists in both "
                        f"{seen[member.name].__name__} and {source.__name__}"
                    )
                _check_data_type(source, member, data_type, name)

                seen[member.name] = source
                # _EnumDict.__setitem__ registers this as an enum member candidate.
                namespace[member.name] = member.value

        return namespace

    def __new__(
        mcls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        includes: tuple[type[Enum], ...] = (),
        **kwds: Any,
    ):
        cls = super().__new__(mcls, name, bases, namespace, **kwds)  # type: ignore[arg-type]

        source_map: dict[str, type[Enum]] = {}
        for source in includes:
            for member in source:
                source_map[member.name] = source

        cls._composite_source_map_ = source_map
        cls._composite_includes_ = tuple(includes)
        cls.source_enum = property(_get_source_enum)  # type: ignore[attr-defined]
        return cls

    def included_enums(cls) -> tuple[type[Enum], ...]:
        """Return the source enums this composite was built from."""
        return getattr(cls, "_composite_includes_", ())

    def includes_enum(cls, source: type[Enum]) -> bool:
        """Check if this composite includes members from *source*."""
        return source in cls.included_enums()

    def members_from(cls, source: type[Enum]) -> frozenset:
        """Return the subset of members that originated from *source*."""
        source_map = getattr(cls, "_composite_source_map_", {})
        return frozenset(cls[name] for name, src in source_map.items() if src is source)

    def to_source(cls, member: Enum) -> Enum | None:
        """Convert a composite member back to its source enum member, or None."""
        source_map = getattr(cls, "_composite_source_map_", {})
        source = source_map.get(member.name)
        if source is None:
            return None
        return source(member.value)

    def from_source(cls, member: Enum) -> Enum | None:
        """Convert a source enum member to its composite equivalent, or None."""
        source_map = getattr(cls, "_composite_source_map_", {})
        source = source_map.get(member.name)
        if source is None or source is not type(member):
            return None
        return cls[member.name]  # type: ignore[return-value]


class CompositeEnum(Enum, metaclass=CompositeEnumMeta):
    """Enum base class with composition support."""
