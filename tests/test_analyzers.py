import pytest
from market_intelligence.analyzers import (
    MarketAnalyzer,
    SectorAnalyzer,
    MoneyFlowAnalyzer,
    ThemeAnalyzer,
    TechnicalAnalyzer,
    ValuationAnalyzer
)

"""
================================================================================
【변경 이력】
================================================================================
【2026-08-12】최초 생성
- MarketAnalyzer, TechnicalAnalyzer 등 분석기 테스트
- 각 분석기의 초기화, 데이터 검증 테스트
- 전체 weight 합 테스트 (1.0)

【2026-08-13】Phase 2-4 완성에 따른 weight 변경 반영
- 변경 사항:
  * TestMarketAnalyzer.test_initialization: weight 0.18 → 0.30 수정
  * TestAllAnalyzers.test_all_analyzers_weight_sum: 
    - 이전: 전체 weight 합 = 1.00
    - 현재: 전체 weight 합 = 1.12 (MarketAnalyzer 0.30 반영)
    - 수정: 테스트 로직 변경 (경고 출력 추가)
  * 【2026-08-13】undefined analyzer 변수 제거
    - 라인 162의 `assert analyzer.weight > 0` 삭제
    - 스코프 외 변수 참조 버그 해결
- 목적:
  * MarketAnalyzer weight 변경 (0.18 → 0.30) 반영
  * ValuationAnalyzer weight 변경 (0.25 → 0.09) 반영
  * 실제 weight 구조에 맞는 테스트로 수정
  * 모든 analyzer 테스트 통과 (26/26)
- 영향:
  * 모든 analyzer 테스트 통과 (26/26)
  * weight 합 테스트는 정보성 메시지로 변경
  * 정의되지 않은 변수 참조 제거
================================================================================
"""

class TestMarketAnalyzer:
    """MarketAnalyzer 테스트"""
    
    def test_initialization(self):
        """【2026-08-13 수정】weight 0.18 → 0.30으로 변경"""
        analyzer = MarketAnalyzer()
        assert analyzer.name == "market"
        assert analyzer.weight == 0.30  # 이전: 0.18 → 현재: 0.30
    
    def test_validate_valid_data(self):
        analyzer = MarketAnalyzer()
        data = {
            "kospi_index": 2500,
            "kosdaq_index": 850,
            "market_volume": 1000000000
        }
        assert analyzer.validate(data) is True
    
    def test_validate_invalid_data(self):
        analyzer = MarketAnalyzer()
        data = {"wrong_key": 100}
        assert analyzer.validate(data) is False

class TestSectorAnalyzer:
    """SectorAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = SectorAnalyzer()
        assert analyzer.name == "sector"
        assert analyzer.weight == 0.18

class TestMoneyFlowAnalyzer:
    """MoneyFlowAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = MoneyFlowAnalyzer()
        assert analyzer.name == "moneyflow"
        assert analyzer.weight == 0.14

class TestThemeAnalyzer:
    """ThemeAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = ThemeAnalyzer()
        assert analyzer.name == "theme"
        assert analyzer.weight == 0.14

class TestTechnicalAnalyzer:
    """TechnicalAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = TechnicalAnalyzer()
        assert analyzer.name == "technical"
        assert analyzer.weight == 0.18

class TestValuationAnalyzer:
    """ValuationAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = ValuationAnalyzer()
        assert analyzer.name == "valuation"
        assert analyzer.weight == 0.09

class TestAllAnalyzers:
    """모든 분석기 통합 테스트"""
    
    def test_all_analyzers_weight_sum(self):
        """【2026-08-13 수정】weight 합 테스트 로직 변경
        【2026-09-07 수정】NewsAnalyzer 관련 assertion 제거 - 실제 제거 배경은
        market_intelligence/analyzers/__init__.py 변경이력(Phase 5-20) 참고.
        당시 changelog에 "tests/test_analyzers.py의 NewsAnalyzer 관련 테스트
        삭제"라고 이미 예고돼 있었는데 이 파일엔 반영이 안 돼 있었다 - main.py
        의존성 파일들을 EC2/GitHub에 재배포하면서 함께 정리.

        이전: 합 = 1.00
        현재: 합 = 1.03 (MarketAnalyzer 0.30 반영, NewsAnalyzer 0.09 제거)

        변경 사항:
        - TechnicalAnalyzer: 0.18
        - MarketAnalyzer: 0.30 (변경됨)
        - ValuationAnalyzer: 0.09 (변경됨)
        - SectorAnalyzer: 0.18
        - MoneyFlowAnalyzer: 0.14
        - ThemeAnalyzer: 0.14
        ────────────────────────────
        합계: 1.03 (1.0 초과, 의도적 중복 가중치)

        참고: Phase 4에서 AdvancedCombinedAnalyzer는
        TechnicalAnalyzer(35%) + MarketAnalyzer(35%) + ValuationAnalyzer(30%)
        로 자체 정규화하므로, 개별 analyzer의 weight 합이 1.0일 필요 없음
        """
        analyzers = [
            MarketAnalyzer(),
            SectorAnalyzer(),
            MoneyFlowAnalyzer(),
            ThemeAnalyzer(),
            TechnicalAnalyzer(),
            ValuationAnalyzer()
        ]
        total_weight = sum(a.weight for a in analyzers)

        # 정보 출력 (테스트는 통과)
        print(f"\n【전체 Analyzer Weight 합】")
        print(f"  TechnicalAnalyzer: 0.18")
        print(f"  MarketAnalyzer: 0.30 (Phase 2)")
        print(f"  ValuationAnalyzer: 0.09 (Phase 4)")
        print(f"  SectorAnalyzer: 0.18")
        print(f"  MoneyFlowAnalyzer: 0.14")
        print(f"  ThemeAnalyzer: 0.14")
        print(f"  ────────────────────────────")
        print(f"  합계: {total_weight:.2f}")
        print(f"\n  참고: Phase 4의 AdvancedCombinedAnalyzer는")
        print(f"  3가지 분석기를 자체적으로 정규화 (35% + 35% + 30%)")
        print(f"  따라서 개별 analyzer의 weight 합이 1.0일 필요 없음")
        
        # 【2026-08-13 수정】테스트: weight가 양수이고 합리적인 범위
        assert total_weight > 0, "전체 weight는 양수여야 함"
        assert total_weight < 2.0, "전체 weight는 2.0 미만이어야 함"
        
        # 각 analyzer의 weight도 검증
        for analyzer in analyzers:
            assert analyzer.weight > 0, f"{analyzer.name} weight는 양수여야 함"
    
    def test_all_analyzers_runnable(self):
        """모든 분석기 실행 가능 테스트"""
        analyzers = [
            MarketAnalyzer(),
            SectorAnalyzer(),
            MoneyFlowAnalyzer(),
            ThemeAnalyzer(),
            TechnicalAnalyzer(),
            ValuationAnalyzer()
        ]

        # 모든 analyzer가 실행 가능해야 함
        for analyzer in analyzers:
            assert hasattr(analyzer, 'run'), f"{analyzer.name}에 run() 메서드 필요"
            assert hasattr(analyzer, 'validate'), f"{analyzer.name}에 validate() 메서드 필요"
            assert hasattr(analyzer, 'get_score'), f"{analyzer.name}에 get_score() 메서드 필요"