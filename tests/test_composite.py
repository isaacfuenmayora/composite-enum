# pyright: reportAttributeAccessIssue=false
"""Tests for composite_enum."""

from __future__ import annotations

import copy
import pickle
import sys
from enum import Enum, IntEnum

import pytest

from composite_enum import CompositeEnum, CompositeEnumMeta


class Operator(Enum):
    UNION = "|"
    INTERSECT = "&"
    DIFF = "-"
    SYM_DIFF = "^"


class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class IntOp(IntEnum):
    ADD = 1
    SUB = 2
    MUL = 3


class TestSingleSource:
    """Tests for composing from a single source enum."""

    def setup_method(self):
        class TokenType(CompositeEnum, includes=(Operator,)):
            IDENT = "IDENT"
            ASSIGN = "="

        self.TokenType = TokenType

    def test_included_members_exist(self):
        assert self.TokenType.UNION.value == "|"
        assert self.TokenType.IDENT.value == "IDENT"
        assert len(self.TokenType) == 6  # 4 from Operator + 2 own

    def test_included_members_come_first_in_iteration(self):
        names = [m.name for m in self.TokenType]
        assert names == [
            "UNION",
            "INTERSECT",
            "DIFF",
            "SYM_DIFF",
            "IDENT",
            "ASSIGN",
        ]

    def test_source_enum_for_included_member(self):
        assert self.TokenType.UNION.source_enum is Operator
        assert self.TokenType.INTERSECT.source_enum is Operator

    def test_source_enum_for_own_member(self):
        assert self.TokenType.IDENT.source_enum is None

    def test_to_source_converts_back(self):
        original = self.TokenType.to_source(self.TokenType.UNION)
        assert original is Operator.UNION
        assert type(original) is Operator

    def test_to_source_returns_none_for_own_member(self):
        assert self.TokenType.to_source(self.TokenType.IDENT) is None

    def test_from_source_converts_to_composite(self):
        result = self.TokenType.from_source(Operator.UNION)
        assert result is self.TokenType.UNION

    def test_from_source_returns_none_for_own_member(self):
        assert self.TokenType.from_source(self.TokenType.IDENT) is None

    def test_from_source_returns_none_for_non_included_enum(self):
        assert self.TokenType.from_source(Priority.LOW) is None

    def test_composite_member_is_not_source_instance(self):
        assert isinstance(self.TokenType.UNION, self.TokenType)
        assert not isinstance(self.TokenType.UNION, Operator)

    def test_composite_member_not_equal_to_source_member(self):
        assert self.TokenType.UNION != Operator.UNION

    def test_composite_member_value_equals_source_value(self):
        assert self.TokenType.UNION.value == Operator.UNION.value

    def test_source_member_not_in_composite(self):
        assert Operator.UNION not in self.TokenType

    def test_value_lookup(self):
        assert self.TokenType("|") is self.TokenType.UNION
        assert self.TokenType("|") is not Operator("|")

    def test_name_lookup(self):
        assert self.TokenType["UNION"] is self.TokenType.UNION


class TestMultipleSources:
    """Tests for composing from multiple source enums."""

    def setup_method(self):
        class Combined(CompositeEnum, includes=(Operator, Priority)):
            EXTRA = "extra"

        self.Combined = Combined

    def test_all_members_present(self):
        assert self.Combined.UNION.value == "|"
        assert self.Combined.LOW.value == 1
        assert self.Combined.EXTRA.value == "extra"
        assert len(self.Combined) == 8  # 4 + 3 + 1

    def test_iteration_preserves_source_order(self):
        names = [m.name for m in self.Combined]
        assert names == [
            "UNION",
            "INTERSECT",
            "DIFF",
            "SYM_DIFF",
            "LOW",
            "MEDIUM",
            "HIGH",
            "EXTRA",
        ]

    def test_sources_tracked_separately(self):
        assert self.Combined.UNION.source_enum is Operator
        assert self.Combined.LOW.source_enum is Priority
        assert self.Combined.EXTRA.source_enum is None

    def test_members_from_returns_correct_subset(self):
        op_members = self.Combined.members_from(Operator)
        assert op_members == frozenset(
            {
                self.Combined.UNION,
                self.Combined.INTERSECT,
                self.Combined.DIFF,
                self.Combined.SYM_DIFF,
            }
        )

    def test_members_from_returns_empty_for_unknown_source(self):
        class Other(Enum):
            X = 1

        assert self.Combined.members_from(Other) == frozenset()

    def test_includes_enum(self):
        assert self.Combined.includes_enum(Operator) is True
        assert self.Combined.includes_enum(Priority) is True

    def test_includes_enum_false_for_unknown(self):
        class Other(Enum):
            X = 1

        assert self.Combined.includes_enum(Other) is False

    def test_included_enums_returns_sources_in_order(self):
        assert self.Combined.included_enums() == (Operator, Priority)


