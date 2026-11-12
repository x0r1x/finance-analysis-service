"""Повтор temporary на записи S3. Живой MinIO не нужен."""

from types import SimpleNamespace

import pytest
from opendal.exceptions import ConditionNotMatch, Unexpected
from opendal.exceptions import NotFound as OdalNotFound

from finance_analysis.adapters.storage.store import S3Store
from finance_analysis.domain.errors import AlreadyExists, DependencyUnavailable


def _store(op) -> S3Store:
    store = S3Store.__new__(S3Store)
    store.read_only = False
    store._op = op
    return store


class _Op:
    def __init__(self, script: list) -> None:
        self.script = list(script)
        self.objects: dict[str, bytes] = {}
        self.writes: list[dict] = []

    async def write(self, key: str, data: bytes, **conds) -> None:
        self.writes.append({"key": key, "data": data, **conds})
        step = self.script.pop(0)
        if step == "store-temporary":
            self.objects[key] = data
            raise Unexpected("Unexpected (temporary) at write")
        if step == "temporary":
            raise Unexpected("Unexpected (temporary) at write")
        if step == "persistent":
            raise Unexpected("Unexpected (persistent) at write")
        if step == "conflict":
            raise ConditionNotMatch("condition not match")
        if step == "ok":
            self.objects[key] = data
            return
        raise AssertionError(step)

    async def read(self, key: str) -> bytes:
        if key not in self.objects:
            raise OdalNotFound(key)
        return self.objects[key]

    async def stat(self, key: str):
        if key not in self.objects:
            raise OdalNotFound(key)
        data = self.objects[key]
        return SimpleNamespace(etag='"abc"', content_length=len(data), last_modified=None)


async def test_temporary_then_same_bytes_is_success():
    op = _Op(["store-temporary", "conflict"])
    store = _store(op)
    meta = await store.put_if_absent("fas/ops/000002.json", b"same")
    assert meta.key == "fas/ops/000002.json"
    assert await store.get("fas/ops/000002.json") == b"same"
    assert all(item.get("if_not_exists") is True for item in op.writes)


async def test_first_conflict_without_blip_is_already_exists():
    op = _Op(["conflict"])
    op.objects["k"] = b"other"
    store = _store(op)
    with pytest.raises(AlreadyExists):
        await store.put_if_absent("k", b"ours")
    assert len(op.writes) == 1


async def test_blip_then_different_bytes_is_already_exists():
    op = _Op(["temporary"])
    op.objects["k"] = b"other"
    store = _store(op)
    with pytest.raises(AlreadyExists):
        await store.put_if_absent("k", b"ours")
    assert len(op.writes) == 1


async def test_temporary_and_still_missing_is_dependency_unavailable():
    op = _Op(["temporary", "temporary", "temporary"])
    store = _store(op)
    with pytest.raises(DependencyUnavailable) as caught:
        await store.put_if_absent("k", b"ours")
    assert caught.value.retryable is True
    assert len(op.writes) == 3


async def test_persistent_unexpected_is_not_retried():
    op = _Op(["persistent"])
    store = _store(op)
    with pytest.raises(Unexpected):
        await store.put_if_absent("k", b"ours")
    assert len(op.writes) == 1


async def test_put_retries_temporary_then_succeeds():
    op = _Op(["temporary", "ok"])
    store = _store(op)
    meta = await store.put("k", b"body")
    assert meta.size == 4
    assert len(op.writes) == 2
    assert "if_not_exists" not in op.writes[0]


async def test_put_if_match_retries_temporary_then_succeeds():
    op = _Op(["temporary", "ok"])
    store = _store(op)
    meta = await store.put_if_match("k", b"body", "abc")
    assert meta.etag == "abc"
    assert op.writes[0]["if_match"] == "abc"
    assert len(op.writes) == 2
