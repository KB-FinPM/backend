from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class S3Service:
    """
    S3 파일 업로드/조회 전담.
    Agent 또는 Router에서 boto3 직접 사용 금지.
    """

    def __init__(self):
        self.bucket = settings.S3_BUCKET_NAME
        # TODO: boto3 client 초기화
        # self.client = boto3.client("s3", region_name=settings.AWS_REGION)

    async def upload(self, file_bytes: bytes, key: str) -> str:
        logger.info(f"[S3] upload | key={key}")
        # TODO: 실제 S3 업로드 구현
        return f"s3://{self.bucket}/{key}"  # Mock

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        logger.info(f"[S3] presigned_url | key={key}")
        # TODO: presigned URL 생성
        return f"https://mock-presigned-url/{key}"  # Mock


s3_service = S3Service()