class TestNoIncludes:
    def test_behaves_like_normal_enum(self):
        class Plain(CompositeEnum):
            A = 1
            B = 2

        assert Plain.A.value == 1
        assert len(Plain) == 2

    def test_empty_includes_tuple(self):
        class Plain(CompositeEnum, includes=()):
            A = 1

        assert Plain.A.value == 1


class TestIncludesAsSequence:
    def test_list_includes(self):
        class TokenType(CompositeEnum, includes=[Operator]):
            IDENT = "IDENT"

        assert TokenType.UNION.value == "|"
        assert TokenType.IDENT.value == "IDENT"
        assert len(TokenType) == 5  # 4 from Operator + 1 own

    def test_list_multiple_sources(self):
        class Combined(CompositeEnum, includes=[Operator, Priority]):
            EXTRA = "extra"

        assert Combined.UNION.value == "|"
        assert Combined.LOW.value == 1
        assert len(Combined) == 8  # 4 + 3 + 1

    def test_included_enums_returns_tuple_regardless(self):
        class TokenType(CompositeEnum, includes=[Operator]):
            IDENT = "IDENT"

        result = TokenType.included_enums()
        assert isinstance(result, tuple)
        assert result == (Operator,)


class TestNameConflicts:
    def test_conflict_between_sources_raises(self):
        class A(Enum):
            X = 1

        class B(Enum):
            X = 2

        with pytest.raises(ValueError, match="Name 'X' exists in both A and B"):

            class Bad(CompositeEnum, includes=(A, B)):
                pass

    def test_conflict_between_source_and_body_raises(self):
        with pytest.raises(TypeError, match="already defined"):

            class Bad(CompositeEnum, includes=(Operator,)):
                UNION = "something_else"


class TestTypeValidation:
    def test_non_enum_in_includes_raises(self):
        with pytest.raises(TypeError, match="includes expects Enum types"):

            class Bad(CompositeEnum, includes=(str,)):
                X = 1

    def test_int_values_into_str_target_raises(self):
        with pytest.raises(TypeError, match="requires str values"):

            class Bad(str, Enum, metaclass=CompositeEnumMeta, includes=(IntOp,)):
                X = "x"

    def test_str_values_into_int_target_raises(self):
        with pytest.raises(TypeError, match="requires int values"):

            class Bad(IntEnum, metaclass=CompositeEnumMeta, includes=(Operator,)):
                X = 1

    def test_int_source_into_plain_enum_works(self):
        class Target(CompositeEnum, includes=(IntOp,)):
            EXTRA = "extra"

        assert Target.ADD.value == 1
        assert Target.EXTRA.value == "extra"

    def test_mixed_type_sources_into_plain_enum(self):
        class Target(CompositeEnum, includes=(IntOp, Operator)):
            EXTRA = "extra"

        assert Target.ADD.value == 1
        assert Target.UNION.value == "|"
        assert Target.EXTRA.value == "extra"
        assert len(Target) == 8  # 3 from IntOp + 4 from Operator + 1 own


class TestFlagRejection:
    def test_flag_source_raises(self):
        from enum import Flag

        class Perms(Flag):
            READ = 1
            WRITE = 2

        with pytest.raises(TypeError, match="Flag enum"):

            class Bad(CompositeEnum, includes=(Perms,)):
                OTHER = 4


