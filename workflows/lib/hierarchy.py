"""
Resolves the parent/child hierarchy hidden in a flat USITC export.

Both hts_base and rule come from a flat JSON list where nesting is implied by
an `indent` field, not an explicit parent pointer. A row's ancestors matter:
a heading ("0101") or a headerless "superior" row ("Articles the product of
Canada:") carries text or legal scope that its descendants depend on -- most
visibly, ~56% of hts_base leaf rows have no rate of their own and inherit one
from their nearest dutiable ancestor, and Chapter 99 exclusion clauses are
often stated once on an ancestor row rather than repeated on every child.

`resolve(rows)` walks the list in document order with an indent-keyed stack
and yields one `Node` per input row, each knowing its nearest ancestor *that
has its own htsno* (headerless rows are never a valid parent_hts -- they have
nothing to be a foreign key to) plus the full ancestor-to-self text chain.
"""

from dataclasses import dataclass, field


@dataclass
class Node:
    htsno: str  # "" for a headerless scaffolding row -- never persisted as its own DB row
    indent: int
    description: str
    superior: bool
    raw: dict
    parent_htsno: str | None  # nearest ancestor with a non-empty htsno, if any
    context_text: str  # ancestor scaffolding/description chain + own description, in order


@dataclass
class _StackEntry:
    indent: int
    htsno: str  # "" if this level has no htsno of its own (a scaffolding row)
    description: str


def resolve(rows: list[dict]) -> list[Node]:
    stack: list[_StackEntry] = []
    nodes: list[Node] = []

    for row in rows:
        indent = int(row["indent"])
        htsno = (row.get("htsno") or "").strip()
        description = (row.get("description") or "").strip()

        while stack and stack[-1].indent >= indent:
            stack.pop()

        parent_htsno = next(
            (entry.htsno for entry in reversed(stack) if entry.htsno), None
        )
        context_parts = [entry.description for entry in stack if entry.description]
        context_parts.append(description)
        context_text = " ".join(p for p in context_parts if p)

        nodes.append(
            Node(
                htsno=htsno,
                indent=indent,
                description=description,
                superior=bool(row.get("superior")),
                raw=row,
                parent_htsno=parent_htsno,
                context_text=context_text,
            )
        )

        stack.append(_StackEntry(indent=indent, htsno=htsno, description=description))

    return nodes
