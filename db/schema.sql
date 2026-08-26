-- ==========================================
-- MIE V2.0 PostgreSQL Database Schema
-- 한국 증시 (KOSPI/KOSDAQ) 자동매매 시스템
-- ==========================================

-- 1. 시장 데이터 테이블
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    kospi_index DECIMAL(10, 2),
    kosdaq_index DECIMAL(10, 2),
    market_volume BIGINT,
    kospi_change DECIMAL(5, 2),
    kosdaq_change DECIMAL(5, 2),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_market_timestamp UNIQUE(timestamp)
);

CREATE INDEX idx_market_data_timestamp ON market_data(timestamp DESC);

-- 2. 업종별 데이터 테이블
CREATE TABLE IF NOT EXISTS sector_data (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sector_name VARCHAR(50) NOT NULL,
    sector_index DECIMAL(10, 2),
    change_percent DECIMAL(5, 2),
    market_cap BIGINT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_sector_timestamp UNIQUE(sector_name, timestamp)
);

CREATE INDEX idx_sector_data_timestamp ON sector_data(timestamp DESC);
CREATE INDEX idx_sector_data_name ON sector_data(sector_name);

-- 3. 수급 데이터 테이블
CREATE TABLE IF NOT EXISTS money_flow_data (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    foreign_net BIGINT,
    institutional_net BIGINT,
    retail_net BIGINT,
    program_net BIGINT,
    foreign_cumulative BIGINT,
    institutional_cumulative BIGINT,
    retail_cumulative BIGINT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_flow_timestamp UNIQUE(timestamp)
);

CREATE INDEX idx_flow_data_timestamp ON money_flow_data(timestamp DESC);

