"""
SQLAlchemy ORM Models for MIE V2.0
한국 증시 자동매매 시스템 데이터 모델
"""

from sqlalchemy import (
    Column, Integer, String, Float, BigInteger, DateTime, Text,
    Numeric, Index, create_engine, VARCHAR, DECIMAL, Boolean
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timezone

Base = declarative_base()

# ==========================================
# 1. MarketData 모델
# ==========================================
class MarketData(Base):
    """한국 증시 KOSPI/KOSDAQ 실시간 데이터"""
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), unique=True, nullable=False)
    kospi_index = Column(Numeric(10, 2))
    kosdaq_index = Column(Numeric(10, 2))
    market_volume = Column(BigInteger)
    kospi_change = Column(Numeric(5, 2))
    kosdaq_change = Column(Numeric(5, 2))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index('idx_market_data_timestamp', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<MarketData(timestamp={self.timestamp}, kospi={self.kospi_index}, kosdaq={self.kosdaq_index})>"

# ==========================================
# 2. SectorData 모델
# ==========================================
class SectorData(Base):
    """8개 주요 업종별 지수 데이터"""
    __tablename__ = "sector_data"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    sector_name = Column(String(50), nullable=False)
    sector_index = Column(Numeric(10, 2))
    change_percent = Column(Numeric(5, 2))
    market_cap = Column(BigInteger)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index('idx_sector_data_timestamp', 'timestamp'),
        Index('idx_sector_data_name', 'sector_name'),
    )
    
    def __repr__(self):
        return f"<SectorData(sector={self.sector_name}, index={self.sector_index}, change={self.change_percent}%)>"

# ==========================================
# 3. MoneyFlowData 모델
# ==========================================
class MoneyFlowData(Base):
    """외국인/기관/개인/프로그램 수급 동향"""
    __tablename__ = "money_flow_data"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), unique=True, nullable=False)
    foreign_net = Column(BigInteger)
    institutional_net = Column(BigInteger)
    retail_net = Column(BigInteger)
    program_net = Column(BigInteger)
    foreign_cumulative = Column(BigInteger)
    institutional_cumulative = Column(BigInteger)
    retail_cumulative = Column(BigInteger)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index('idx_flow_data_timestamp', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<MoneyFlowData(timestamp={self.timestamp}, foreign={self.foreign_net}, institutional={self.institutional_net})>"

# ==========================================
# 4. NewsFeed 모델
# ==========================================
class NewsFeed(Base):
    """시장 뉴스 및 상장사 공시"""
    __tablename__ = "news_feed"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text)
    source = Column(String(100))
    news_type = Column(String(50))  # 'news', 'disclosure', 'notice'
    sentiment_score = Column(Numeric(3, 2))  # -1.0 to 1.0
    importance_level = Column(String(20))  # 'critical', 'important', 'minor'
    ticker = Column(String(10))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index('idx_news_timestamp', 'timestamp'),
        Index('idx_news_type', 'news_type'),
        Index('idx_news_sentiment', 'sentiment_score'),
    )
    
    def __repr__(self):
        return f"<NewsFeed(title={self.title[:50]}, sentiment={self.sentiment_score})>"

# ==========================================
# 5. TechnicalIndicators 모델
# ==========================================
class TechnicalIndicators(Base):
    """MACD, RSI, 볼린저밴드, 이동평균선 기술 지표"""
    __tablename__ = "technical_indicators"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), unique=True, nullable=False)
    macd_value = Column(Numeric(10, 4))
    macd_signal = Column(Numeric(10, 4))
    macd_histogram = Column(Numeric(10, 4))
    rsi_value = Column(Numeric(5, 2))
    bb_upper = Column(Numeric(10, 2))
    bb_middle = Column(Numeric(10, 2))
    bb_lower = Column(Numeric(10, 2))
    bb_width = Column(Numeric(10, 2))
    ma5 = Column(Numeric(10, 2))
    ma20 = Column(Numeric(10, 2))
    ma60 = Column(Numeric(10, 2))
    ma120 = Column(Numeric(10, 2))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index('idx_technical_timestamp', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<TechnicalIndicators(timestamp={self.timestamp}, rsi={self.rsi_value}, macd={self.macd_value})>"

# ==========================================
# 6. AnalysisResults 모델
# ==========================================
class AnalysisResults(Base):
    """7개 분석기 종합 점수 및 추천"""
    __tablename__ = "analysis_results"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), unique=True, nullable=False)
    market_score = Column(Numeric(5, 2))
    sector_score = Column(Numeric(5, 2))
    moneyflow_score = Column(Numeric(5, 2))
    theme_score = Column(Numeric(5, 2))
    news_score = Column(Numeric(5, 2))
    technical_score = Column(Numeric(5, 2))
    valuation_score = Column(Numeric(5, 2))
    final_score = Column(Numeric(5, 2))
    market_sentiment = Column(String(100))
    recommendation = Column(String(200))
    confidence_level = Column(Numeric(3, 2))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index('idx_analysis_timestamp', 'timestamp'),
        Index('idx_analysis_score', 'final_score'),
    )
    
    def __repr__(self):
        return f"<AnalysisResults(timestamp={self.timestamp}, final_score={self.final_score}, recommendation={self.recommendation})>"

