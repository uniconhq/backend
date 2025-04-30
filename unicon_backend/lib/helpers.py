from collections import defaultdict
from collections.abc import Callable, Sequence
from threading import Timer


def partition[T](
    predicate: Callable[[T], bool], xs: Sequence[T]
) -> tuple[Sequence[T], Sequence[T]]:
    """Partition a sequence into two sequences based on a predicate"""
    return [x for x in xs if predicate(x)], [x for x in xs if not predicate(x)]


def create_multi_index[T, K, V](
    items: list[T],
    key_fn: Callable[[T], K],
    value_fn: Callable[[T], V],
    filter_fn: Callable[[T], bool] = lambda _: True,
) -> defaultdict[K, list[V]]:
    """Create a one-to-many mapping index from a single list of items"""
    index = defaultdict(list)
    for item in filter(filter_fn, items):
        index[key_fn(item)].append(value_fn(item))
    return index


def create_and_start_timer(time, fn):
    timer = Timer(time, fn)
    timer.start()
    return timer
