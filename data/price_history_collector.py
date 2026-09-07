"""
PriceHistoryCollector - 전체 종목 일봉(OHLCV) 히스토리 수집기 (Phase 5-13)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
- 배경: docs/hierarchical_scoring_plan.md Phase 1. sector_analy_method.txt의
  Sector/Theme/종목 점수 공식(5·20·60일 수익률, 상대강도, 상승확산도, 거래대금
  증가)이 모두 종목별 일별 OHLCV 시계열을 전제로 하는데, 이 프로젝트에는 이를
  저장하는 테이블도 수집기도 없었다. data/kis_client.py의
  get_stock_daily_chart(stock_code, days)는 Phase 5-11에서 이미 추가되어 있어서
  "가져오는" 방법 자체는 있었다 - 이 모듈은 그걸 전체 종목에 대해 rate-limit +
  체크포인트하며 반복 호출하는 역할만 한다
  (market_intelligence/collectors/valuation_collector.py의 ValuationCollector와
  거의 동일한 구조 - 그 모듈이 이미 검증한 "역할 분리/체크포인트/일일 캐시" 패턴을
  그대로 재사용한다).
- ValuationCollector와의 차이점: 종목 1개당 결과가 스칼라 1개(PER/PBR)가 아니라
  최대 100개 행(거래일별 OHLCV)이다. 그래서 collect()의 반환값은
  "종목별 레코드 1개짜리 리스트"가 아니라 "(종목, 거래일)별 행 리스트"로 이미
  펼쳐서(flatten) 반환한다 - 호출부(price_history_pipeline.py)가 바로
  DB 행으로 변환해 넣을 수 있게.
- 이 세션은 실제 KIS API에 접근할 수 없어 라이브 검증을 못 했다 (get_stock_daily_chart
  자체가 이미 "실제 응답 필드명은 라이브 검증 필요"로 표시되어 있음 - 이 모듈은 그
  가정을 새로 추가하지 않고 그대로 이어받는다). Mock KISClient로 단위테스트만 검증.
【2026-08-23】chart_to_price_rows() 모듈 레벨 함수로 분리 (Phase 5-17: main.py 배선)
- 배경: main.py의 종목별 루프(analyze_stock)가 TechnicalAnalyzer용으로 이미 매
  종목마다 get_stock_daily_chart()를 호출하고 있었다 - price_history_pipeline이
  같은 데이터를 다시 API로 수집하면 종목당 API 호출이 2배가 된다(전체 종목 기준
  수 분~십수 분 낭비). collect()의 chart→행 변환 로직(dates/opens/highs/lows/
  closes/volumes 병렬 리스트 → 행 리스트, 형식 오류 시 그 종목만 빈 리스트로
  건너뛰는 처리)을 그대로 재사용할 수 있도록 모듈 함수로 뽑아, main.py가 이미
  받은 chart 응답을 이 함수에 바로 넘겨 재사용하게 한다. collect() 내부도 이
  함수를 호출하도록 바꿔 로직이 두 곳에서 따로 갈라지지 않게 했다(동작 변화 없음 -
  기존 tests/test_price_history_collector.py 전부 그대로 통과).
================================================================================
"""

import json
import logging
import os
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_RATE_LIMIT_SEC = 0.2  # data/kis_client.py / valuation_collector.py와 동일 관례
_DEFAULT_CHECKPOINT_EVERY = 50
_DEFAULT_DAYS = 60


def chart_to_price_rows(symbol: str, market: Optional[str], chart: Dict[str, Any]) -> List[Dict[str, Any]]:
    """get_stock_daily_chart()가 돌려준 chart(dates/opens/highs/lows/closes/volumes
    병렬 리스트)를 (종목, 거래일)별 행 리스트로 펼친다.

    chart가 비어 있거나(빈 dict) 형식이 깨져 있으면(필드 누락, 길이 불일치 등)
    빈 리스트를 돌려준다 - 이 함수를 호출하는 쪽(collect()의 반복문, main.py의
    종목별 루프)에서 한 종목의 형식 오류가 전체를 중단시키지 않도록 보장한다
    ("종목별 실패는 전체를 중단시키지 않는다" - 이 프로젝트 전체 원칙).
    """
    try:
        return [
            {
                "symbol": symbol,
                "market": market,
                "date": trade_date,
                "open": chart["opens"][idx],
                "high": chart["highs"][idx],
                "low": chart["lows"][idx],
                "close": chart["closes"][idx],
                "volume": chart["volumes"][idx],
            }
            for idx, trade_date in enumerate(chart.get("dates", []) or [])
        ]
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f"⚠️  {symbol} 일봉 데이터 형식 오류 - {e}")
        return []


