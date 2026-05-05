"""
Simula AWS S3 usando filesystem local.
Operações: put_object, get_object, list_objects, delete_object.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import STORAGE_PATH
from logger import get_logger

log = get_logger("s3_sim")


class S3Bucket:
    """
    Simula um bucket S3 mapeado para um diretório local.
    Arquivos são armazenados como JSON com metadados.
    """

    def __init__(self, bucket_name: str, base_path: Path = STORAGE_PATH) -> None:
        self.bucket_name = bucket_name
        self.base_path = base_path / bucket_name
        self.base_path.mkdir(parents=True, exist_ok=True)
        log.debug("s3_bucket_init", bucket=bucket_name, path=str(self.base_path))

    def _key_to_path(self, key: str) -> Path:
        safe_key = key.replace("/", "__").replace(":", "-")
        return self.base_path / f"{safe_key}.json"

    def put_object(
        self, key: str, body: Any, metadata: dict[str, str] | None = None
    ) -> str:
        """Salva objeto. Retorna URI simulada."""
        path = self._key_to_path(key)
        envelope = {
            "key": key,
            "bucket": self.bucket_name,
            "metadata": metadata or {},
            "body": body,
        }
        path.write_text(
            json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        uri = f"s3://{self.bucket_name}/{key}"
        log.info("s3_put", bucket=self.bucket_name, key=key, path=str(path))
        return uri

    def get_object(self, key: str) -> Any:
        """Retorna body do objeto ou None se não existir."""
        path = self._key_to_path(key)
        if not path.exists():
            log.warning("s3_get_not_found", bucket=self.bucket_name, key=key)
            return None
        envelope = json.loads(path.read_text(encoding="utf-8"))
        return envelope.get("body")

    def list_objects(self, prefix: str = "") -> list[str]:
        """Lista keys com prefixo opcional."""
        keys = []
        for file in self.base_path.glob("*.json"):
            envelope = json.loads(file.read_text(encoding="utf-8"))
            key = envelope.get("key", "")
            if key.startswith(prefix):
                keys.append(key)
        return sorted(keys)

    def delete_object(self, key: str) -> bool:
        """Remove objeto. Retorna True se existia."""
        path = self._key_to_path(key)
        if path.exists():
            path.unlink()
            log.info("s3_delete", bucket=self.bucket_name, key=key)
            return True
        return False


_buckets: dict[str, S3Bucket] = {}


def get_bucket(bucket_name: str) -> S3Bucket:
    """Factory de buckets (singleton por nome)."""
    if bucket_name not in _buckets:
        _buckets[bucket_name] = S3Bucket(bucket_name)
    return _buckets[bucket_name]
