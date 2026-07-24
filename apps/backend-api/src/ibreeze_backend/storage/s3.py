"""S3-compatible object storage service for skill packages."""

import hashlib
import logging
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from ibreeze_backend.settings import settings

logger = logging.getLogger(__name__)


class S3ObjectStorage:
    """S3-compatible object storage for skill packages."""

    def __init__(self):
        self.bucket_name = settings.s3_bucket_name
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

    def store(self, skill_id: str, version: str, zip_path: Path) -> str:
        """
        Store a skill ZIP file in S3.

        Args:
            skill_id: The skill identifier
            version: The skill version
            zip_path: Path to the ZIP file

        Returns:
            The S3 object key
        """
        object_key = f"skills/{skill_id}/{version}.zip"

        try:
            # 计算 SHA-256 用于 ETag
            sha256_hash = hashlib.sha256()
            with open(zip_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256_hash.update(chunk)
            content_sha256 = sha256_hash.hexdigest()

            # 上传到 S3
            self.client.upload_file(
                str(zip_path),
                self.bucket_name,
                object_key,
                ExtraArgs={
                    "ContentType": "application/zip",
                    "Metadata": {
                        "skill-id": skill_id,
                        "version": version,
                        "content-sha256": content_sha256,
                    },
                },
            )

            logger.info(f"Stored skill package: {object_key}")
            return object_key

        except ClientError as e:
            logger.error(f"Failed to store skill package: {e}")
            raise

    def retrieve(self, skill_id: str, version: str, download_path: Path) -> bool:
        """
        Retrieve a skill ZIP file from S3.

        Args:
            skill_id: The skill identifier
            version: The skill version
            download_path: Path to save the downloaded file

        Returns:
            True if successful, False if not found
        """
        object_key = f"skills/{skill_id}/{version}.zip"

        try:
            self.client.download_file(
                self.bucket_name,
                object_key,
                str(download_path),
            )
            logger.info(f"Retrieved skill package: {object_key}")
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            logger.error(f"Failed to retrieve skill package: {e}")
            raise

    def delete(self, skill_id: str, version: str) -> bool:
        """
        Delete a skill ZIP file from S3.

        Args:
            skill_id: The skill identifier
            version: The skill version

        Returns:
            True if successful, False if not found
        """
        object_key = f"skills/{skill_id}/{version}.zip"

        try:
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=object_key,
            )
            logger.info(f"Deleted skill package: {object_key}")
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            logger.error(f"Failed to delete skill package: {e}")
            raise

    def list_versions(self, skill_id: str) -> list[str]:
        """
        List all versions for a skill.

        Args:
            skill_id: The skill identifier

        Returns:
            List of version strings
        """
        prefix = f"skills/{skill_id}/"

        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
            )

            versions = []
            for obj in response.get("Contents", []):
                key = obj["Key"]
                # 提取版本号：skills/{skill_id}/{version}.zip
                if key.endswith(".zip"):
                    version = key.split("/")[-1].replace(".zip", "")
                    versions.append(version)

            return sorted(versions)

        except ClientError as e:
            logger.error(f"Failed to list skill versions: {e}")
            raise

    def get_object_sha256(self, skill_id: str, version: str) -> str | None:
        """
        Get the SHA-256 hash of a stored skill package.

        Args:
            skill_id: The skill identifier
            version: The skill version

        Returns:
            SHA-256 hash string or None if not found
        """
        object_key = f"skills/{skill_id}/{version}.zip"

        try:
            response = self.client.head_object(
                Bucket=self.bucket_name,
                Key=object_key,
            )

            # 从元数据中获取 SHA-256
            metadata = response.get("Metadata", {})
            return metadata.get("content-sha256")

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            logger.error(f"Failed to get object SHA-256: {e}")
            raise

    def object_exists(self, skill_id: str, version: str) -> bool:
        """
        Check if a skill package exists in S3.

        Args:
            skill_id: The skill identifier
            version: The skill version

        Returns:
            True if exists, False otherwise
        """
        object_key = f"skills/{skill_id}/{version}.zip"

        try:
            self.client.head_object(
                Bucket=self.bucket_name,
                Key=object_key,
            )
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise
