"""Compose enum types by including members from other enums.

Usage::

    from composite_enum import CompositeEnum

    class Operator(Enum):
        UNION = "|"
        INTERSECT = "&"

    class TokenType(CompositeEnum, includes=Operator):
        IDENT = "IDENT"
        ASSIGN = "="

    assert TokenType.UNION.value == "|"
    assert TokenType.UNION.source_enum is Operator
"""

from composite_enum._meta import CompositeEnum, CompositeEnumMeta

__all__ = ["CompositeEnum", "CompositeEnumMeta"]
__version__ = "0.1.0"
