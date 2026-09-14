from collections.abc import Mapping, Sequence
from enum import Enum, EnumMeta
from typing import Any, TypeVar

from typing_extensions import Self

_T = TypeVar("_T", bound=Enum)

class CompositeEnumMeta(EnumMeta):
    _composite_source_map_: Mapping[str, type[Enum]]
    _composite_includes_: tuple[type[Enum], ...]

    def __new__(
        mcls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        includes: type[Enum] | Sequence[type[Enum]] = (),
        **kwds: Any,
    ) -> CompositeEnumMeta: ...
    def __getattr__(cls: type[_T], name: str) -> _T: ...  # type: ignore
    def included_enums(cls) -> tuple[type[Enum], ...]: ...
    def includes_enum(cls, source: type[Enum]) -> bool: ...
    def members_from(cls, source: type[Enum]) -> frozenset[Enum]: ...
    def from_source(cls, member: Enum) -> Enum | None: ...

class CompositeEnum(Enum, metaclass=CompositeEnumMeta):
    def __init_subclass__(
        cls,
        *,
        includes: type[Enum] | Sequence[type[Enum]] = (),
        **kwargs: Any,
    ) -> None: ...
    @property
    def source_enum(self) -> type[Enum] | None: ...
    def to_source(self) -> Enum | None: ...
    @classmethod
    def from_source(cls, member: Enum) -> Self | None: ...  # type: ignore[override]
    @classmethod
    def members_from(cls, source: type[Enum]) -> frozenset[Self]: ...  # type: ignore[override]
    @classmethod
    def included_enums(cls) -> tuple[type[Enum], ...]: ...
    @classmethod
    def includes_enum(cls, source: type[Enum]) -> bool: ...
