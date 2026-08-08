"""
SQLAlchemy ORM Models for MIE V2.0
한국 증시 자동매매 시스템 데이터 모델
"""

from sqlalchemy import (
    Column, Integer, String, Float, BigInteger, DateTime, Text,
    Numeric, Index, create_engine, VARCHAR, DECIMAL
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
    'get_database_url',
    'create_session',
    'create_tables',
]