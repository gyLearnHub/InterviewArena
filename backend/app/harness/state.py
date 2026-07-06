from __future__ import annotations

from app.harness.contracts import CheckpointCreate
from app.repositories.harness import HarnessCheckpointRecord, HarnessRepository


class CheckpointError(RuntimeError):
    pass


class CheckpointManager:
    def __init__(self, repository: HarnessRepository) -> None:
        self.repository = repository

    def create_checkpoint(self, checkpoint: CheckpointCreate) -> int:
        try:
            return self.repository.create_checkpoint(checkpoint)
        except Exception as exc:
            raise CheckpointError("failed to create harness checkpoint") from exc

    def latest_checkpoint(
        self,
        interview_id: int,
        *,
        round_id: int | None = None,
        node_id: str | None = None,
    ) -> HarnessCheckpointRecord | None:
        return self.repository.latest_checkpoint(interview_id, round_id=round_id, node_id=node_id)
