import os

from app.core.config import settings


def test_test_environment_disables_external_aws_lookup() -> None:
    assert os.environ["AWS_EC2_METADATA_DISABLED"] == "true"
    assert os.environ["AWS_ACCESS_KEY_ID"] == ""
    assert os.environ["AWS_SECRET_ACCESS_KEY"] == ""
    assert os.environ["AWS_SESSION_TOKEN"] == ""
    assert settings.S3_STORAGE_BACKEND == "mock"
