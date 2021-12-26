import collections
import typing


class FrozenDict(collections.Mapping):
    def __init__(self, *args, **kwargs) -> None:
        self._d = dict(*args, **kwargs)
        self._hash = None

    def __repr__(self) -> str:
        return repr(self._d)

    def __iter__(self) -> typing.Iterator:
        return iter(self._d)

    def __len__(self) -> int:
        return len(self._d)

    def __getitem__(self, key: typing.Any) -> typing.Any:
        return self._d[key]

    def __hash__(self) -> int:
        # It would have been simpler and maybe more obvious to
        # use hash(tuple(sorted(self._d.iteritems()))) from this discussion
        # so far, but this solution is O(n). I don't know what kind of
        # n we are going to run into, but sometimes it's hard to resist the
        # urge to optimize when it will gain improved algorithmic performance.
        if self._hash is None:
            hash_ = 0

            for pair in self.items():
                hash_ ^= hash(pair)

            self._hash = hash_

        return self._hash
