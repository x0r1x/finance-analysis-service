"""NumPy brute force по матрице в памяти (≤ ~10⁵ векторов, §4.5). LanceDB/Milvus — тот же порт."""

from __future__ import annotations

import anyio
import numpy as np


class NumpyIndex:
    def __init__(self) -> None:
        self._matrix = np.zeros((0, 0), dtype=np.float32)
        self._payloads: list[dict] = []

    async def replace(self, vectors: list[list[float]], payloads: list[dict]) -> None:
        def _build():
            if not vectors:
                return np.zeros((0, 0), dtype=np.float32)
            matrix = np.asarray(vectors, dtype=np.float32)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            return matrix / np.where(norms == 0, 1.0, norms)

        self._matrix = await anyio.to_thread.run_sync(_build)
        self._payloads = list(payloads)

    async def size(self) -> int:
        return len(self._payloads)

    async def search(self, vectors: list[list[float]], k: int) -> list[list[tuple[float, dict]]]:
        if not vectors or not self._payloads:
            return [[] for _ in vectors]
        matrix = self._matrix
        payloads = self._payloads

        def _search():
            query = np.asarray(vectors, dtype=np.float32)
            if query.shape[1] != matrix.shape[1]:
                return [[] for _ in vectors]
            norms = np.linalg.norm(query, axis=1, keepdims=True)
            query = query / np.where(norms == 0, 1.0, norms)
            scores = query @ matrix.T
            top = min(k, matrix.shape[0])
            idx = np.argpartition(-scores, top - 1, axis=1)[:, :top]
            out = []
            for row, picks in enumerate(idx):
                ranked = sorted(picks, key=lambda j: -scores[row, j])
                out.append([(float(scores[row, j]), payloads[j]) for j in ranked])
            return out

        return await anyio.to_thread.run_sync(_search)