# ==========================================
# 7. TradingHistory 모델 (향후 자동매매용)
# ==========================================
class TradingHistory(Base):
    """자동매매 거래 기록"""
    __tablename__ = "trading_history"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ticker = Column(String(10), nullable=False)
    trade_type = Column(String(10))  # 'BUY', 'SELL'
    quantity = Column(Integer)
    price = Column(Numeric(10, 2))
    total_amount = Column(BigInteger)
    signal_source = Column(String(100))
    confidence = Column(Numeric(3, 2))
    result = Column(String(20))  # 'pending', 'executed', 'cancelled'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index('idx_trading_timestamp', 'timestamp'),
        Index('idx_trading_ticker', 'ticker'),
    )
    
    def __repr__(self):
        return f"<TradingHistory(ticker={self.ticker}, type={self.trade_type}, quantity={self.quantity})>"

# ==========================================
# 8. SystemStatus 모델
# ==========================================
class SystemStatus(Base):
    """시스템 상태 모니터링"""
    __tablename__ = "system_status"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    status = Column(String(50))  # 'running', 'error', 'maintenance'
    message = Column(Text)
    last_analysis_time = Column(DateTime)
    last_market_update = Column(DateTime)
    analyzer_health = Column(Text)  # JSON 형식
    api_status = Column(String(50))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        Index('idx_system_status_timestamp', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<SystemStatus(timestamp={self.timestamp}, status={self.status})>"

# ==========================================
# 9. StockValuation 모델 (Phase 5: 상대평가 방식)
# ==========================================
class StockValuation(Base):
    """종목별 PER/PBR/배당수익률 및 시장(KOSPI/KOSDAQ) 상대평가 결과

    ValuationCollector가 수집한 원본 값(per/pbr/dividend_yield)과
    MarketValuation이 계산한 시장 중앙값(market_per 등),
    ValuationAnalyzer가 산출한 상대점수(*_relative_score)/최종점수를 함께 저장한다.
    market_data 등 시장 전체를 다루는 테이블과 달리 한 번의 수집(timestamp)에
    종목 수만큼 행이 생기므로(sector_data와 동일한 패턴) timestamp 단독으로는
    unique 제약을 걸지 않는다 - 대신 (ticker, timestamp) 조합으로 스키마에서
    유일성을 보장한다(schema.sql 참고).
    """
    __tablename__ = "stock_valuation"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ticker = Column(String(10), nullable=False)
    market = Column(String(10))  # 'KOSPI', 'KOSDAQ'
    per = Column(Numeric(10, 2))
    pbr = Column(Numeric(10, 2))
    dividend_yield = Column(Numeric(5, 2))
    market_per = Column(Numeric(10, 2))
    market_pbr = Column(Numeric(10, 2))
    market_dividend_yield = Column(Numeric(5, 2))
    # 【2026-08-24, Phase 5-19】Sector별 밸류에이션 중앙값 - 위 market_per 등(시장
    # 전체 중앙값)과 별도로 저장한다(기존 컬럼 의미는 안 바꿈). Sector 표본이
    # 부족하거나 sector 자체가 없으면 NULL로 남는다(0이나 시장값으로 대신 채우지
    # 않음 - StockAnalyzer가 이 컬럼이 NULL이면 market_per로 자동 대체하도록 이미
    # 설계돼 있으므로, 여기서 값을 만들어 채우면 그 자동 대체가 조용히 막힌다).
    sector = Column(String(50))
    sector_per_median = Column(Numeric(10, 2))
    sector_pbr_median = Column(Numeric(10, 2))
    sector_dividend_median = Column(Numeric(5, 2))
    per_relative_score = Column(Numeric(5, 2))
    pbr_relative_score = Column(Numeric(5, 2))
    dividend_relative_score = Column(Numeric(5, 2))
    valuation_score = Column(Numeric(5, 2))
    data_quality = Column(Numeric(5, 2))  # 0~100, 확보된 지표 비율
    data_source = Column(String(20))  # 'relative', 'insufficient_data', 'not_applicable'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index('idx_stock_valuation_timestamp', 'timestamp'),
        Index('idx_stock_valuation_ticker', 'ticker'),
        Index('idx_stock_valuation_market', 'market'),
    )

    def __repr__(self):
        return f"<StockValuation(ticker={self.ticker}, market={self.market}, per={self.per}, valuation_score={self.valuation_score})>"

