"""`.length` types as Int in a provide method body, as it does in a `fn`.

`infer_ir`, the type oracle of the provide-method stratum, answered None for
`.length` on a Str, Bytes or List, where `infer_ast` (the `fn` stratum) types
it Int. So the reference lowering left `operands` off `xs.length + 1` in a
provide method, and every tier that keys on `operands` rendered the host
operator there: on go the sum wrapped where the same sum in a `fn` traps, and
selfhost/lower.rvl (which does annotate it) diverged from the reference on
tests/fixtures/emit_go_corpus/comp_provide_records.rvl (PR #2261).

The rule is for sized values only. A record field that happens to be named
`length` keeps its declared type, so `r.length + 1` on a `length: Str` field
is refused in a provide method with the message a `fn` gives.
"""

import re

import pytest

from revl import compile_source
from revl.errors import RevlError

SIZED = ("Str", "Bytes", "List[Int]")


def _sum_nodes(ir):
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("kind") == "bin" and node.get("op") == "+":
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(ir["components"])
    return found


@pytest.mark.parametrize("sized", SIZED)
def test_length_sum_in_a_provide_method_carries_int_operands(sized):
    ir = compile_source(f"""
service Sizes {{ fn grow(x: {sized}) -> Int }}
component C provides sizes: Sizes {{
  provide sizes {{ fn grow(x) = x.length + 1 }}
}}
""", "length_operands_2261.rvl")
    sums = _sum_nodes(ir)
    assert len(sums) == 1, sums
    assert sums[0].get("operands") == "Int", (
        f"`x.length + 1` on {sized} in a provide method lowered without Int "
        f"operands: {sums[0]}")


def _refusal(source: str) -> str:
    with pytest.raises(RevlError) as info:
        compile_source(source, "length_field_2261.rvl")
    # the location prefix differs (line numbers); the message must not
    return re.sub(r"^\S+:\d+: ", "", str(info.value).strip().splitlines()[0])


def test_a_record_field_named_length_keeps_its_type_in_a_provide_method():
    in_fn = _refusal("""
type R = { length: Str }
fn f(r: R) -> Int { return r.length + 1 }
""")
    in_provide = _refusal("""
type R = { length: Str }
service S { fn g(r: R) -> Int }
component C provides s: S {
  provide s { fn g(r) = r.length + 1 }
}
""")
    assert in_fn == "operand of string `+` expects `Str`, got `Int`", in_fn
    assert in_provide == in_fn
