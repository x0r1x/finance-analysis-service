"""GOVERNANCE на версию объекта. COMPLIANCE этот модуль не включает."""

from __future__ import annotations

from datetime import datetime

import anyio

from finance_analysis.domain.errors import InvalidArgument


def put_object_governance(client, *, bucket: str, key: str, until: datetime) -> None:
    """Ставит GOVERNANCE до `until`. Режим COMPLIANCE сюда не передаётся."""

    client.put_object_retention(
        Bucket=bucket,
        Key=key,
        Retention={"Mode": "GOVERNANCE", "RetainUntilDate": until},
    )


class S3GovernanceRetainer:
    """Замок версии в бакете S3 или MinIO. Вызов — только GOVERNANCE."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        endpoint: str | None = None,
        region: str = "us-east-1",
        access_key: str,
        secret_key: str,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.endpoint = endpoint
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key

    def hold_key(self, key: str, *, until: datetime) -> None:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )
        full = f"{self.prefix}/{key}" if self.prefix else key
        put_object_governance(client, bucket=self.bucket, key=full, until=until)

    async def hold(self, key: str, *, mode: str, until: datetime) -> None:
        if mode != "GOVERNANCE":
            raise InvalidArgument("продукт ставит только GOVERNANCE")
        await anyio.to_thread.run_sync(lambda: self.hold_key(key, until=until))