# ==========================================
# 10. 종목별 Sector/Theme 매핑 테이블 (Phase 5-12)
# ==========================================
class StockSectorMapping(Base):
    """종목별 Analysis_Sector 매핑 - 사용자가 1차로 분류해 엑셀(전체종목_매핑 시트)로
    전달한 결과를 그대로 저장한다.

    stock_valuation과 동일한 "배치(timestamp)" 패턴 - 사용자가 분류를 다시 정리해서
    새 엑셀을 주면 새 timestamp로 통째로 다시 insert하고, 분석은 항상 최신 배치
    (MAX(timestamp))만 사용한다. 과거 배치는 지우지 않고 이력으로 남긴다.
    """
    __tablename__ = "stock_sector_mapping"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ticker = Column(String(10), nullable=False)
    name = Column(String(50))
    market = Column(String(10))       # 정규화된 값: 'KOSPI', 'KOSDAQ', 'KONEX'
    market_raw = Column(String(10))   # 엑셀 원본 라벨: '유가', '코스닥', '코넥스'
    krx_industry = Column(String(100))  # KRX_원본업종
    main_products = Column(Text)        # 주요제품
    sector = Column(String(50), nullable=False)  # Analysis_Sector
    needs_review = Column(Boolean, default=False)  # 검토필요여부
    sector_method = Column(String(50))   # Sector_판정방식
    theme_method = Column(String(100))   # Theme_판정방식
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index('idx_stock_sector_mapping_timestamp', 'timestamp'),
        Index('idx_stock_sector_mapping_ticker', 'ticker'),
        Index('idx_stock_sector_mapping_sector', 'sector'),
    )

    def __repr__(self):
        return f"<StockSectorMapping(ticker={self.ticker}, sector={self.sector}, market={self.market})>"


class StockPriceHistory(Base):
    """종목별 일봉(OHLCV) 히스토리 (Phase 5-13: 계층형 스코어링용 선행 데이터)

    docs/hierarchical_scoring_plan.md Phase 1 참고. 방법론 문서(sector_analy_method.txt)의
    Sector/Theme/종목 점수 공식(5·20·60일 수익률, 상대강도, 상승확산도, 거래대금 증가 등)이
    모두 종목별 일별 시계열을 전제로 하는데, 이 테이블이 생기기 전에는 어디에도 저장되지
    않고 있었다(data/kis_client.py의 get_stock_daily_chart()로 "가져오는" 방법만 있었음).

    stock_valuation/stock_sector_mapping처럼 "매번 새 timestamp로 통째로 insert"하는
    배치 스냅샷 패턴이 아니다 - 종목의 특정 거래일 시세는 사실 하나뿐이므로
    (ticker, trade_date) 조합으로 유일해야 하고, 수집을 여러 번 반복해도 이미 있는
    거래일은 다시 만들지 않고 새로 생긴 거래일만 누적된다(파이프라인 쪽 책임 -
    market_intelligence/collectors/price_history_pipeline.py 참고).
    """
    __tablename__ = "stock_price_history"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), nullable=False)
    market = Column(String(10))  # 'KOSPI', 'KOSDAQ', 'KONEX'
    trade_date = Column(String(8), nullable=False)  # 'YYYYMMDD' - KIS API 원본 형식 그대로
    open = Column(Numeric(12, 2))
    high = Column(Numeric(12, 2))
    low = Column(Numeric(12, 2))
    close = Column(Numeric(12, 2))
    volume = Column(BigInteger)
    collected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index('idx_stock_price_history_ticker_date', 'ticker', 'trade_date', unique=True),
        Index('idx_stock_price_history_trade_date', 'trade_date'),
    )

    def __repr__(self):
        return f"<StockPriceHistory(ticker={self.ticker}, trade_date={self.trade_date}, close={self.close})>"