class TestIntEnum:
    def test_int_source_into_int_target(self):
        class Extended(IntEnum, metaclass=CompositeEnumMeta, includes=(IntOp,)):
            DIV = 4
            MOD = 5

        assert Extended.ADD.value == 1
        assert Extended.DIV.value == 4
        assert isinstance(Extended.ADD, int)

    def test_to_source_with_int(self):
        class Extended(IntEnum, metaclass=CompositeEnumMeta, includes=(IntOp,)):
            DIV = 4

        assert Extended.to_source(Extended.ADD) is IntOp.ADD

    def test_from_source_with_int(self):
        class Extended(IntEnum, metaclass=CompositeEnumMeta, includes=(IntOp,)):
            DIV = 4

        assert Extended.from_source(IntOp.ADD) is Extended.ADD

    def test_source_enum_with_int(self):
        class Extended(IntEnum, metaclass=CompositeEnumMeta, includes=(IntOp,)):
            DIV = 4

        assert Extended.ADD.source_enum is IntOp
        assert Extended.DIV.source_enum is None


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="StrEnum requires Python 3.11+",
)
class TestStrEnum:
    def test_str_source_into_strenum_target(self):
        from enum import StrEnum

        class StrOp(StrEnum):
            PLUS = "+"
            MINUS = "-"

        class Extended(StrEnum, metaclass=CompositeEnumMeta, includes=(StrOp,)):
            STAR = "*"
            SLASH = "/"

        assert Extended.PLUS.value == "+"
        assert Extended.STAR.value == "*"
        assert isinstance(Extended.PLUS, str)

    def test_plain_enum_str_values_into_strenum(self):
        from enum import StrEnum

        class TokenType(StrEnum, metaclass=CompositeEnumMeta, includes=(Operator,)):
            IDENT = "IDENT"

        assert isinstance(TokenType.UNION, str)
        assert TokenType.UNION == "|"

    def test_to_source_with_strenum(self):
        from enum import StrEnum

        class StrOp(StrEnum):
            PLUS = "+"
            MINUS = "-"

        class Extended(StrEnum, metaclass=CompositeEnumMeta, includes=(StrOp,)):
            STAR = "*"

        assert Extended.to_source(Extended.PLUS) is StrOp.PLUS

    def test_from_source_with_strenum(self):
        from enum import StrEnum

        class StrOp(StrEnum):
            PLUS = "+"
            MINUS = "-"

        class Extended(StrEnum, metaclass=CompositeEnumMeta, includes=(StrOp,)):
            STAR = "*"

        assert Extended.from_source(StrOp.PLUS) is Extended.PLUS

    def test_strenum_source_into_plain_enum(self):
        from enum import StrEnum

        class StrOp(StrEnum):
            PLUS = "+"

        class Target(CompositeEnum, includes=(StrOp,)):
            EXTRA = "extra"

        assert Target.PLUS.value == "+"
        assert Target.EXTRA.value == "extra"

    def test_source_enum_with_strenum(self):
        from enum import StrEnum

        class StrOp(StrEnum):
            PLUS = "+"
            MINUS = "-"

        class Extended(StrEnum, metaclass=CompositeEnumMeta, includes=(StrOp,)):
            STAR = "*"

        assert Extended.PLUS.source_enum is StrOp
        assert Extended.STAR.source_enum is None


class TestPreMixinPattern:
    def test_str_enum_mixin_pre311(self):
        class TokenType(str, Enum, metaclass=CompositeEnumMeta, includes=(Operator,)):
            IDENT = "IDENT"

        assert isinstance(TokenType.UNION, str)
        assert TokenType.UNION == "|"


class TestAutoInSource:
    def test_auto_values_resolved_before_inclusion(self):
        from enum import auto

        class Source(Enum):
            A = auto()
            B = auto()
            C = auto()

        class Target(CompositeEnum, includes=(Source,)):
            D = 100

        assert Target.A.value == 1
        assert Target.B.value == 2
        assert Target.C.value == 3
        assert Target.D.value == 100


class _PickleTokenType(CompositeEnum, includes=(Operator,)):
    IDENT = "IDENT"


