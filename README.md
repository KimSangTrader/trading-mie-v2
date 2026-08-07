# MIE V2.0 - Market Intelligence Engine

Market Intelligence Engine for Automated Trading System

## 🎯 개요

자동매매 시스템을 위한 고급 시장 분석 엔진입니다. 7개의 독립적인 분석기가 협력하여 종합적인 투자 의사결정을 지원합니다.

## 📊 분석기 구성

| 분석기 | 가중치 | 설명 |
|--------|--------|------|
| MarketAnalyzer | 18% | 시장 지표 및 지수 분석 |
| SectorAnalyzer | 18% | 업종 분류 및 성과 분석 |
| MoneyFlowAnalyzer | 14% | 외국인/기관/프로그램/연금 수급 분석 |
| ThemeAnalyzer | 14% | 시장 테마 및 트렌드 분석 |
| NewsAnalyzer | 9% | 뉴스 감정 및 공시 분석 |
| TechnicalAnalyzer | 18% | MACD, RSI, 볼린저 밴드 등 기술적 분석 |
| ValuationAnalyzer | 9% | PER, PBR, 성장성 밸류에이션 |
| **합계** | **100%** | **종합 점수 도출** |

## 🏗️ 프로젝트 구조

trading-mie-v2/
├── market_intelligence/
│ ├── init.py
│ ├── base_analyzer.py
│ ├── intelligence_manager.py
│ ├── analyzers/
│ │ ├── init.py
│ │ ├── market_analyzer.py
│ │ ├── sector_analyzer.py
│ │ ├── moneyflow_analyzer.py
│ │ ├── theme_analyzer.py
│ │ ├── news_analyzer.py
│ │ ├── technical_analyzer.py
│ │ └── valuation_analyzer.py
│ ├── ranking/
│ ├── database/
│ └── utils/
├── tests/
│ ├── init.py
│ ├── test_base_analyzer.py
│ ├── test_intelligence_manager.py
│ └── test_analyzers.py
├── config/
│ └── score_config.yaml
├── main.py
├── requirements.txt
├── README.md
├── .gitignore
└── LICENSE


## 🚀 설치 및 사용

### 1. 저장소 클론

```bash
git clone https://github.com/KimSangTrader/trading-mie-v2.git
cd trading-mie-v2
```

### 2. 가상 환경 설정

```bash
# Windows
python -m venv venv
.\venv\Scripts\Activate.ps1

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 통합 테스트 실행

```bash
python main.py
```

### 5. 단위 테스트 실행

```bash
pytest tests/ -v
pytest tests/ --cov=market_intelligence
```

## 📖 사용 예시

### 기본 사용법

```python
from market_intelligence.intelligence_manager import IntelligenceManager
from market_intelligence.analyzers import (
    MarketAnalyzer, SectorAnalyzer, MoneyFlowAnalyzer,
    ThemeAnalyzer, NewsAnalyzer, TechnicalAnalyzer, ValuationAnalyzer
)

# 1. 매니저 초기화
manager = IntelligenceManager()

# 2. 분석기 등록
manager.register_analyzer(MarketAnalyzer())
manager.register_analyzer(SectorAnalyzer())
# ... (나머지 분석기 등록)

# 3. 분석 데이터 준비
data = {
    "kospi_index": 2500,
    "kosdaq_index": 850,
    "market_volume": 1000000000,
    # ... (기타 데이터)
}

# 4. 분석 실행
results = manager.run_all(data)

# 5. 결과 확인
print(f"Final Score: {results['final_score']}")
```

## 🧪 테스트

### 전체 테스트

```bash
pytest tests/ -v
```

### 테스트 커버리지

```bash
pytest tests/ --cov=market_intelligence --cov-report=html
```

## 📊 테스트 결과

- ✅ **26/26 테스트 통과**
- ✅ BaseAnalyzer 및 ScoreResult 테스트
- ✅ IntelligenceManager 테스트
- ✅ 7개 분석기 테스트
- ✅ 통합 테스트

## 🔄 개발 로드맵

### ✅ PHASE 1 (완료)
- EC2 인스턴스 구축
- Python 개발 환경 설정

### ✅ PHASE 2 (진행 중)
- Week 1: 기본 클래스 및 테스트 완료
- Week 2: GitHub Actions CI/CD 및 EC2 배포

### ⏳ PHASE 3 (향후)
- 각 분석기 로직 구현
- 실시간 데이터 연동

### ⏳ PHASE 4 (향후)
- 백테스팅 엔진
- 성능 최적화

## 🛠️ 기술 스택

- **언어**: Python 3.14+
- **테스트**: pytest, pytest-cov
- **버전 관리**: Git, GitHub
- **배포**: GitHub Actions, AWS EC2
- **데이터베이스**: SQLite (개발), PostgreSQL (프로덕션)

## 📝 라이센스

MIT License

## 👨‍💼 개발자

KimSangTrader

---

**PHASE 2 Week 2 진행 중: 2026-08-19 ~ 2026-08-25**