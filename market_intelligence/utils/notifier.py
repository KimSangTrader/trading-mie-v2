"""
텔레그램 알림 (2026-10-30 신규) - 실전 매매 중 주문 실패/예외를 휴대폰으로 즉시 알린다.

================================================================================
【변경 이력】
================================================================================
【2026-10-30】최초 생성
- 배경: 10/28 실전투자 전환 후, 주문 실패나 장중 루프 예외가 로그에만 남아 사용자가
  직접 로그를 보기 전엔 알 수 없었다(10/27 모의투자 신청 만료도 로그로만 발견).
  사용자가 알림 수단으로 텔레그램을 선택.
- .env의 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID를 읽는다. 둘 중 하나라도 없으면 알림을
  보내지 않고(no-op) 처음 한 번만 경고 로그를 남긴다 - 알림 설정이 없어도 매매는 그대로 돈다.
- 【중요】send()는 절대 예외를 올리지 않는다. 알림 실패(텔레그램 장애, 네트워크) 때문에
  손절/주문 로직이 멈추면 안 되기 때문 - 실패는 로그로만 남긴다. timeout도 짧게(5초).
- 같은 key의 알림은 cooldown_seconds(기본 10분) 안에 다시 보내지 않는다 - 손절 주문 실패는
  1분마다 재시도되므로 그대로 보내면 휴대폰이 알림으로 도배된다.
================================================================================
"""
import logging
import os
import time
from typing import Callable, Dict, Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        cooldown_seconds: int = 600,
        prefix: str = "",
        clock: Callable[[], float] = time.monotonic,
    ):
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")
        self.cooldown_seconds = cooldown_seconds
        self.prefix = prefix
        self._clock = clock
        self._last_sent: Dict[str, float] = {}
        self._warned_disabled = False

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str, key: Optional[str] = None) -> bool:
        """알림 전송. 보냈으면 True, 설정 없음/쿨다운/실패면 False. 예외를 올리지 않는다."""
        if not self.enabled:
            if not self._warned_disabled:
                self._warned_disabled = True
                logger.warning("⚠️  텔레그램 알림 꺼짐 - .env에 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID가 없음")
            return False

        now = self._clock()
        if key is not None:
            last = self._last_sent.get(key)
            if last is not None and now - last < self.cooldown_seconds:
                return False

        try:
            response = requests.post(
                TELEGRAM_SEND_URL.format(token=self.token),
                data={"chat_id": self.chat_id, "text": f"{self.prefix}{text}"},
                timeout=5,
            )
            if response.status_code != 200:
                logger.warning(f"⚠️  텔레그램 알림 전송 실패: HTTP {response.status_code} {response.text[:200]}")
                return False
        except Exception as e:  # 알림 실패가 매매 로직을 멈추면 안 됨
            logger.warning(f"⚠️  텔레그램 알림 전송 오류: {e}")
            return False

        if key is not None:
            self._last_sent[key] = now
        return True
