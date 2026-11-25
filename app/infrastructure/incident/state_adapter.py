"""Atomic JSON persistence for the active incident and its group reference."""

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from domain.incident.aggregate import IncidentGroup
from domain.incident.ports import IncidentStatePort


class FileIncidentStateAdapter(IncidentStatePort):
    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)

    def save_active(
        self, title: str, group: IncidentGroup, started_at: datetime
    ) -> None:
        self._write({
            "active": True,
            "title": title,
            "group": asdict(group),
            "started_at": started_at.isoformat(),
        })

    def save_inactive(self) -> None:
        self._write({"active": False})

    def load(self) -> dict | None:
        try:
            with self._path.open(encoding="utf-8") as state_file:
                data = json.load(state_file)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            # The application query logs invalid state and starts inactive.
            return None
        return data if data.get("active") is True else None

    def _write(self, data: dict) -> None:
        """Replace, rather than partially overwrite, the state file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_path = tempfile.mkstemp(
            dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as state_file:
                json.dump(data, state_file)
                state_file.write("\n")
                state_file.flush()
                os.fsync(state_file.fileno())
            os.replace(temporary_path, self._path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise
