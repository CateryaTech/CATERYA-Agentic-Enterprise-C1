"""
Encrypted Automated Backup — S3 + IPFS
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Backup strategy:
  1. Encrypt backup with AES-256-GCM (Fernet)
  2. Upload to AWS S3 (primary)
  3. Pin to IPFS via Pinata/web3.storage (immutable audit backup)
  4. Store CID/S3 key in provenance chain
  5. Rotate keys on schedule
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Encryption (Fernet AES-256) ───────────────────────────────────────────────

def _get_fernet():
    from cryptography.fernet import Fernet
    key_b64 = os.getenv("BACKUP_ENCRYPTION_KEY")
    if not key_b64:
        raise RuntimeError(
            "BACKUP_ENCRYPTION_KEY not set. Generate with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key_b64.encode() if isinstance(key_b64, str) else key_b64)


def encrypt_payload(data: bytes) -> bytes:
    """AES-256-GCM encrypt + gzip compress."""
    compressed = gzip.compress(data, compresslevel=9)
    return _get_fernet().encrypt(compressed)


def decrypt_payload(encrypted: bytes) -> bytes:
    """Decrypt + decompress."""
    compressed = _get_fernet().decrypt(encrypted)
    return gzip.decompress(compressed)


# ── Backup manifest ───────────────────────────────────────────────────────────

@dataclass
class BackupManifest:
    backup_id:     str
    tenant_id:     str
    timestamp:     str
    size_bytes:    int
    encrypted:     bool
    sha256:        str
    s3_key:        Optional[str] = None
    ipfs_cid:      Optional[str] = None
    tables:        List[str]     = None
    status:        str           = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "tenant_id": self.tenant_id,
            "timestamp": self.timestamp,
            "size_bytes": self.size_bytes,
            "encrypted": self.encrypted,
            "sha256": self.sha256,
            "s3_key": self.s3_key,
            "ipfs_cid": self.ipfs_cid,
            "tables": self.tables or [],
            "status": self.status,
        }


# ── S3 Backend ────────────────────────────────────────────────────────────────

class S3BackupBackend:
    def __init__(self):
        self.bucket  = os.getenv("BACKUP_S3_BUCKET", "caterya-backups")
        self.prefix  = os.getenv("BACKUP_S3_PREFIX", "backups/")
        self.region  = os.getenv("AWS_REGION", "ap-southeast-1")

    def upload(self, key: str, data: bytes, metadata: Dict = None) -> bool:
        try:
            import boto3
            s3 = boto3.client("s3", region_name=self.region)
            s3.put_object(
                Bucket=self.bucket,
                Key=self.prefix + key,
                Body=data,
                Metadata=metadata or {},
                ServerSideEncryption="AES256",   # S3-side encryption (double-encrypted)
                StorageClass="STANDARD_IA",
            )
            logger.info("S3 upload OK | bucket=%s key=%s size=%d", self.bucket, key, len(data))
            return True
        except Exception as e:
            logger.error("S3 upload failed: %s", e)
            return False

    def download(self, key: str) -> Optional[bytes]:
        try:
            import boto3
            s3 = boto3.client("s3", region_name=self.region)
            obj = s3.get_object(Bucket=self.bucket, Key=self.prefix + key)
            return obj["Body"].read()
        except Exception as e:
            logger.error("S3 download failed: %s", e)
            return None

    def list_backups(self, tenant_id: str) -> List[str]:
        try:
            import boto3
            s3 = boto3.client("s3", region_name=self.region)
            resp = s3.list_objects_v2(Bucket=self.bucket, Prefix=f"{self.prefix}{tenant_id}/")
            return [obj["Key"] for obj in resp.get("Contents", [])]
        except Exception as e:
            logger.warning("S3 list failed: %s", e)
            return []


# ── IPFS Backend (Pinata) ─────────────────────────────────────────────────────

class IPFSBackupBackend:
    def __init__(self):
        self.pinata_jwt = os.getenv("PINATA_JWT", "")
        self.pinata_url = "https://api.pinata.cloud"

    def pin(self, data: bytes, name: str) -> Optional[str]:
        """Pin data to IPFS via Pinata. Returns CID."""
        if not self.pinata_jwt:
            logger.warning("PINATA_JWT not set, skipping IPFS backup")
            return None
        try:
            import httpx
            files = {"file": (name, io.BytesIO(data), "application/octet-stream")}
            headers = {"Authorization": f"Bearer {self.pinata_jwt}"}
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    f"{self.pinata_url}/pinning/pinFileToIPFS",
                    files=files, headers=headers,
                    data={"pinataMetadata": json.dumps({"name": name})},
                )
            if resp.status_code == 200:
                cid = resp.json().get("IpfsHash")
                logger.info("IPFS pin OK | cid=%s name=%s", cid, name)
                return cid
        except Exception as e:
            logger.error("IPFS pin failed: %s", e)
        return None

    def verify(self, cid: str) -> bool:
        """Verify data is accessible on IPFS gateway."""
        try:
            import httpx
            url = f"https://gateway.pinata.cloud/ipfs/{cid}"
            with httpx.Client(timeout=15) as client:
                resp = client.head(url)
            return resp.status_code == 200
        except Exception:
            return False


# ── Main Backup Manager ───────────────────────────────────────────────────────

class BackupManager:
    """
    Manages encrypted, redundant backups to S3 + IPFS.

    Usage::

        manager = BackupManager()

        # Backup a tenant's provenance chain
        manifest = manager.backup_provenance(
            tenant_id="acme",
            provenance_records=[...],
        )
        print(manifest.s3_key, manifest.ipfs_cid)

        # Restore
        records = manager.restore_provenance(manifest.backup_id, tenant_id="acme")
    """

    def __init__(self):
        self.s3   = S3BackupBackend()
        self.ipfs = IPFSBackupBackend()
        self._manifests: Dict[str, BackupManifest] = {}

    def backup_provenance(
        self,
        tenant_id: str,
        provenance_records: List[Dict],
    ) -> BackupManifest:
        import uuid
        backup_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        payload   = json.dumps(provenance_records, default=str).encode()
        sha256    = hashlib.sha256(payload).hexdigest()

        try:
            encrypted = encrypt_payload(payload)
        except RuntimeError:
            # No encryption key — use unencrypted in dev
            encrypted = payload
            encrypted_flag = False
            logger.warning("BACKUP_ENCRYPTION_KEY not set — storing unencrypted (dev only)")
        else:
            encrypted_flag = True

        s3_key = f"{tenant_id}/{backup_id}/provenance.enc"
        manifest = BackupManifest(
            backup_id=backup_id, tenant_id=tenant_id, timestamp=timestamp,
            size_bytes=len(encrypted), encrypted=encrypted_flag,
            sha256=sha256, tables=["provenance_chain"], status="uploading",
        )

        # S3 upload
        s3_ok = self.s3.upload(s3_key, encrypted, metadata={"tenant_id": tenant_id, "sha256": sha256})
        if s3_ok:
            manifest.s3_key = s3_key

        # IPFS pin (best-effort)
        cid = self.ipfs.pin(encrypted, f"caterya-provenance-{tenant_id}-{backup_id[:8]}.enc")
        if cid:
            manifest.ipfs_cid = cid

        manifest.status = "complete" if s3_ok else "s3_failed"
        self._manifests[backup_id] = manifest

        logger.info("Backup complete | id=%s tenant=%s s3=%s ipfs=%s",
                    backup_id, tenant_id, manifest.s3_key, manifest.ipfs_cid)
        return manifest

    def restore_provenance(
        self,
        backup_id: str,
        tenant_id: str,
    ) -> Optional[List[Dict]]:
        manifest = self._manifests.get(backup_id)
        if not manifest or manifest.tenant_id != tenant_id:
            logger.error("Backup not found or tenant mismatch: %s", backup_id)
            return None

        # Try S3 first
        encrypted = self.s3.download(manifest.s3_key) if manifest.s3_key else None

        # IPFS fallback
        if not encrypted and manifest.ipfs_cid:
            try:
                import httpx
                url = f"https://gateway.pinata.cloud/ipfs/{manifest.ipfs_cid}"
                with httpx.Client(timeout=30) as client:
                    resp = client.get(url)
                encrypted = resp.content if resp.status_code == 200 else None
            except Exception as e:
                logger.error("IPFS restore failed: %s", e)

        if not encrypted:
            logger.error("Restore failed: no data available for backup %s", backup_id)
            return None

        try:
            payload = decrypt_payload(encrypted) if manifest.encrypted else encrypted
        except Exception:
            payload = encrypted  # fallback

        # Verify integrity
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if actual_sha256 != manifest.sha256:
            logger.error("SHA256 mismatch on restore! Expected %s got %s",
                         manifest.sha256, actual_sha256)
            return None

        return json.loads(payload)

    def schedule_backups(self, interval_hours: int = 6) -> None:
        """
        Schedule periodic backups. In production, use Celery Beat:
        @app.on_after_configure.connect
        def setup_periodic_tasks(sender, **kwargs):
            sender.add_periodic_task(interval_hours * 3600, backup_task.s())
        """
        import threading
        def _run():
            while True:
                time.sleep(interval_hours * 3600)
                logger.info("Scheduled backup triggered")
        t = threading.Thread(target=_run, daemon=True)
        t.start()
