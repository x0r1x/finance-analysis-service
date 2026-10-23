"""ObjectStorePort: local (flock + CAS) и s3 (opendal AsyncOperator)."""

from __future__ import annotations

import fcntl
import hashlib
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import anyio
import opendal
from opendal.exceptions import AlreadyExists as OdalExists
from opendal.exceptions import ConditionNotMatch
from opendal.exceptions import NotFound as OdalNotFound

from finance_analysis.application.ports import ObjMeta
from finance_analysis.domain.errors import (
    AlreadyExists,
    DependencyUnavailable,
    InvalidId,
    NotFound,
    PreconditionFailed,
)
from finance_analysis.domain.ids import ulid as check_ulid
from finance_analysis.settings import Settings

_READ_ONLY = "хранилище в режиме только чтения"


def _reject_key(key: str) -> str:
    if not isinstance(key, str) or not key or key.startswith("/") or "\\" in key:
        raise InvalidId("ключ объекта недопустим")
    parts = key.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise InvalidId("ключ объекта недопустим")
    return key


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _meta(key: str, data: bytes, mtime: datetime | None, etag: str | None) -> ObjMeta:
    return ObjMeta(key=key, size=len(data) if data is not None else 0, etag=etag, mtime=mtime)


class _StoreBase:
    def __init__(self, *, read_only: bool) -> None:
        self.read_only = read_only

    def _guard(self) -> None:
        if self.read_only:
            raise DependencyUnavailable(_READ_ONLY)

    async def selftest(self) -> None:
        token_key = f"_meta/selftest/{check_ulid(str(__import__('ulid').ULID()))}"
        first = await self.put_if_absent(token_key, b"a")
        try:
            await self.put_if_absent(token_key, b"b")
        except AlreadyExists:
            pass
        else:
            raise DependencyUnavailable("put_if_absent не отклонил повтор")
        try:
            await self.put_if_match(token_key, b"c", "deadbeef")
        except PreconditionFailed:
            pass
        else:
            raise DependencyUnavailable("put_if_match принял чужой токен")
        if not first.etag:
            raise DependencyUnavailable("хранилище не вернуло токен условной записи")
        await self.put_if_match(token_key, b"d", first.etag)
        await self.delete_prefix(token_key)


