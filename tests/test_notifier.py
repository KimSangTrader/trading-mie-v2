"""market_intelligence/utils/notifier.py 테스트 (2026-10-30) - 실제 텔레그램은 호출하지 않는다."""
from unittest.mock import MagicMock, patch

import requests

from market_intelligence.utils.notifier import TelegramNotifier


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _ok():
    return MagicMock(status_code=200, text="ok")


class TestTelegramNotifier:
    def test_disabled_without_token_or_chat_id(self):
        n = TelegramNotifier(token="", chat_id="")
        with patch("market_intelligence.utils.notifier.requests.post") as post:
            assert n.send("x") is False
        post.assert_not_called()

    def test_sends_with_prefix(self):
        n = TelegramNotifier(token="T", chat_id="C", prefix="[MIE 실전] ")
        with patch("market_intelligence.utils.notifier.requests.post", return_value=_ok()) as post:
            assert n.send("주문 실패") is True
        assert post.call_args.kwargs["data"] == {"chat_id": "C", "text": "[MIE 실전] 주문 실패"}
        assert "botT/sendMessage" in post.call_args.args[0]

    def test_same_key_suppressed_within_cooldown(self):
        clock = FakeClock()
        n = TelegramNotifier(token="T", chat_id="C", cooldown_seconds=600, clock=clock)
        with patch("market_intelligence.utils.notifier.requests.post", return_value=_ok()) as post:
            assert n.send("a", key="stop_fail:005930") is True
            clock.now += 60
            assert n.send("a", key="stop_fail:005930") is False   # 1분 뒤 재시도 - 보내지 않음
            assert n.send("b", key="stop_fail:000660") is True    # 다른 종목은 보냄
            clock.now += 600
            assert n.send("a", key="stop_fail:005930") is True    # 쿨다운 지나면 다시 보냄
        assert post.call_count == 3

    def test_network_error_never_raises(self):
        n = TelegramNotifier(token="T", chat_id="C")
        with patch("market_intelligence.utils.notifier.requests.post",
                   side_effect=requests.exceptions.ConnectionError("down")):
            assert n.send("x", key="k") is False

    def test_failed_send_does_not_start_cooldown(self):
        n = TelegramNotifier(token="T", chat_id="C")
        with patch("market_intelligence.utils.notifier.requests.post",
                   side_effect=[MagicMock(status_code=500, text="err"), _ok()]):
            assert n.send("x", key="k") is False
            assert n.send("x", key="k") is True