class PriceHistoryCollector:
    """전체 종목 일봉(OHLCV) 히스토리 수집기.

    KISClient.get_stock_daily_chart()를 종목별로 호출해 (ticker, trade_date)별
    행 리스트로 펼쳐서 반환한다. DB 저장(중복 제거/upsert)은 이 모듈의 책임이
    아니다 - price_history_pipeline.py가 담당한다(ValuationCollector가 DB를
    모르는 것과 동일한 역할 분리 원칙).
    """

    def __init__(self, kis_client: Optional[Any] = None, cache_dir: Optional[str] = None):
        """
        kis_client: None이면 KISClient 자동 초기화 시도 (실패 시 예외 - ValuationCollector와
        동일하게 Mock 폴백을 두지 않는다. 테스트에서는 Mock 클라이언트를 직접 주입한다).
        """
        if kis_client is None:
            from data.kis_client import KISClient
            kis_client = KISClient()
        self.kis_client = kis_client
        self.cache_dir = cache_dir or os.path.join(os.getcwd(), "data", "price_history_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    # ---------- 공개 API ----------

    def get_or_collect(self, stock_list: List[Dict[str, Any]], days: int = _DEFAULT_DAYS,
                        force_refresh: bool = False,
                        rate_limit_sec: float = _DEFAULT_RATE_LIMIT_SEC,
                        checkpoint_every: int = _DEFAULT_CHECKPOINT_EVERY,
                        progress_callback: Optional[Callable[[int, int], None]] = None,
                        ) -> List[Dict[str, Any]]:
        """오늘자 캐시(같은 days 파라미터)가 있으면 그대로 반환, 없으면 새로 수집한다."""
        result_path = self._result_cache_path(days)

        if not force_refresh and os.path.exists(result_path):
            logger.info(f"✅ 오늘자 일봉 수집 결과 재사용: {result_path}")
            with open(result_path, "r", encoding="utf-8") as f:
                return json.load(f)

        records = self.collect(stock_list, days=days, rate_limit_sec=rate_limit_sec,
                                checkpoint_every=checkpoint_every,
                                progress_callback=progress_callback)

        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)

        self._clear_checkpoint()
        return records

    def collect(self, stock_list: List[Dict[str, Any]], days: int = _DEFAULT_DAYS,
                rate_limit_sec: float = _DEFAULT_RATE_LIMIT_SEC,
                checkpoint_every: int = _DEFAULT_CHECKPOINT_EVERY,
                progress_callback: Optional[Callable[[int, int], None]] = None,
                ) -> List[Dict[str, Any]]:
        """
        stock_list: StockMaster.get_stock_list()의 반환값
            [{"symbol": "005930", "name": "삼성전자", "market": "KOSPI", ...}, ...]

        Returns: (종목, 거래일)별로 펼쳐진 행 리스트
            [{"symbol": ..., "market": ..., "date": "20260812", "open": ..., "high": ...,
              "low": ..., "close": ..., "volume": ...}, ...]
            (개별 종목 조회 실패/데이터 없음은 그 종목의 행이 아예 없는 것으로 처리된다 -
            PER/PBR과 달리 "값이 None인 행"을 만들 방법이 없다 - 하루치 시세가 없으면
            그 거래일 자체가 없는 것이므로)
        """
        collected_symbols, remaining = self._resume_or_start(stock_list)
        total = len(collected_symbols) + len(remaining)

        if total == 0:
            logger.warning("⚠️  수집할 종목이 없습니다 (빈 stock_list)")
            return []

        checkpoint_every = max(1, checkpoint_every)
        all_rows: List[Dict[str, Any]] = list(self._load_checkpoint_rows())

        logger.info(f"📊 일봉 히스토리 수집 시작: 총 {total}종목 (이어받기: {len(collected_symbols)}건 완료됨)")
        start_time = time.monotonic()
        done_symbols = list(collected_symbols)

        for i, stock in enumerate(remaining):
            symbol = stock["symbol"]
            market = stock.get("market")
            try:
                chart = self.kis_client.get_stock_daily_chart(symbol, days=days)
            except Exception as e:
                logger.warning(f"⚠️  {symbol}({stock.get('name')}) 일봉 조회 실패 - {e}")
                chart = {}

            symbol_rows = chart_to_price_rows(symbol, market, chart)
            all_rows.extend(symbol_rows)

            done_symbols.append(symbol)
            done = len(done_symbols)
            if progress_callback:
                progress_callback(done, total)
            if done % checkpoint_every == 0 or done == total:
                elapsed = time.monotonic() - start_time
                logger.info(f"   진행: {done}/{total} ({done*100//total}%) - 경과 {elapsed:.0f}초, 누적 {len(all_rows)}행")
                self._save_checkpoint(done_symbols, all_rows)

            if i < len(remaining) - 1:  # 마지막 종목 뒤에는 대기할 필요 없음
                time.sleep(rate_limit_sec)

        logger.info(f"✅ 일봉 히스토리 수집 완료: {len(done_symbols)}종목, {len(all_rows)}행")
        return all_rows

    # ---------- 캐시/체크포인트 ----------

    def _result_cache_path(self, days: int) -> str:
        return os.path.join(self.cache_dir, f"price_history_{date.today().isoformat()}_{days}d.json")

    def _checkpoint_path(self) -> str:
        return os.path.join(self.cache_dir, "_checkpoint.json")

    def _resume_or_start(self, stock_list: List[Dict[str, Any]]):
        checkpoint_path = self._checkpoint_path()
        if not os.path.exists(checkpoint_path):
            return [], list(stock_list)

        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("⚠️  체크포인트 파일이 손상되어 처음부터 다시 수집합니다")
            return [], list(stock_list)

        done_symbols = checkpoint.get("done_symbols", [])
        done_set = set(done_symbols)
        remaining = [s for s in stock_list if s["symbol"] not in done_set]

        if done_symbols:
            logger.info(f"🔄 체크포인트에서 이어받기: {len(done_symbols)}종목 완료됨, {len(remaining)}종목 남음")

        return done_symbols, remaining

    def _load_checkpoint_rows(self) -> List[Dict[str, Any]]:
        checkpoint_path = self._checkpoint_path()
        if not os.path.exists(checkpoint_path):
            return []
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                return json.load(f).get("rows", [])
        except (json.JSONDecodeError, OSError):
            return []

    def _save_checkpoint(self, done_symbols: List[str], rows: List[Dict[str, Any]]) -> None:
        checkpoint = {
            "done_symbols": done_symbols,
            "rows": rows,
            "updated_at": datetime.now().isoformat(),
        }
        with open(self._checkpoint_path(), "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, ensure_ascii=False)

    def _clear_checkpoint(self) -> None:
        checkpoint_path = self._checkpoint_path()
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)


if __name__ == "__main__":
    import sys
    from data.stock_master import StockMaster

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    # 【안전을 위한 기본값】 전체 2,700여 종목이 아니라 앞쪽 일부만 시험 수집.
    # 전체 수집은 python -m data.price_history_collector all 로 실행.
    limit = None if (len(sys.argv) > 1 and sys.argv[1] == "all") else 20

    master = StockMaster()
    stocks = master.get_stock_list(market="ALL", common_stock_only=True)
    if limit:
        stocks = stocks[:limit]
        print(f"⚠️  시험 실행: 앞쪽 {limit}종목만 수집합니다 (전체는 인자로 'all' 전달)")

    collector = PriceHistoryCollector()
    records = collector.get_or_collect(stocks, force_refresh=True)

    symbols_with_data = {r["symbol"] for r in records}
    print(f"\n수집 완료: {len(stocks)}종목 중 {len(symbols_with_data)}종목 데이터 확보, 총 {len(records)}행")
    for symbol in list(symbols_with_data)[:5]:
        rows = [r for r in records if r["symbol"] == symbol]
        print(f"  {symbol}: {len(rows)}일치, 최신 종가={rows[-1]['close']}")