class LocalStore(_StoreBase):
    backend = "local"
    conditional_writes = "flock"

    def __init__(self, root: Path, *, read_only: bool = False) -> None:
        super().__init__(read_only=read_only)
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.url = self.root.as_uri()
        self._op = opendal.AsyncOperator("fs", root=str(self.root))

    def physical(self, key: str) -> str:
        return str(self._path(key))

    def _path(self, key: str) -> Path:
        safe = _reject_key(key)
        path = (self.root / safe).resolve()
        if not path.is_relative_to(self.root):
            raise InvalidId("ключ выходит за корень хранилища")
        return path

    async def get(self, key: str) -> bytes:
        try:
            return await self._op.read(_reject_key(key))
        except OdalNotFound as exc:
            raise NotFound(key) from exc

    async def stat(self, key: str) -> ObjMeta | None:
        path = self._path(key)
        if not path.is_file():
            return None
        data = path.read_bytes()
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        return ObjMeta(key=key, size=len(data), etag=_hash(data), mtime=mtime)

    async def put(self, key: str, data: bytes) -> ObjMeta:
        self._guard()
        return await anyio.to_thread.run_sync(self._put_sync, key, data)

    async def put_if_absent(self, key: str, data: bytes) -> ObjMeta:
        self._guard()
        return await anyio.to_thread.run_sync(self._put_absent_sync, key, data)

    async def put_if_match(self, key: str, data: bytes, token: str) -> ObjMeta:
        self._guard()
        return await anyio.to_thread.run_sync(self._put_match_sync, key, data, token)

    def _lock(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_name(path.name + ".lock")
        handle = open(lock_path, "a+", encoding="utf-8")  # noqa: SIM115 — закрывает вызывающий после LOCK_UN
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def _replace(self, path: Path, data: bytes) -> None:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)

    def _put_sync(self, key: str, data: bytes) -> ObjMeta:
        path = self._path(key)
        handle = self._lock(path)
        try:
            self._replace(path, data)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        return ObjMeta(key=key, size=len(data), etag=_hash(data), mtime=datetime.now(UTC))

    def _put_absent_sync(self, key: str, data: bytes) -> ObjMeta:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(path, flags, 0o644)
        except FileExistsError as exc:
            raise AlreadyExists(key) from exc
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        return ObjMeta(key=key, size=len(data), etag=_hash(data), mtime=datetime.now(UTC))

    def _put_match_sync(self, key: str, data: bytes, token: str) -> ObjMeta:
        path = self._path(key)
        handle = self._lock(path)
        try:
            if not path.is_file():
                raise PreconditionFailed(f"нет объекта {key}")
            current = _hash(path.read_bytes())
            if current != token:
                raise PreconditionFailed("токен не совпал", extra={"etag": current})
            self._replace(path, data)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        return ObjMeta(key=key, size=len(data), etag=_hash(data), mtime=datetime.now(UTC))

    async def list(self, prefix: str) -> AsyncIterator[ObjMeta]:
        safe = prefix.strip("/")
        if safe:
            _reject_key(safe) if "/" in safe or safe not in {".", ".."} else None
            if ".." in safe.split("/"):
                raise InvalidId("префикс недопустим")
        try:
            listed = await self._op.list(safe + "/" if safe else "", recursive=True)
        except OdalNotFound:
            return
        async for entry in listed:
            meta = entry.metadata
            if meta is not None and (meta.is_dir or str(entry.path).endswith("/")):
                continue
            rel = entry.path.lstrip("/")
            if safe and not (rel == safe or rel.startswith((safe + "/", safe))):
                # list may already be scoped
                pass
            name = rel.rsplit("/", 1)[-1]
            if not rel or rel.endswith("/") or name.endswith(".lock") or name.startswith("."):
                continue
            stat = await self.stat(rel)
            if stat is not None:
                yield stat

    async def delete_prefix(self, prefix: str) -> int:
        self._guard()
        keys = [item.key async for item in self.list(prefix)]
        if prefix and (self.root / prefix).is_file():
            keys.append(prefix)
        count = 0
        for key in dict.fromkeys(keys):
            path = self._path(key)
            if path.is_file():
                path.unlink()
                count += 1
            lock = path.with_name(path.name + ".lock")
            if lock.is_file():
                lock.unlink()
        return count


