from collections import defaultdict
from typing import Iterable

from langgraph.store.base import Op


def _group_ops(ops: Iterable[Op]) -> tuple[dict[type, list[tuple[int, Op]]], int]:
    """Group operations by type for batch processing."""
    grouped_ops: dict[type, list[tuple[int, Op]]] = defaultdict(list)
    tot = 0
    for idx, op in enumerate(ops):
        grouped_ops[type(op)].append((idx, op))
        tot += 1
    return grouped_ops, tot


def _namespace_to_text(
    namespace: tuple[str, ...]
) -> str:
    return "_".join(namespace)
