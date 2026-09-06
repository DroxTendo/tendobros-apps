"""Factory for cloud uploaders -- the one place that knows which provider
names map to which implementation, so the load stage just asks for
"s3"/"azure" and never imports a provider module directly.

Only "s3" is implemented today. To add Azure Blob Storage later: write
mlb_scraper/cloud/azure_blob.py with a class implementing CloudUploader
(see base.py), then wire it into get_uploader() below the same way s3 is.
"""

from __future__ import annotations

from mlb_scraper.cloud.base import CloudUploader

SUPPORTED_PROVIDERS = ("s3", "azure")


def get_uploader(provider: str) -> CloudUploader:
    provider = provider.lower()

    if provider == "s3":
        from mlb_scraper.cloud.s3 import S3Uploader
        return S3Uploader()

    if provider == "azure":
        raise NotImplementedError(
            "azure provider is not implemented yet -- add mlb_scraper/cloud/azure_blob.py "
            "and wire it into get_uploader() once the Azure Storage account is set up"
        )

    raise ValueError(f"unknown provider: {provider!r} (supported: {', '.join(SUPPORTED_PROVIDERS)})")
