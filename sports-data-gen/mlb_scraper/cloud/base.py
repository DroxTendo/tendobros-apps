"""Cloud-agnostic upload interface. Concrete providers (s3.py, and a future
azure_blob.py) implement CloudUploader so stages/load.py's load_range
never contains provider-specific code -- switching providers is a --provider
flag / .env change, not a code change.
"""

from __future__ import annotations

import abc
from pathlib import Path


class CloudUploader(abc.ABC):
    @abc.abstractmethod
    def upload_file(self, local_path: Path, remote_key: str) -> None:
        """Upload local_path's bytes to remote_key under this provider's configured bucket/container."""