-- 4. 뉴스/공시 테이블
CREATE TABLE IF NOT EXISTS news_feed (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    title VARCHAR(500) NOT NULL,
    content TEXT,
    source VARCHAR(100),
    news_type VARCHAR(50), -- 'news', 'disclosure', 'notice'
    sentiment_score DECIMAL(3, 2), -- -1.0 to 1.0
    importance_level VARCHAR(20), -- 'critical', 'important', 'minor'
    ticker VARCHAR(10), -- 종목코드 (해당시)
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_news_timestamp ON news_feed(timestamp DESC);
CREATE INDEX idx_news_type ON news_feed(news_type);
CREATE INDEX idx_news_sentiment ON news_feed(sentiment_score DESC);

-- 5. 기술 지표 테이블
CREATE TABLE IF NOT EXISTS technical_indicators (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    macd_value DECIMAL(10, 4),
    macd_signal DECIMAL(10, 4),
    macd_histogram DECIMAL(10, 4),
    rsi_value DECIMAL(5, 2),
    bb_upper DECIMAL(10, 2),
    bb_middle DECIMAL(10, 2),
    bb_lower DECIMAL(10, 2),
    bb_width DECIMAL(10, 2),
    ma5 DECIMAL(10, 2),
    ma20 DECIMAL(10, 2),
    ma60 DECIMAL(10, 2),
    ma120 DECIMAL(10, 2),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_technical_timestamp UNIQUE(timestamp)
);

CREATE INDEX idx_technical_timestamp ON technical_indicators(timestamp DESC);

-- 6. 분석 결과 테이블
CREATE TABLE IF NOT EXISTS analysis_results (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    market_score DECIMAL(5, 2),
    sector_score DECIMAL(5, 2),
    moneyflow_score DECIMAL(5, 2),
    theme_score DECIMAL(5, 2),
    news_score DECIMAL(5, 2),
    technical_score DECIMAL(5, 2),
    valuation_score DECIMAL(5, 2),
    final_score DECIMAL(5, 2),
    market_sentiment VARCHAR(100),
    recommendation VARCHAR(200),
    confidence_level DECIMAL(3, 2),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_analysis_timestamp UNIQUE(timestamp)
);

CREATE INDEX idx_analysis_timestamp ON analysis_results(timestamp DESC);
CREATE INDEX idx_analysis_score ON analysis_results(final_score DESC);

-- 7. 거래 기록 테이블 (향후 자동매매용)
CREATE TABLE IF NOT EXISTS trading_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ticker VARCHAR(10) NOT NULL,
    trade_type VARCHAR(10), -- 'BUY', 'SELL'
    quantity INTEGER,
    price DECIMAL(10, 2),
    total_amount BIGINT,
    signal_source VARCHAR(100),
    confidence DECIMAL(3, 2),
    result VARCHAR(20), -- 'pending', 'executed', 'cancelled'
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trading_timestamp ON trading_history(timestamp DESC);
CREATE INDEX idx_trading_ticker ON trading_history(ticker);

-- 8. 시스템 상태 테이블
CREATE TABLE IF NOT EXISTS system_status (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50), -- 'running', 'error', 'maintenance'
    message TEXT,
    last_analysis_time TIMESTAMP,
    last_market_update TIMESTAMP,
    analyzer_health TEXT, -- JSON 형식
    api_status VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_system_status_timestamp ON system_status(timestamp DESC);

-- 9. 종목별 밸류에이션(상대평가) 테이블 (Phase 5)
CREATE TABLE IF NOT EXISTS stock_valuation (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ticker VARCHAR(10) NOT NULL,
    market VARCHAR(10), -- 'KOSPI', 'KOSDAQ'
    per DECIMAL(10, 2),
    pbr DECIMAL(10, 2),
    dividend_yield DECIMAL(5, 2),
    market_per DECIMAL(10, 2),
    market_pbr DECIMAL(10, 2),
    market_dividend_yield DECIMAL(5, 2),
    -- 【2026-08-24, Phase 5-19】Sector별 밸류에이션 중앙값 (market_per 등과 별도,
    -- 표본 부족/sector 미상이면 NULL로 남김 - migrate_add_sector_valuation_columns.py 참고)
    sector VARCHAR(50),
    sector_per_median DECIMAL(10, 2),
    sector_pbr_median DECIMAL(10, 2),
    sector_dividend_median DECIMAL(5, 2),
    per_relative_score DECIMAL(5, 2),
    pbr_relative_score DECIMAL(5, 2),
    dividend_relative_score DECIMAL(5, 2),
    valuation_score DECIMAL(5, 2),
    data_quality DECIMAL(5, 2), -- 0~100, 확보된 지표 비율
    data_source VARCHAR(20), -- 'relative', 'insufficient_data', 'not_applicable'
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_stock_valuation_ticker_timestamp UNIQUE(ticker, timestamp)
);

CREATE INDEX idx_stock_valuation_timestamp ON stock_valuation(timestamp DESC);
CREATE INDEX idx_stock_valuation_ticker ON stock_valuation(ticker);
CREATE INDEX idx_stock_valuation_market ON stock_valuation(market);

-- 10. 종목별 Sector 매핑 테이블 (Phase 5-12) - 사용자가 1차 분류한 엑셀 원본
CREATE TABLE IF NOT EXISTS stock_sector_mapping (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 임포트 배치 시각
    ticker VARCHAR(10) NOT NULL,
    name VARCHAR(50),
    market VARCHAR(10),       -- 정규화: 'KOSPI', 'KOSDAQ', 'KONEX'
    market_raw VARCHAR(10),   -- 엑셀 원본 라벨: '유가', '코스닥', '코넥스'
    krx_industry VARCHAR(100),
    main_products TEXT,
    sector VARCHAR(50) NOT NULL,
    needs_review BOOLEAN DEFAULT FALSE,
    sector_method VARCHAR(50),
    theme_method VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stock_sector_mapping_timestamp ON stock_sector_mapping(timestamp DESC);
CREATE INDEX idx_stock_sector_mapping_ticker ON stock_sector_mapping(ticker);
CREATE INDEX idx_stock_sector_mapping_sector ON stock_sector_mapping(sector);

-- 11. 종목별 Theme 매핑 테이블 (Phase 5-12) - 종목:테마 다대다(Primary + Secondary)
CREATE TABLE IF NOT EXISTS stock_theme_mapping (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, -- stock_sector_mapping과 동일 배치
    ticker VARCHAR(10) NOT NULL,
    theme VARCHAR(50) NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stock_theme_mapping_timestamp ON stock_theme_mapping(timestamp DESC);
CREATE INDEX idx_stock_theme_mapping_ticker ON stock_theme_mapping(ticker);
CREATE INDEX idx_stock_theme_mapping_theme ON stock_theme_mapping(theme);

-- 12. 종목별 일봉(OHLCV) 히스토리 (Phase 5-13) - 계층형 스코어링(docs/hierarchical_scoring_plan.md)
-- 선행 데이터. 배치 스냅샷 패턴이 아니라 (ticker, trade_date)로 유일한 사실 테이블.
CREATE TABLE IF NOT EXISTS stock_price_history (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    market VARCHAR(10), -- 'KOSPI', 'KOSDAQ', 'KONEX'
    trade_date VARCHAR(8) NOT NULL, -- 'YYYYMMDD'
    open DECIMAL(12, 2),
    high DECIMAL(12, 2),
    low DECIMAL(12, 2),
    close DECIMAL(12, 2),
    volume BIGINT,
    collected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_stock_price_history_ticker_date UNIQUE(ticker, trade_date)
);

CREATE INDEX idx_stock_price_history_ticker_date ON stock_price_history(ticker, trade_date DESC);
CREATE INDEX idx_stock_price_history_trade_date ON stock_price_history(trade_date);

-- 13. 계층형(시장→Sector→Theme→종목) 최종 순위 스냅샷 (Phase 5-16)
-- analysis_results와 별도 테이블인 이유는 db/models.py StockHierarchicalScore 문서 참고.
CREATE TABLE IF NOT EXISTS stock_hierarchical_scores (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ticker VARCHAR(10) NOT NULL,
    market VARCHAR(10),
    sector VARCHAR(50),
    primary_theme VARCHAR(50),
    market_score DECIMAL(5, 2),
    sector_score DECIMAL(5, 2),
    theme_score DECIMAL(5, 2),
    stock_score DECIMAL(5, 2),
    final_score DECIMAL(5, 2),
    sector_rank INTEGER,
    theme_rank INTEGER,
    overall_rank INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stock_hierarchical_scores_timestamp ON stock_hierarchical_scores(timestamp DESC);
CREATE INDEX idx_stock_hierarchical_scores_ticker ON stock_hierarchical_scores(ticker);
CREATE INDEX idx_stock_hierarchical_scores_final_score ON stock_hierarchical_scores(final_score DESC);

-- 14. 현재 보유 중인 매매 포지션 추적 (Phase 6-3) - db/models.py TradePosition 문서 참고.
-- trading_history(7번, append-only 개별 체결 기록)와 달리 이 테이블은 UPDATE되는
-- "현재 상태"(손절가/최고가/평균단가/보유수량 등)를 담는다.
CREATE TABLE IF NOT EXISTS trade_positions (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    market VARCHAR(10),
    sector VARCHAR(50),
    primary_theme VARCHAR(50),
    status VARCHAR(10) NOT NULL DEFAULT 'OPEN', -- 'OPEN', 'CLOSED'
    entry_price DECIMAL(12, 2),
    entry_rank INTEGER,
    entry_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    initial_stop_price DECIMAL(12, 2),
    initial_risk_per_share DECIMAL(12, 2),
    stop_price DECIMAL(12, 2),
    highest_price DECIMAL(12, 2),
    average_price DECIMAL(12, 2),
    quantity INTEGER,
    target_shares INTEGER,
    entry_count INTEGER DEFAULT 1,
    last_entry_price DECIMAL(12, 2),
    partial_profit_taken BOOLEAN DEFAULT FALSE,
    closed_at TIMESTAMP,
    close_price DECIMAL(12, 2),
    close_reason VARCHAR(30),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trade_positions_ticker ON trade_positions(ticker);
CREATE INDEX idx_trade_positions_status ON trade_positions(status);

-- ==========================================
-- 권한 설정
-- ==========================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO mieadmin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO mieadmin;
GRANT USAGE ON SCHEMA public TO mieadmin;

-- ==========================================
-- 주석 추가 (메타데이터)
-- ==========================================
COMMENT ON TABLE market_data IS '한국 증시 KOSPI/KOSDAQ 실시간 데이터';
COMMENT ON TABLE sector_data IS '8개 주요 업종별 지수 데이터';
COMMENT ON TABLE money_flow_data IS '외국인/기관/개인/프로그램 수급 데이터';
COMMENT ON TABLE news_feed IS '시장 뉴스 및 상장사 공시';
COMMENT ON TABLE technical_indicators IS 'MACD, RSI, 볼린저밴드, 이동평균선 지표';
COMMENT ON TABLE analysis_results IS '7개 분석기 종합 점수 및 추천';
COMMENT ON TABLE trading_history IS '자동매매 거래 기록 (향후)';
COMMENT ON TABLE system_status IS '시스템 상태 모니터링';
COMMENT ON TABLE stock_valuation IS '종목별 PER/PBR/배당수익률 및 시장(KOSPI/KOSDAQ) 상대평가 결과';
COMMENT ON TABLE stock_sector_mapping IS '종목별 Analysis_Sector 매핑 (사용자 1차 분류 엑셀 원본)';
COMMENT ON TABLE stock_theme_mapping IS '종목별 Theme 매핑 (Primary/Secondary, 다대다)';
COMMENT ON TABLE stock_price_history IS '종목별 일봉(OHLCV) 히스토리 (계층형 스코어링 선행 데이터)';
COMMENT ON TABLE stock_hierarchical_scores IS '시장→Sector→Theme→종목 계층형 최종 순위 스냅샷';
COMMENT ON TABLE trade_positions IS '현재 보유 중인 매매 포지션 추적 (Phase 6-3, UPDATE되는 상태값)';