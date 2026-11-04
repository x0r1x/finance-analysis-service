"""Голова пишется по токену, прочитанному в момент записи."""

from __future__ import annotations

import json

import pytest

from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.application import keys
from finance_analysis.application.service import FasService
from finance_analysis.domain.errors import PreconditionFailed


def _body(state_seq: int, fence: int) -> dict:
    return {
        "build_key": "build",
        "state_seq": state_seq,
        "derive_key": "derive",
        "versions": {},
        "mdl_version": "1",
        "fence": fence,
    }


@pytest.mark.asyncio
async def test_stale_token_does_not_block_a_newer_fence(tmp_path):
    store = LocalStore(tmp_path)
    service = FasService.__new__(FasService)
    service.store = store
    job = "a" * 64
    key = keys.head_key(job)
    await store.put_if_absent(key, json.dumps(_body(1, 1)).encode())
    stale = (await store.stat(key)).etag
    await store.put_if_match(key, json.dumps(_body(2, 1)).encode(), stale)
    await service._publish_head(job, _body(3, 2), stale, 2)
    saved = json.loads(await store.get(key))
    assert saved["state_seq"] == 3
    assert saved["fence"] == 2
    with pytest.raises(PreconditionFailed, match="устаревший fencing-токен"):
        await service._publish_head(job, _body(4, 1), None, 1)
