"""pytest 설정 - Mock 데이터 사용"""
import pytest

@pytest.fixture
def mock_technical_data():
    """기술지표 테스트 데이터"""
    return {
        "symbol": "0001",
        "dates": ["20260812", "20260811", "20260810"] + ["20260101"] * 57,
        "opens": [7500] * 60,
        "highs": [7600] * 60,
        "lows": [7400] * 60,
        "closes": [7516.04] + [7510] * 59,
        "volumes": [458190] * 60
    }

@pytest.fixture
def mock_market_data():
    """시장 데이터"""
    return {
        "kospi_index": 6579.04,
        "kospi_change_rate": 3.68,
        "kosdaq_index": 858.91,
        "kosdaq_change_rate": 0.12
    }
