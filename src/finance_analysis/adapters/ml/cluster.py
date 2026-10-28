"""HDBSCAN по эмбеддингам unknown-строк (§5.10.4). Шум остаётся -1 и в кластер не навязывается."""

from __future__ import annotations

import anyio
import numpy as np


class HdbscanCluster:
    async def cluster(self, vectors: list[list[float]], *, min_cluster_size: int) -> list[int]:
        if len(vectors) < max(min_cluster_size, 2):
            return [-1 for _ in vectors]

        def _run() -> list[int]:
            from sklearn.cluster import HDBSCAN

            matrix = np.asarray(vectors, dtype=np.float64)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            matrix = matrix / np.where(norms == 0, 1.0, norms)
            labels = HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean", copy=True).fit_predict(matrix)
            return [int(label) for label in labels]

        return await anyio.to_thread.run_sync(_run)