class StockHierarchicalScore(Base):
    """계층형(시장→Sector→Theme→종목) 최종 순위 스냅샷 (Phase 5-16)

    market_intelligence/hierarchical_ranker.py의 rank_stocks() 결과를 그대로 저장한다.
    AnalysisResults 테이블에 컬럼을 추가하는 대신 별도 테이블로 둔 이유: AnalysisResults는
    timestamp에 UNIQUE 제약이 걸린 "실행 1회당 요약 행 1개" 구조라 종목별로 여러 행이
    필요한 이 데이터와 맞지 않는다. 대신 stock_valuation과 동일한 배치(timestamp) 패턴을
    따른다 - 실행마다 새 timestamp로 종목 수만큼 insert하고, 조회는 항상 최신 배치만 본다.
    """
    __tablename__ = "stock_hierarchical_scores"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ticker = Column(String(10), nullable=False)
    market = Column(String(10))
    sector = Column(String(50))
    primary_theme = Column(String(50))
    market_score = Column(Numeric(5, 2))
    sector_score = Column(Numeric(5, 2))
    theme_score = Column(Numeric(5, 2))
    stock_score = Column(Numeric(5, 2))
    final_score = Column(Numeric(5, 2))
    sector_rank = Column(Integer)
    theme_rank = Column(Integer)
    overall_rank = Column(Integer)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index('idx_stock_hierarchical_scores_timestamp', 'timestamp'),
        Index('idx_stock_hierarchical_scores_ticker', 'ticker'),
        Index('idx_stock_hierarchical_scores_final_score', 'final_score'),
    )

    def __repr__(self):
        return f"<StockHierarchicalScore(ticker={self.ticker}, final_score={self.final_score})>"


class StockThemeMapping(Base):
    """종목별 Theme 매핑 - 종목 1개가 여러 테마에 속할 수 있어(Primary + Secondary)
    stock_sector_mapping과 별도로 다대다(종목:테마) 형태로 저장한다.

    is_primary=True면 엑셀의 Primary_Theme, False면 Secondary_Themes(콤마로 구분된
    여러 값을 각각 한 행씩 분리)에서 온 것이다. batch는 timestamp로
    stock_sector_mapping과 동일하게 맞춘다(같은 임포트 실행에서 나온 값).
    """
    __tablename__ = "stock_theme_mapping"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ticker = Column(String(10), nullable=False)
    theme = Column(String(50), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index('idx_stock_theme_mapping_timestamp', 'timestamp'),
        Index('idx_stock_theme_mapping_ticker', 'ticker'),
        Index('idx_stock_theme_mapping_theme', 'theme'),
    )

    def __repr__(self):
        return f"<StockThemeMapping(ticker={self.ticker}, theme={self.theme}, is_primary={self.is_primary})>"


