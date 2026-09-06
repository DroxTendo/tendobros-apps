"""S3 implementation of CloudUploader.

Bucket/region come from config.py (itself populated from .env). Credentials
are never read here directly -- boto3's default credential chain (env vars,
~/.aws/credentials, an IAM role, etc.) handles that, so setting
AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY in .env works automatically once
config.py's load_dotenv() has put them in the process environment, but
`aws configure`/an instance role work too without any of this project's
config needing to know about it.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

import boto3

import config
from mlb_scraper.cloud.base import CloudUploader

logger = logging.getLogger(__name__)


class S3Uploader(CloudUploader):
    def __init__(self, bucket: str | None = None):
        self.bucket = bucket or config.S3_BUCKET
        if not self.bucket:
            raise ValueError("S3 bucket not configured -- set S3_BUCKET in .env (see .env.example)")
        self._client = boto3.client("s3", region_name=config.AWS_REGION)

    def upload_file(self, local_path: Path, remote_key: str) -> None:
        # boto3 doesn't guess Content-Type from the extension the way `aws s3
        # cp` does -- without this every object defaults to
        # application/octet-stream, which is wrong for a .json file and only
        # matters if something ever fetches these over HTTP directly
        # (presigned URL, CloudFront, static hosting) rather than through
        # get_object/boto3.
        content_type, _ = mimetypes.guess_type(str(local_path))
        extra_args = {"ContentType": content_type} if content_type else {}

        self._client.upload_file(str(local_path), self.bucket, remote_key, ExtraArgs=extra_args)
        logger.debug("uploaded %s -> s3://%s/%s (%s)", local_path, self.bucket, remote_key, content_type or "no content-type guessed")
