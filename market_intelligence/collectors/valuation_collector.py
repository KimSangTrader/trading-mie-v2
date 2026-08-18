"""
ValuationCollector - 전체 종목 PER/PBR 수집기 (Phase 5-3)

================================================================================
【변경 이력】
================================================================================
【2026-08-15】최초 생성 (Phase 5 방향 보고서 반영, 사용자가 "KOSPI/KOSDAQ 전체 종목"
범위로 진행 결정함)

- 역할: StockMaster(종목마스터)가 만든 KOSPI/KOSDAQ 전체 종목 리스트를 받아, 종목별로
  KISClient.get_stock_fundamental()을 호출해 PER/PBR을 모으고,
  market_intelligence.market_valuation.MarketValuation이 바로 소비할 수 있는 형태
  (symbol/market/per/pbr/dividend_yield 레코드 리스트)로 반환한다.
- 이 모듈도 ValuationAnalyzer와 마찬가지로 "무엇을 할지"만 조립하고, KISClient는
  생성자에서 주입받는다 (테스트 시 Mock 클라이언트로 교체 가능, Phase 5 방향 보고서의
  "역할 분리" 원칙).
- 규모 문제: KOSPI 약 800 + KOSDAQ 약 1500 = 약 2,300종목. 종목당 1회 API 호출 +
  기존 코드 관례(kis_client.py get_daily_price)와 동일한 0.2초 호출 간격을 적용하면
  최소 약 7~8분, 실제로는 네트워크 왕복까지 포함해 더 오래 걸릴 수 있다. 따라서:
    * 체크포인트: N종목마다 진행 상황을 파일에 저장해서, 중간에 끊겨도(네트워크 오류,
      프로세스 종료 등) 처음부터 다시 받지 않고 이어서 수집할 수 있다.
    * 일일 캐시: 재무 데이터는 하루에도 여러 번 바뀌지 않으므로, 같은 날짜에 이미 전체
      수집을 완료했으면 그 결과를 재사용한다 (Phase 5 방향 보고서의 캐싱 전략과 동일).
    * 종목별 실패는 전체를 중단시키지 않고 건너뛴다 (한 종목 조회 실패가 나머지 2천여
      종목 수집을 막으면 안 됨).
- 이 세션은 실제 KIS API로 2천여 종목을 수집해서 검증할 수 없었다 (클라우드 샌드박스가
  KIS API 도메인에 네트워크 접근이 안 됨 - kis_client.py 자체는 사용자 컴퓨터에서 이미
  개별 종목 조회로 라이브 검증됨). 소규모(예: 10~20종목)로 먼저 __main__ 실행해서
  확인하는 것을 권장한다.
  → 사용자 컴퓨터에서 실제로 KOSPI 915/KOSDAQ 1803(합계 2718)종목 전체 실행 및 실제
  RDS 저장까지 검증 완료함(2026-08-16, valuation_pipeline.py를 통해).

【2026-08-17】배당수익률 병합 추가 (Phase 5-8, 1차 - KIS 랭킹 API, 폐기됨)
- 처음엔 KISClient.get_dividend_rates(market)로 시장당 1회씩 병합하도록 했으나,
  실측 결과 그 API 자체가 부적합했다(시장당 20종목까지만 반환, 필드도 배당수익률이
  아니라 액면배당률). 자세한 경위는 data/kis_client.py 변경 이력 참고.

【2026-08-17】배당수익률 병합 2차 - KRX 정보데이터시스템으로 교체
- 사용자가 첨부한 "한국거래소를 이용한 배당율조회와 실시간 조회 연동방법.docx"
  제안대로, KIS Open API가 아니라 KRX 정보데이터시스템(data.krx.co.kr, 별도
  공개 API)에서 시장 전체 배당수익률을 한 번에 받아오는 data/krx_data.py로 교체.
- collect()가 종목별 PER/PBR 수집을 끝낸 뒤 시장(KOSPI/KOSDAQ)별로 1회씩만
  dividend_fetcher(market)를 호출해 종목코드 기준으로 병합한다. 종목 수만큼
  호출하는 게 아니라서 rate_limit/체크포인트 로직과는 무관하다.
- dividend_fetcher를 생성자에서 주입 가능하게 해서(기본값은 krx_data.get_dividend_yields
  지연 임포트) 테스트에서 Mock 함수로 교체할 수 있다.
- fetch_dividends 파라미터(기본 True)로 끌 수 있게 해서, 배당 병합 없이 PER/PBR
  로직만 보고 싶을 때 끌 수 있다.

【2026-08-17】배당수익률 병합 3차 - KRX 라이브 API → CSV 임포터로 교체
- data/krx_data.py(위 2차)를 사용자 컴퓨터에서 실제로 호출해본 결과, 날짜와
  무관하게 모든 요청이 HTTP 400 + "LOGOUT"으로 거부됨을 확인했다. 브라우저
  개발자도구로 실제 요청을 여러 차례 캡처해 비교한 결과, 페이지의 자바스크립트가
  세팅하는 것으로 보이는 세션 쿠키(mdc.client_session=true)가 있어야 서버가
  요청을 받아주는 것으로 판단됨 - requests 같은 순수 HTTP 클라이언트로는 재현이
  안 되는 안티봇 조치로 보인다(자세한 진단 경위는 data/krx_data.py 변경이력 참고).
- 그래서 사용자 제안대로 CSV 수동 임포트 방식(data/krx_importer.py)으로 교체.
  장 마감 후 사람이 KRX 화면에서 CSV를 다운로드해 data/krx/incoming/에 넣으면
  자동으로 검증·정규화되어 data/krx/latest/에 반영되고, ValuationCollector는
  그 latest 데이터를 읽기만 한다.
- 인터페이스는 그대로다(market(str) -> {종목코드: 배당수익률} 딕셔너리) - 그래서
  기본 dividend_fetcher 지연 임포트 대상만 data.krx_data.get_dividend_yields에서
  data.krx_importer.get_dividend_yields로 바꾸면 됐고, ValuationCollector 자체의
  로직/테스트는 거의 그대로 유지된다(dividend_fetcher 주입 구조 덕분).
================================================================================
"""