class S3Store(_StoreBase):
    backend = "s3"
    conditional_writes = "native"

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        endpoint: str | None,
        region: str,
        access_key: str,
        secret_key: str,
        read_only: bool = False,
    ) -> None:
        super().__init__(read_only=read_only)
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.endpoint = endpoint
        self.region = region
        self.url = f"s3://{bucket}/{self.prefix}" if self.prefix else f"s3://{bucket}"
        kwargs = {
            "bucket": bucket,
            "region": region,
            "access_key_id": access_key,
            "secret_access_key": secret_key,
            "root": self.prefix,
        }
        if endpoint:
            kwargs["endpoint"] = endpoint
            kwargs["enable_virtual_host_style"] = "false"
        self._op = opendal.AsyncOperator("s3", **kwargs)

    def physical(self, key: str) -> str:
        _reject_key(key)
        base = f"s3://{self.bucket}/{self.prefix}" if self.prefix else f"s3://{self.bucket}"
        return f"{base}/{key}"

    async def get(self, key: str) -> bytes:
        try:
            return bytes(await self._op.read(_reject_key(key)))
        except OdalNotFound as exc:
            raise NotFound(key) from exc

    async def stat(self, key: str) -> ObjMeta | None:
        try:
            meta = await self._op.stat(_reject_key(key))
        except OdalNotFound:
            return None
        etag = meta.etag
        if isinstance(etag, str):
            etag = etag.strip('"')
        return ObjMeta(
            key=key,
            size=int(meta.content_length or 0),
            etag=etag,
            mtime=meta.last_modified,
        )

    async def put(self, key: str, data: bytes) -> ObjMeta:
        self._guard()
        await self._op.write(_reject_key(key), data)
        stat = await self.stat(key)
        assert stat is not None
        return stat

    async def put_if_absent(self, key: str, data: bytes) -> ObjMeta:
        self._guard()
        try:
            await self._op.write(_reject_key(key), data, if_not_exists=True)
        except (ConditionNotMatch, OdalExists) as exc:
            raise AlreadyExists(key) from exc
        stat = await self.stat(key)
        assert stat is not None
        return stat

    async def put_if_match(self, key: str, data: bytes, token: str) -> ObjMeta:
        self._guard()
        quoted = token if token.startswith('"') else f'"{token}"'
        last_error: Exception | None = None
        for candidate in (token, quoted):
            try:
                await self._op.write(_reject_key(key), data, if_match=candidate)
                stat = await self.stat(key)
                assert stat is not None
                return stat
            except (ConditionNotMatch, OdalNotFound, OdalExists) as exc:
                last_error = exc
                continue
        raise PreconditionFailed("токен не совпал", extra={"etag": token}) from last_error

    async def list(self, prefix: str) -> AsyncIterator[ObjMeta]:
        safe = _reject_key(prefix) if prefix else ""
        try:
            listed = await self._op.list(safe, recursive=True)
        except OdalNotFound:
            return
        async for entry in listed:
            meta = entry.metadata
            rel = entry.path.lstrip("/")
            if not rel or rel.endswith("/"):
                continue
            if meta is not None and meta.is_dir:
                continue
            etag = meta.etag if meta is not None else None
            if isinstance(etag, str):
                etag = etag.strip('"')
            yield ObjMeta(
                key=rel,
                size=int(meta.content_length or 0) if meta is not None else 0,
                etag=etag,
                mtime=meta.last_modified if meta is not None else None,
            )

    async def delete_prefix(self, prefix: str) -> int:
        self._guard()
        count = 0
        async for item in self.list(prefix):
            await self._op.delete(item.key)
            count += 1
        if prefix:
            try:
                await self._op.delete(_reject_key(prefix))
                count += 1
            except OdalNotFound:
                pass
        return count


def build_storage(settings: Settings) -> LocalStore | S3Store:
    if settings.s3_enabled:
        return S3Store(
            bucket=settings.fas_s3_bucket or "",
            prefix=settings.fas_s3_prefix,
            endpoint=settings.fas_s3_endpoint,
            region=settings.fas_s3_region,
            access_key=settings.fas_s3_access_key or "",
            secret_key=settings.fas_s3_secret_key or "",
            read_only=settings.fas_read_only,
        )
    root = Path(settings.fas_data_dir).expanduser().resolve() / settings.fas_s3_prefix
    return LocalStore(root, read_only=settings.fas_read_only)


async def open_storage(settings: Settings) -> LocalStore | S3Store:
    store = build_storage(settings)
    try:
        await store.selftest()
    except Exception as exc:
        if store.backend == "s3":
            raise DependencyUnavailable(f"самотест условных записей не прошёл: {exc}") from exc
        raise
    return store


class BrokenConditionalStore(S3Store):
    """Тестовый двойник: S3 без условных записей."""

    async def put_if_match(self, key: str, data: bytes, token: str) -> ObjMeta:
        raise DependencyUnavailable("conditional writes unsupported")

    async def selftest(self) -> None:
        try:
            await super().selftest()
        except Exception as exc:
            raise DependencyUnavailable("самотест условных записей не прошёл") from exc
        raise DependencyUnavailable("самотест обязан был упасть")
