"""KISClient._get_with_retry() 테스트 (2026-10-20) - 조회 실패 시 1회 재시도 + 응답 본문 로깅.

실제 KIS 서버는 호출하지 않는다: __init__을 우회한 인스턴스에 requests.get을 Mock으로 바꿔 끼운다."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from data.kis_client import KISClient


def _client():
    client = KISClient.__new__(KISClient)  # __init__(.env 키 검사/출력) 우회
    client.QUERY_RETRY_DELAY_SECONDS = 0
    return client


def _response(status, json_body=None, text=""):
    response = MagicMock(status_code=status, text=text)
    if json_body is None:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = json_body
    return response


class TestGetWithRetry:
    def test_success_first_try_no_retry(self):
        ok = _response(200, {"rt_cd": "0"})
        with patch("data.kis_client.requests.get", return_value=ok) as get:
            assert _client()._get_with_retry("u", {}, {}, "잔고조회") is ok
        assert get.call_count == 1

    def test_500_then_success_retries_once(self, capsys):
        fail = _response(500, {"msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과하였습니다."})
        ok = _response(200, {"rt_cd": "0"})
        with patch("data.kis_client.requests.get", side_effect=[fail, ok]) as get:
            assert _client()._get_with_retry("u", {}, {}, "잔고조회") is ok
        assert get.call_count == 2
        out = capsys.readouterr().out
        assert "EGW00201" in out and "재시도" in out

    def test_500_twice_returns_last_response_and_logs_body(self, capsys):
        fail = _response(500, None, text="<html>Internal Server Error</html>")
        with patch("data.kis_client.requests.get", return_value=fail) as get:
            response = _client()._get_with_retry("u", {}, {}, "잔고조회")
        assert response.status_code == 500  # 호출부의 기존 status_code 검사가 그대로 동작
        assert get.call_count == 2
        assert "Internal Server Error" in capsys.readouterr().out

    def test_connection_error_then_success(self):
        ok = _response(200, {"rt_cd": "0"})
        error = requests.exceptions.ConnectionError("Remote end closed connection without response")
        with patch("data.kis_client.requests.get", side_effect=[error, ok]) as get:
            assert _client()._get_with_retry("u", {}, {}, "현재가(033560)") is ok
        assert get.call_count == 2

    def test_connection_error_twice_raises(self):
        error = requests.exceptions.ConnectionError("down")
        with patch("data.kis_client.requests.get", side_effect=[error, error]):
            with pytest.raises(requests.exceptions.ConnectionError):
                _client()._get_with_retry("u", {}, {}, "현재가(033560)")


class TestCallSites:
    def test_get_current_quote_recovers_after_one_500(self):
        client = _client()
        client.access_token, client.api_key, client.api_secret, client.base_url = "t", "k", "s", "http://x"
        client.ensure_valid_token = lambda: True
        fail = _response(500, {"msg_cd": "EGW00201", "msg1": "초당 거래건수 초과"})
        ok = _response(200, {"rt_cd": "0", "output": {"stck_prpr": "10000", "stck_hgpr": "10100",
                                                      "stck_lwpr": "9900", "prdy_ctrt": "1.0", "stck_sdpr": "9900"}})
        with patch("data.kis_client.requests.get", side_effect=[fail, ok]):
            quote = client.get_current_quote("033560")
        assert quote["current_price"] == 10000.0

    def test_place_order_does_not_use_retry(self):
        """주문(POST)은 재시도 대상이 아니다 - 중복 주문 방지."""
        import inspect
        assert "_get_with_retry" not in inspect.getsource(KISClient.place_order)