import json
import logging
import os
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_RATE_LIMIT_SEC = 0.2  # data/kis_client.py의 기존 관례와 동일
_DEFAULT_CHECKPOINT_EVERY = 50


class ValuationCollector:
    """전체 종목 PER/PBR 수집기 (API 호출은 하되, 상대평가 계산은 하지 않는다 - 그건
    ValuationAnalyzer/MarketValuation의 몫)"""

    def __init__(self, kis_client: Optional[Any] = None, cache_dir: Optional[str] = None,
                 dividend_fetcher: Optional[Callable[[str], Dict[str, float]]] = None):
        """
        kis_client: None이면 KISClient 자동 초기화 시도 (실패 시 예외 - 이 컬렉터는
        실데이터 수집이 유일한 목적이라 Mock 폴백을 두지 않는다. 테스트에서는 Mock
        클라이언트를 직접 주입한다).
        dividend_fetcher: market(str) -> {종목코드: 배당수익률(%)} 딕셔너리를 반환하는
        콜러블. None이면 data.krx_importer.get_dividend_yields를 지연 임포트해서
        사용한다 - KRX 정보데이터시스템에서 사람이 수동으로 다운로드해 data/krx/incoming/
        에 넣은 CSV를 검증·정규화한 결과(data/krx/latest/)를 읽어온다. KIS Open API와는
        무관한 별도 데이터 소스다(라이브 API 직접 호출은 안티봇 조치로 막혀서 폐기 -
        data/krx_data.py 변경이력 참고).
        """
        if kis_client is None:
            from data.kis_client import KISClient
            kis_client = KISClient()
        self.kis_client = kis_client
        self.cache_dir = cache_dir or os.path.join(os.getcwd(), "data", "valuation_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

        if dividend_fetcher is None:
            def dividend_fetcher(market):
                from data.krx_importer import get_dividend_yields
                return get_dividend_yields(market)
        self.dividend_fetcher = dividend_fetcher

    # ---------- 공개 API ----------

    def get_or_collect(self, stock_list: List[Dict[str, Any]], force_refresh: bool = False,
                        rate_limit_sec: float = _DEFAULT_RATE_LIMIT_SEC,
                        checkpoint_every: int = _DEFAULT_CHECKPOINT_EVERY,
                        progress_callback: Optional[Callable[[int, int], None]] = None,
                        fetch_dividends: bool = True,
                        ) -> List[Dict[str, Any]]:
        """
        오늘자 캐시가 있으면 그대로 반환, 없으면(또는 force_refresh=True) 새로 수집한다.
        """
        result_path = self._result_cache_path()

        if not force_refresh and os.path.exists(result_path):
            logger.info(f"✅ 오늘자 밸류에이션 수집 결과 재사용: {result_path}")
            with open(result_path, "r", encoding="utf-8") as f:
                return json.load(f)

        records = self.collect(stock_list, rate_limit_sec=rate_limit_sec,
                                checkpoint_every=checkpoint_every,
                                progress_callback=progress_callback,
                                fetch_dividends=fetch_dividends)

        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)

        self._clear_checkpoint()
        return records

    def collect(self, stock_list: List[Dict[str, Any]],
                rate_limit_sec: float = _DEFAULT_RATE_LIMIT_SEC,
                checkpoint_every: int = _DEFAULT_CHECKPOINT_EVERY,
                progress_callback: Optional[Callable[[int, int], None]] = None,
                fetch_dividends: bool = True,
                ) -> List[Dict[str, Any]]:
        """
        stock_list: StockMaster.get_stock_list()의 반환값
            [{"symbol": "005930", "name": "삼성전자", "market": "KOSPI", ...}, ...]

        fetch_dividends: True면 종목별 PER/PBR 수집이 끝난 뒤, 시장(KOSPI/KOSDAQ)별로
            1회씩 KISClient.get_dividend_rates()를 호출해 배당률을 종목코드 기준으로
            병합한다. (종목 수만큼 호출하는 게 아니라서 rate_limit/체크포인트와 무관)
            테스트에서 배당 병합 없이 PER/PBR 로직만 보고 싶으면 False로 끈다.

        Returns: MarketValuation.calculate_medians() 입력 형식과 동일
            [{"symbol": ..., "market": ..., "per": ..., "pbr": ..., "dividend_yield": ...}, ...]
            (개별 종목 조회 실패 시 per/pbr/dividend_yield는 None으로 채워지고 목록에는
            남는다 - MarketValuation이 알아서 결측값을 제외하고 중앙값을 계산한다)
        """
        collected, remaining = self._resume_or_start(stock_list)
        total = len(collected) + len(remaining)

        if total == 0:
            logger.warning("⚠️  수집할 종목이 없습니다 (빈 stock_list)")
            return []

        checkpoint_every = max(1, checkpoint_every)

        logger.info(f"📊 밸류에이션 수집 시작: 총 {total}종목 (이어받기: {len(collected)}건 완료됨)")
        start_time = time.monotonic()

        for i, stock in enumerate(remaining):
            symbol = stock["symbol"]
            record = {
                "symbol": symbol,
                "name": stock.get("name"),
                "market": stock.get("market"),
                "per": None,
                "pbr": None,
                "dividend_yield": None,
            }
            try:
                fetched = self.kis_client.get_stock_fundamental(symbol)
                if fetched:
                    record["per"] = fetched.get("per")
                    record["pbr"] = fetched.get("pbr")
                    record["dividend_yield"] = fetched.get("dividend_yield")
            except Exception as e:
                logger.warning(f"⚠️  {symbol}({stock.get('name')}) 조회 실패 - {e}")

            collected.append(record)

            done = len(collected)
            if progress_callback:
                progress_callback(done, total)
            if done % checkpoint_every == 0 or done == total:
                elapsed = time.monotonic() - start_time
                logger.info(f"   진행: {done}/{total} ({done*100//total}%) - 경과 {elapsed:.0f}초")
                self._save_checkpoint(collected)

            if i < len(remaining) - 1:  # 마지막 종목 뒤에는 대기할 필요 없음
                time.sleep(rate_limit_sec)

        logger.info(f"✅ 밸류에이션 수집 완료: {len(collected)}종목")

        if fetch_dividends:
            self._merge_dividend_rates(collected)

        return collected

    def _merge_dividend_rates(self, collected: List[Dict[str, Any]]) -> None:
        """collected를 제자리(in-place)에서 갱신 - 시장별로 배당수익률을 한 번씩만
        (KRX 정보데이터시스템, self.dividend_fetcher) 조회해 종목코드 기준으로 병합한다.
        조회가 실패해도 PER/PBR 수집 결과에는 영향을 주지 않는다(경고만 남기고
        dividend_yield는 None으로 유지)."""
        markets_present = sorted({r.get("market") for r in collected if r.get("market")})
        if not markets_present:
            return

        for market in markets_present:
            try:
                dividend_map = self.dividend_fetcher(market)
            except Exception as e:
                logger.warning(f"⚠️  {market} 배당수익률 일괄 조회 실패 - {e}")
                continue

            if not dividend_map:
                continue

            for record in collected:
                if record.get("market") != market:
                    continue
                rate = dividend_map.get(record.get("symbol"))
                if rate is not None:
                    record["dividend_yield"] = rate

    # ---------- 캐시/체크포인트 ----------

    def _result_cache_path(self) -> str:
        return os.path.join(self.cache_dir, f"valuation_{date.today().isoformat()}.json")

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

        collected = checkpoint.get("collected", [])
        done_symbols = {r["symbol"] for r in collected}
        remaining = [s for s in stock_list if s["symbol"] not in done_symbols]

        if collected:
            logger.info(f"🔄 체크포인트에서 이어받기: {len(collected)}건 완료됨, {len(remaining)}건 남음")

        return collected, remaining

    def _save_checkpoint(self, collected: List[Dict[str, Any]]) -> None:
        """
        진행 중 수집된 결과만 저장한다. 아직 처리하지 못한 나머지(remaining)는 저장하지
        않는다 - _resume_or_start()가 재시작 시점의 stock_list와 collected의 symbol
        차집합으로 다시 계산하므로, remaining을 따로 저장/복원할 필요가 없다.
        """
        checkpoint = {
            "collected": collected,
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

    # 【안전을 위한 기본값】 전체 2,300여 종목이 아니라 앞쪽 일부만 시험 수집.
    # 전체 수집은 python -m market_intelligence.collectors.valuation_collector all 로 실행.
    limit = None if (len(sys.argv) > 1 and sys.argv[1] == "all") else 20

    master = StockMaster()
    stocks = master.get_stock_list(market="ALL", common_stock_only=True)
    if limit:
        stocks = stocks[:limit]
        print(f"⚠️  시험 실행: 앞쪽 {limit}종목만 수집합니다 (전체는 인자로 'all' 전달)")

    collector = ValuationCollector()
    records = collector.get_or_collect(stocks, force_refresh=True)

    valid = [r for r in records if r["per"] and r["pbr"]]
    print(f"\n수집 완료: {len(records)}종목 중 {len(valid)}종목 PER/PBR 확보")
    for r in valid[:10]:
        print(f"  {r['symbol']} {r['name']} ({r['market']}): PER={r['per']}, PBR={r['pbr']}")