class TestPickle:
    def test_composite_members_survive_pickle(self):
        for member in _PickleTokenType:
            roundtripped = pickle.loads(pickle.dumps(member))
            assert roundtripped is member


class TestCopyDeepcopy:
    def test_copy_preserves_identity(self):
        assert copy.copy(_PickleTokenType.UNION) is _PickleTokenType.UNION

    def test_deepcopy_preserves_identity(self):
        assert copy.deepcopy(_PickleTokenType.UNION) is _PickleTokenType.UNION


class TestValueAliases:
    def test_same_value_across_sources_creates_alias(self):
        class A(Enum):
            X = 1

        class B(Enum):
            Y = 1  # same value as A.X

        class Combined(CompositeEnum, includes=(A, B)):
            Z = 2

        assert Combined.X.value == 1
        assert Combined.Y is Combined.X  # Y is an alias
        assert len(Combined) == 2  # X and Z (Y is alias, not counted)


class TestEdgeCases:
    def test_empty_source_enum(self):
        class Empty(Enum):
            pass

        class Target(CompositeEnum, includes=(Empty,)):
            X = 1

        assert len(Target) == 1
        assert Target.X.value == 1

    def test_composite_with_no_own_members(self):
        class Target(CompositeEnum, includes=(Operator,)):
            pass

        assert len(Target) == 4
        assert Target.UNION.value == "|"


class TestNestedComposition:
    def setup_method(self):
        class Base(CompositeEnum, includes=(Operator,)):
            IDENT = "IDENT"

        class Extended(CompositeEnum, includes=(Base,)):
            EXTRA = "extra"

        self.Base = Base
        self.Extended = Extended

    def test_all_members_transfer(self):
        names = [m.name for m in self.Extended]
        assert names == ["UNION", "INTERSECT", "DIFF", "SYM_DIFF", "IDENT", "EXTRA"]

    def test_source_enum_points_to_immediate_source(self):
        assert self.Extended.UNION.source_enum is self.Base
        assert self.Extended.IDENT.source_enum is self.Base
        assert self.Extended.EXTRA.source_enum is None

    def test_to_source_returns_immediate_source_member(self):
        result = self.Extended.to_source(self.Extended.UNION)
        assert result is self.Base.UNION
        assert type(result) is self.Base

    def test_chaining_to_source_reaches_original(self):
        base_member = self.Extended.to_source(self.Extended.UNION)
        assert base_member is not None
        original = self.Base.to_source(base_member)
        assert original is Operator.UNION

    def test_from_source_with_nested(self):
        assert self.Extended.from_source(self.Base.UNION) is self.Extended.UNION
        assert (
            self.Extended.from_source(Operator.UNION) is None
        )  # not the immediate source


class TestSetifyUseCase:
    def setup_method(self):
        self.Operator = Operator

        class TokenType(CompositeEnum, includes=(Operator,)):
            IDENT = "IDENT"
            STRING = "STRING"
            ASSIGN = "="
            LPAREN = "("
            RPAREN = ")"

        self.TokenType = TokenType

    def test_operator_check_via_members_from(self):
        ops = self.TokenType.members_from(self.Operator)
        assert self.TokenType.UNION in ops
        assert self.TokenType.IDENT not in ops

    def test_bridge_to_operator_for_dispatch(self):
        token_type = self.TokenType.DIFF
        op = self.TokenType.to_source(token_type)
        assert op is Operator.DIFF

        dispatch = {
            Operator.UNION: set.union,
            Operator.INTERSECT: set.intersection,
            Operator.DIFF: set.difference,
            Operator.SYM_DIFF: set.symmetric_difference,
        }
        a = {1, 2, 3}
        b = {2, 3, 4}
        assert dispatch[op](a, b) == {1}

    def test_source_enum_property(self):
        assert self.TokenType.UNION.source_enum is Operator
        assert self.TokenType.IDENT.source_enum is None

    def test_full_iteration(self):
        names = [m.name for m in self.TokenType]
        assert names == [
            "UNION",
            "INTERSECT",
            "DIFF",
            "SYM_DIFF",
            "IDENT",
            "STRING",
            "ASSIGN",
            "LPAREN",
            "RPAREN",
        ]
