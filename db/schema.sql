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