class TradePosition(Base):
    """현재 보유 중인 매매 포지션 추적 (Phase 6-3: 실제 매매 프로그램).

    기존 TradingHistory는 "개별 거래 기록"(체결 1건 = 1행, 재활용해서 계속 씀 -
    market_intelligence/trade_execution_pipeline.py가 매수/매도 체결마다 여기 1행씩
    남긴다)용이라 "지금 이 종목을 얼마에 몇 주 들고 있고 손절가가 어디인지"처럼
    시간에 따라 값이 바뀌는(UPDATE되는) 상태를 표현할 수 없다 - stop_price/
    highest_price/average_price/quantity/entry_count/partial_profit_taken은 전부
    보유 기간 내내 계속 갱신되는 값이라 append-only인 TradingHistory와 근본적으로
    다른 테이블이 필요했다(Phase 6-1 docs 변경이력의 "아직 안 한 것" 항목 그대로).

    market_intelligence/trade_execution/의 순수 계산기(pyramiding.should_add,
    exit_engine.analyze_exit/update_stop)가 요구하는 position 딕셔너리 필드와
    1:1로 대응하도록 컬럼을 설계했다 - trade_execution_pipeline.py가 이 ORM 행을
    그대로 dict로 변환해서 순수 계산기에 넘긴다(변환 함수: position_to_dict()).
    """
    __tablename__ = "trade_positions"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), nullable=False)
    market = Column(String(10))  # 'KOSPI', 'KOSDAQ'
    sector = Column(String(50))
    primary_theme = Column(String(50))
    status = Column(String(10), nullable=False, default="OPEN")  # 'OPEN' | 'CLOSED'

    entry_price = Column(Numeric(12, 2))          # 최초 1차 매수가(고정, 이후 안 바뀜)
    entry_rank = Column(Integer)                    # 최초 매수 시점의 계층형 overall_rank(고정)
    entry_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    initial_stop_price = Column(Numeric(12, 2))    # 최초 계산된 손절가(고정, exit_engine이 INITIAL_STOP/TRAILING_STOP 구분에 사용)
    initial_risk_per_share = Column(Numeric(12, 2))  # entry_price - initial_stop_price(고정) - R 배수 계산의 분모
    stop_price = Column(Numeric(12, 2))              # 현재 유효 손절가(exit_engine.update_stop()이 위로만 갱신)
    highest_price = Column(Numeric(12, 2))           # 보유 기간 중 최고가(트레일링 스톱 계산용)

    average_price = Column(Numeric(12, 2))           # 현재 평균단가(피라미딩 시 갱신)
    quantity = Column(Integer)                        # 현재 보유 수량(부분익절/피라미딩마다 갱신)
    target_shares = Column(Integer)                    # 최초 진입 시 position_sizer.calculate_position()으로
                                                          # 계산한 목표 총수량(고정) - 1/2/3차 분할매수 비중
                                                          # (split_entry_shares())을 이 값 기준으로 나눈다
    entry_count = Column(Integer, default=1)          # 지금까지의 분할매수(피라미딩 포함) 횟수
    last_entry_price = Column(Numeric(12, 2))        # 가장 최근 매수 체결가(피라미딩 트리거 계산용)
    partial_profit_taken = Column(Boolean, default=False)  # +2R 부분 익절을 이미 실행했는지

    closed_at = Column(DateTime)
    close_price = Column(Numeric(12, 2))
    close_reason = Column(String(30))  # exit_engine의 reason 그대로: INITIAL_STOP/TRAILING_STOP/EMERGENCY_EXIT/RANK_COLLAPSE/SECTOR_THEME_COLLAPSE/TURTLE_10DAY_EXIT 등

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index('idx_trade_positions_ticker', 'ticker'),
        Index('idx_trade_positions_status', 'status'),
    )

    def __repr__(self):
        return f"<TradePosition(ticker={self.ticker}, status={self.status}, quantity={self.quantity}, stop_price={self.stop_price})>"


# ==========================================
# Database Session 관리
# ==========================================

def get_database_url(
    user: str = "mieadmin",
    password: str = "MieV2Postgres2026!",
    host: str = "localhost",
    port: int = 5432,
    database: str = "postgres"
) -> str:
    """데이터베이스 연결 URL 생성"""
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"

def create_session(database_url: str):
    """데이터베이스 세션 생성"""
    engine = create_engine(database_url, echo=False, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal, engine

def create_tables(engine):
    """모든 테이블 생성"""
    Base.metadata.create_all(bind=engine)

# ==========================================
# 모델 목록
# ==========================================
__all__ = [
    'Base',
    'MarketData',
    'SectorData',
    'MoneyFlowData',
    'NewsFeed',
    'TechnicalIndicators',
    'AnalysisResults',
    'TradingHistory',
    'SystemStatus',
    'StockValuation',
    'StockSectorMapping',
    'StockThemeMapping',
    'StockPriceHistory',
    'StockHierarchicalScore',
    'TradePosition',
    'get_database_url',
    'create_session',
    'create_tables',
]