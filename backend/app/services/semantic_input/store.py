"""Immutable semantic artifact and internal audit storage."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ...config import Config
from ...utils.atomic_file import read_json_file, write_json_file
from .contracts import SemanticArtifactRef, SemanticAuditRecord, SemanticInputArtifact


class SemanticArtifactStore:
    ROOT = os.path.join(Config.UPLOAD_FOLDER, "semantic_inputs")

    @classmethod
    def _artifact_dir(cls, artifact_id: str) -> str:
        return os.path.join(cls.ROOT, artifact_id)

    @classmethod
    def _artifact_path(cls, artifact_id: str, revision: int) -> str:
        return os.path.join(cls._artifact_dir(artifact_id), f"revision_{revision}.json")

    @classmethod
    def _audit_path(cls, artifact_id: str, revision: int) -> str:
        return os.path.join(cls._artifact_dir(artifact_id), f"revision_{revision}.audit.json")

    @classmethod
    def save(cls, artifact: SemanticInputArtifact, audit: SemanticAuditRecord) -> None:
        os.makedirs(cls._artifact_dir(artifact.artifact_id), exist_ok=True)
        write_json_file(
            cls._artifact_path(artifact.artifact_id, artifact.revision),
            artifact.model_dump(mode="json"),
        )
        write_json_file(
            cls._audit_path(artifact.artifact_id, artifact.revision),
            audit.model_dump(mode="json"),
        )

    @classmethod
    def get(
        cls,
        artifact_id: str,
        revision: Optional[int] = None,
    ) -> Optional[SemanticInputArtifact]:
        if not artifact_id:
            return None
        if revision is None:
            revision = cls.latest_revision(artifact_id)
        if not revision:
            return None
        payload = read_json_file(cls._artifact_path(artifact_id, revision), default=None)
        return SemanticInputArtifact.model_validate(payload) if payload else None

    @classmethod
    def get_by_ref(cls, value: Any) -> Optional[SemanticInputArtifact]:
        if not value:
            return None
        if isinstance(value, SemanticArtifactRef):
            ref = value
        elif isinstance(value, dict):
            try:
                ref = SemanticArtifactRef.model_validate(value)
            except Exception:
                return None
        else:
            return cls.get(str(value))
        artifact = cls.get(ref.artifact_id, ref.revision)
        if artifact and ref.content_hash and artifact.content_hash != ref.content_hash:
            return None
        return artifact

    @classmethod
    def get_audit(cls, artifact_id: str, revision: int) -> Optional[Dict[str, Any]]:
        return read_json_file(cls._audit_path(artifact_id, revision), default=None)

    @classmethod
    def latest_revision(cls, artifact_id: str) -> int:
        directory = cls._artifact_dir(artifact_id)
        if not os.path.isdir(directory):
            return 0
        revisions = []
        for name in os.listdir(directory):
            if not name.startswith("revision_") or not name.endswith(".json") or name.endswith(".audit.json"):
                continue
            try:
                revisions.append(int(name[len("revision_") : -len(".json")]))
            except ValueError:
                continue
        return max(revisions, default=0)

    @classmethod
    def public_ref(cls, artifact: SemanticInputArtifact) -> Dict[str, Any]:
        return artifact.ref().model_dump(mode="json")
