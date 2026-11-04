"""Задачи worker-а: выполнение операции, GC, сверка (§4.13.5, §4.14.4)."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import redis.asyncio as redis_async
from taskiq.kicker import AsyncKicker

from finance_analysis.adapters.queue import runtime as runtime_mod
from finance_analysis.adapters.queue.fairness import complete as fair_complete
from finance_analysis.adapters.queue.isolated import run_isolated
from finance_analysis.adapters.queue.names import BATCH, DLQ, INTERACTIVE, MAINTENANCE
from finance_analysis.adapters.queue.retry import full_jitter
from finance_analysis.application.gc import gc_incomplete
from finance_analysis.application.operations import append_event, is_terminal, read_op
from finance_analysis.domain.errors import FasError

RUN_TASK = "fas.run"
GC_TASK = "fas.gc_builds"
RECONCILE_TASK = "fas.reconcile_operations"
# Повторно ставить можно только идемпотентные виды. glossary.validate сюда
# не входит: повтор записал бы успех, не повторив запись релиза.
_IDEMPOTENT = {"book.load", "glossary.remap"}
_SERVICE_STAGES = {
    "glossary.transition": "perform_glossary_transition",
    "glossary.decide": "perform_proposal_decision",
    "glossary.remap": "perform_glossary_remap",
    "mapping.infer": "perform_mapping_infer",
}


def _rt():
    if runtime_mod.RUNTIME is None:
        raise RuntimeError("worker runtime не привязан")
    return runtime_mod.RUNTIME


def register_tasks(broker, *, schedules: bool, cron: str, settings=None) -> None:
    from finance_analysis.adapters.queue.learning_tasks import register_learning

    broker.register_task(run_operation, task_name=RUN_TASK)
    labels = {"queue_name": MAINTENANCE}
    register_learning(broker, schedules=schedules, settings=settings, batch=BATCH, maintenance=MAINTENANCE)
    if schedules:
        broker.register_task(gc_builds, task_name=GC_TASK, schedule=[{"cron": cron}], **labels)
        broker.register_task(
            reconcile_operations,
            task_name=RECONCILE_TASK,
            schedule=[{"cron": "* * * * *"}],
            **labels,
        )
    else:
        broker.register_task(gc_builds, task_name=GC_TASK, **labels)
        broker.register_task(reconcile_operations, task_name=RECONCILE_TASK, **labels)


def _payload_of(message) -> dict:
    if message.args and isinstance(message.args[0], dict):
        return message.args[0]
    if isinstance(message.kwargs, dict):
        return message.kwargs
    return {}


async def fail_exhausted(message, exception: BaseException) -> None:
    rt = _rt()
    payload = _payload_of(message)
    op_id = payload.get("op_id")
    reason = f"{type(exception).__name__}: {exception}"
    await _dlq(rt, op_id or "", reason, payload)
    if op_id:
        await _finish(rt, op_id, None, "failed", error={"code": "task_failed", "detail": reason})
        await _release_fair(rt, payload)


async def run_operation(payload: dict) -> dict:
    rt = _rt()
    op_id = payload["op_id"]
    if await _cancelled(rt, op_id):
        await _finish(rt, op_id, None, "cancelled")
        await _release_fair(rt, payload)
        return {"status": "cancelled"}
    if payload.get("needs_book_lock") and payload.get("job_id"):
        async with rt.locks.try_lock(f"book:{payload['job_id']}", rt.settings.lock_ttl_ms) as fence:
            if fence is None:
                await _reschedule(rt, payload)
                return {"status": "rescheduled"}
            return await _run_locked(rt, payload)
    return await _run_locked(rt, payload)


async def _run_locked(rt, payload: dict) -> dict:
    op_id = payload["op_id"]
    decision, attempt = await _begin_run(rt, op_id)
    if decision == "skip":
        return {"status": "skipped"}
    stop = asyncio.Event()
    beater = asyncio.create_task(_beat(rt, op_id, attempt, stop))
    terminal = decision == "poison"
    try:
        if decision == "poison":
            await _dlq(rt, op_id, "poison_task", payload)
            await _finish(
                rt,
                op_id,
                attempt,
                "failed",
                error={"code": "poison_task", "title": "Задача исчерпала попытки", "status": 500},
            )
            return {"status": "failed", "code": "poison_task"}
        result = await _stage(rt, payload, attempt)
        # Статус внутри результата домена (например active у релиза) — не статус
        # операции. Его забирает только поле result. Пропущенная запись (skipped)
        # уже закрыта шагом: здесь операцию успехом не помечаем.
        status = result.get("status")
        if status == "skipped":
            terminal = True
            return result
        if status not in {"succeeded", "failed", "cancelled"}:
            status = "succeeded" if result.get("ok", True) else "failed"
        error = result.get("error")
        if status == "failed" and isinstance(error, dict):
            await _finish(rt, op_id, attempt, status, error=error)
        elif status == "succeeded" and "result" in result:
            await _finish(rt, op_id, attempt, status, result=result["result"])
        else:
            await _finish(rt, op_id, attempt, status, result=result)
        terminal = True
        return result
    finally:
        stop.set()
        beater.cancel()
        await rt.redis.delete(f"fas:op:{op_id}:hb")
        if terminal:
            await _release_fair(rt, payload)


async def _begin_run(rt, op_id: str) -> tuple[str, int]:
    key = f"fas:op:{op_id}:attempt"
    attempt = int(await rt.redis.incr(key))
    raw = await rt.redis.get(f"fas:op:{op_id}:hb")
    if raw:
        text = raw.decode() if isinstance(raw, bytes) else str(raw)
        attempt_s, _, ts_s = text.partition(":")
        try:
            fresh = time.time() - float(ts_s) < max(rt.settings.op_heartbeat_sec * 2, 1)
            hb_attempt = int(attempt_s)
        except ValueError:
            fresh = False
            hb_attempt = attempt
        if fresh and hb_attempt != attempt:
            await rt.redis.decr(key)
            return "skip", hb_attempt
    limit = rt.settings.task_retry_max + 1
    if attempt > limit:
        return "poison", attempt
    # Закрытую операцию повтор задачи не открывает заново. Иначе проверка
    # зависших операций уже записала отказ, а поздний воркер переписал бы
    # книгу и мог бы поставить успех.
    try:
        current = await read_op(rt.store, op_id)
    except (FasError, OSError, ValueError, TypeError):
        current = None
    if current and is_terminal(current.get("status", "")):
        await rt.redis.decr(key)
        return "skip", attempt
    await append_event(rt.store, op_id, {"type": "run.started", "status": "running", "run_attempt": attempt})
    return "run", attempt


async def _beat(rt, op_id: str, attempt: int, stop: asyncio.Event) -> None:
    interval = rt.settings.op_heartbeat_sec
    ttl = max(int(interval * 2), 1)
    key = f"fas:op:{op_id}:hb"
    while not stop.is_set():
        await rt.redis.set(key, f"{attempt}:{time.time()}", ex=ttl)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue


async def _stage(rt, payload: dict, attempt: int) -> dict:
    if not payload.get("stage"):
        # Повтор без шага не выполняет работу. Проверка зависших операций
        # раньше ставила такую задачу снова, и этот возврат записывал
        # незавершённую загрузку как успех.
        from finance_analysis.application.service import _operation_problem
        from finance_analysis.domain.errors import Interrupted

        return {"ok": False, "status": "failed", "error": _operation_problem(Interrupted())}
    name = payload["stage"]
    args = payload.get("stage_args") or {}
    op_id = payload["op_id"]
    if name == "sleep":
        return await _sleep(rt, op_id, attempt, float(args.get("seconds") or 0))
    if name == "kill":
        await rt.redis.incr(f"fas:exec:{op_id}")
        os.kill(os.getpid(), signal.SIGKILL)
        return {"ok": False, "status": "failed"}
    if name == "oom":
        await rt.redis.incr(f"fas:exec:{op_id}")
        _oom()
        return {"ok": False, "status": "failed"}
    if name == "duckdb":
        return await _duckdb(rt, payload)
    if name == "once":
        commits = int(await rt.redis.incr(f"fas:commit:{op_id}"))
        return {"ok": True, "status": "succeeded", "commits": commits}
    if name == "marker":
        await rt.redis.set(f"fas:marker:{op_id}", "1", nx=True)
        await _sleep(rt, op_id, attempt, float(args.get("seconds") or 0))
        return {"ok": True, "status": "succeeded"}
    if name in _SERVICE_STAGES:
        return await _service_stage(name, args, op_id)
    return {"ok": True, "status": "succeeded"}


async def _service_stage(name: str, args: dict, op_id: str) -> dict:
    """Выполняет шаг глоссария или подбора на сервисе воркера.

    `name` — имя шага из задачи. `args` — аргументы, которые API положило
    в `stage_args`. `op_id` — операция. Идентификатор передаётся в метод,
    чтобы запись головы не случилась после отмены и после того, как
    проверка зависших операций уже закрыла операцию.

    Успех возвращает словарь с полем `result`: туда кладётся ответ домена,
    даже если в нём есть свой `status` (например `active`). Иначе проверка
    очереди приняла бы статус релиза за статус операции. Ошибка возвращается
    как провал с телом problem+json и не поднимается наружу: очередь не
    должна повторять уже записанный отказ. Пропуск записи (`skipped`) тоже
    не считается успехом.
    """

    from finance_analysis.adapters.queue.learning_tasks import _mine_service
    from finance_analysis.application.service import _operation_problem

    service = await _mine_service()
    method = getattr(service, _SERVICE_STAGES[name])
    call = dict(args)
    call["op_id"] = op_id
    try:
        value = await method(**call)
    except Exception as exc:  # noqa: BLE001 — ошибка шага закрывает операцию и не уходит в повтор Taskiq
        return {"ok": False, "status": "failed", "error": _operation_problem(exc)}
    if isinstance(value, dict) and value.get("skipped"):
        return {"ok": True, "status": "skipped"}
    return {"ok": True, "status": "succeeded", "result": value}


async def _sleep(rt, op_id: str, attempt: int, seconds: float) -> dict:
    await rt.redis.incr(f"fas:exec:{op_id}")
    await rt.redis.rpush(f"fas:start:{op_id}", str(time.time()))
    flagged = False
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    try:
        while True:
            if await _overlap(rt, op_id, attempt) and not flagged:
                await rt.redis.incr(f"fas:op:{op_id}:parallel")
                flagged = True
            if loop.time() >= deadline:
                return {"ok": True, "status": "succeeded"}
            if await _cancelled(rt, op_id):
                return {"ok": False, "status": "cancelled"}
            await asyncio.sleep(min(0.05, max(deadline - loop.time(), 0)))
    finally:
        await rt.redis.hdel(f"fas:op:{op_id}:runners", str(attempt))


async def _overlap(rt, op_id: str, attempt: int) -> bool:
    """Другой живой запуск — параллельный дубль."""
    key = f"fas:op:{op_id}:runners"
    now = time.time()
    await rt.redis.hset(key, str(attempt), str(now))
    await rt.redis.expire(key, 300)
    window = max(rt.settings.op_heartbeat_sec * 2, 1)
    others = await rt.redis.hgetall(key)
    for name, raw in others.items():
        label = name.decode() if isinstance(name, bytes) else str(name)
        if label == str(attempt):
            continue
        text = raw.decode() if isinstance(raw, bytes) else str(raw)
        try:
            if now - float(text) < window:
                return True
        except ValueError:
            continue
    return False


def _write_cgroup(path: Path, text: str) -> None:
    payload = text if text.endswith("\n") else f"{text}\n"
    try:
        path.write_text(payload)
    except OSError:
        subprocess.run(
            ["sudo", "-n", "tee", str(path)],
            input=payload,
            text=True,
            check=True,
            stdout=subprocess.DEVNULL,
        )


def _enter_cgroup(cgroup: str) -> None:
    """Переносит текущий процесс в cgroup. На чужом sibling это может сделать только root."""

    _write_cgroup(Path(cgroup, "cgroup.procs"), str(os.getpid()))


def _oom() -> None:
    """Входит в cgroup и только потом ставит memory.max, чтобы OOM остался внутри него."""

    raw = os.environ.get("FAS_OOM_CGROUP")
    if not raw:
        raise RuntimeError("FAS_OOM_CGROUP не задан")
    cgroup = Path(raw)
    _enter_cgroup(raw)
    group = cgroup / "memory.oom.group"
    if group.is_file():
        _write_cgroup(group, "0")
    swap = cgroup / "memory.swap.max"
    if swap.is_file():
        _write_cgroup(swap, "0")
    _write_cgroup(cgroup / "memory.max", os.environ.get("FAS_OOM_BYTES") or "268435456")
    blobs: list[bytearray] = []
    while True:
        blobs.append(bytearray(8 * 1024 * 1024))


async def _duckdb(rt, payload: dict) -> dict:
    op_id = payload["op_id"]
    cancel = asyncio.Event()

    async def _watch() -> None:
        while not cancel.is_set():
            if await _cancelled(rt, op_id):
                cancel.set()
                return
            await asyncio.sleep(0.05)

    watcher = asyncio.create_task(_watch())
    try:
        return await run_isolated(
            "duckdb_scan",
            {"rounds": int((payload.get("stage_args") or {}).get("rounds") or 10**12)},
            rt.settings.heavy_stage_timeout_sec,
            grace=rt.settings.heavy_stage_kill_grace_sec,
            memory_mb=rt.settings.heavy_stage_memory_mb,
            cancelled=cancel.is_set,
        )
    finally:
        watcher.cancel()


async def _cancelled(rt, op_id: str) -> bool:
    if await rt.redis.exists(f"fas:op:{op_id}:cancel"):
        return True
    try:
        current = await read_op(rt.store, op_id)
    except (FasError, OSError, ValueError, TypeError):
        return False
    return current.get("status") == "cancelled"


async def _finish(rt, op_id: str, attempt: int | None, status: str, **fields) -> None:
    if attempt is not None:
        current = int(await rt.redis.get(f"fas:op:{op_id}:attempt") or 0)
        if current != attempt:
            return
    try:
        operation = await read_op(rt.store, op_id)
    except (FasError, OSError, ValueError, TypeError):
        return
    if is_terminal(operation.get("status", "")):
        return
    await append_event(rt.store, op_id, {"status": status, **fields})
    try:
        await rt.redis.publish(f"fas:op:{op_id}", status)
    except redis_async.RedisError:
        return


async def _dlq(rt, op_id: str, reason: str, payload: dict) -> None:
    await rt.redis.xadd(
        DLQ,
        {"op_id": op_id, "reason": reason, "payload": json.dumps(payload, ensure_ascii=False)},
        maxlen=rt.settings.taskiq_stream_maxlen,
        approximate=True,
    )


async def _reschedule(rt, payload: dict) -> None:
    delay = full_jitter(rt.settings.task_retry_base_sec, rt.settings.task_retry_max_delay_sec, 1)
    when = datetime.now(UTC) + timedelta(seconds=delay)
    kicker = AsyncKicker(RUN_TASK, rt.broker, {}).with_labels(queue_name=payload.get("queue") or INTERACTIVE)
    await kicker.schedule_by_time(rt.schedule, when, payload)


async def _release_fair(rt, payload: dict) -> None:
    queue = payload.get("queue")
    user = payload.get("user_id")
    if queue != INTERACTIVE or not user:
        return
    nxt = await fair_complete(rt.redis, queue, user)
    if nxt:
        await _kick(rt.broker, nxt)


async def _kick(broker, payload: dict) -> None:
    task = broker.find_task(RUN_TASK)
    await task.kicker().with_labels(queue_name=payload.get("queue") or INTERACTIVE).kiq(payload)


async def gc_builds() -> dict:
    rt = _rt()
    async with rt.locks.try_lock("gc", rt.settings.lock_ttl_ms) as fence:
        if fence is None:
            return {"skipped": "locked"}

        async def locked(job: str) -> bool:
            return bool(await rt.redis.exists(f"fas:lock:book:{job}"))

        return await gc_incomplete(
            rt.store,
            max_age_s=rt.settings.gc_age_seconds(),
            is_locked=locked,
        )


def _resumable(operation: dict) -> bool:
    """Операцию можно продолжить, если в нагрузке есть шаг и повтор безопасен.

    `operation` — тело операции. Повторять можно `book.load` и
    `glossary.remap`, а также операцию с полем `idempotent`. Без шага
    повтор нечего выполнять, поэтому метод возвращает ложь и проверку
    зависших операций не просит ставить пустую задачу.
    """

    payload = operation.get("payload") or {}
    if not payload.get("stage"):
        return False
    return operation.get("kind") in _IDEMPOTENT or bool(payload.get("idempotent"))


async def _lease_live(rt, operation: dict) -> bool:
    """Жива ли аренда процесса, которому принадлежит операция.

    `operation` — тело операции. Процесс API пишет ключ `fas:api:{owner}`
    и обновляет его, пока сам жив. Если владельца нет или ключ истёк,
    метод возвращает ложь. Тогда операцию без шага можно закрыть.
    """

    owner = operation.get("owner")
    if not owner:
        return False
    return bool(await rt.redis.exists(f"fas:api:{owner}"))


async def reconcile_operations() -> dict:
    """Закрывает или продолжает операции без свежей метки живости.

    Метод обходит операции в статусе `running`. Свежую метку
    `fas:op:{id}:hb` не трогает. Если метки нет или она старше
    `OP_STALE_SEC`, дальше решает аренда владельца и шаг в нагрузке.
    Живая аренда без шага значит, что процесс API ещё может грузить
    книгу: такую операцию метод оставляет. Идемпотентную операцию со
    шагом ставит в очередь снова. Операцию без шага закрывает как
    `interrupted`, чтобы пустой повтор не записали успехом. Остальные
    закрывает как `dependency_unavailable`. Возвращает числа `resent`
    и `closed`.
    """

    from finance_analysis.application.service import _operation_problem
    from finance_analysis.domain.errors import Interrupted

    rt = _rt()
    closed = 0
    resent = 0
    async for item in rt.store.list("operations"):
        if not item.key.endswith("/op.json"):
            continue
        op_id = item.key.split("/")[1]
        try:
            operation = await read_op(rt.store, op_id)
        except (FasError, OSError, ValueError, TypeError):
            operation = None
        if not operation or operation.get("status") != "running":
            continue
        if not await _stale(rt, op_id):
            continue
        payload = dict(operation.get("payload") or {})
        if await _lease_live(rt, operation) and not payload.get("stage"):
            continue
        if _resumable(operation):
            payload.setdefault("op_id", op_id)
            payload.setdefault("kind", operation.get("kind"))
            payload.setdefault("queue", payload.get("queue") or MAINTENANCE)
            payload.setdefault("user_id", (operation.get("actor") or {}).get("user_id"))
            await _kick(rt.broker, payload)
            resent += 1
            continue
        if not payload.get("stage"):
            await _finish(rt, op_id, None, "failed", error=_operation_problem(Interrupted()))
            closed += 1
            continue
        await _finish(
            rt,
            op_id,
            None,
            "failed",
            error={"code": "dependency_unavailable", "title": "Нет heartbeat операции"},
        )
        closed += 1
    return {"resent": resent, "closed": closed}


async def _stale(rt, op_id: str) -> bool:
    raw = await rt.redis.get(f"fas:op:{op_id}:hb")
    if not raw:
        created = await _created_age(rt, op_id)
        return created is None or created >= rt.settings.op_stale_sec
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    _attempt, _, ts_s = text.partition(":")
    try:
        age = time.time() - float(ts_s)
    except ValueError:
        return True
    return age >= rt.settings.op_stale_sec


async def _created_age(rt, op_id: str) -> float | None:
    try:
        operation = await read_op(rt.store, op_id)
    except (FasError, OSError, ValueError, TypeError):
        return None
    raw = operation.get("created_at")
    if not raw:
        return None
    try:
        stamp = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return (datetime.now(UTC) - stamp).total_seconds()
