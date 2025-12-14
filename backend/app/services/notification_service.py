"""
Notification Service
알림 전송을 담당하는 서비스 (e.g., Slack)
"""
import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


class NotificationService:
    """알림 전송 서비스"""

    def __init__(self):
        self.slack_webhook_url = settings.SLACK_WEBHOOK_URL

    async def send_slack_notification(self, message: str):
        """Slack으로 알림 메시지를 전송합니다."""
        if not self.slack_webhook_url:
            log.warning("Slack webhook URL is not configured. Skipping notification.")
            return

        payload = {"text": message}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.slack_webhook_url, json=payload)
                response.raise_for_status()  # HTTP 4xx or 5xx 에러 발생 시 예외 처리
            log.info("Successfully sent Slack notification.", message=message)
        except httpx.RequestError as e:
            log.error(
                "Failed to send Slack notification",
                error=str(e),
                url=self.slack_webhook_url,
                exc_info=True,
            )
        except httpx.HTTPStatusError as e:
            log.error(
                "Failed to send Slack notification due to status error",
                status_code=e.response.status_code,
                response_text=e.response.text,
                exc_info=True,
            )

# 싱글턴 인스턴스 생성
notification_service = NotificationService()
