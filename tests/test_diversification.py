"""diversification.py 테스트 (Phase 6-1) - 업로드 문서 §5/§6의 AI/반도체 예시 그대로."""
from market_intelligence.trade_execution.diversification import diversify_candidates


def _stock(rank, sector, theme):
    return {"rank": rank, "sector": sector, "primary_theme": theme}


class TestDiversifyCandidates:
    def test_document_ai_example(self):
        """문서 §6 예시: 1~4위가 전부 AI 테마면 4위는 제외되고 5위(반도체)가
        대신 선정된다."""
        ranked = [
            _stock(1, "IT", "AI"),
            _stock(2, "IT", "AI"),
            _stock(3, "IT", "AI"),
            _stock(4, "IT", "AI"),
            _stock(5, "반도체", "반도체"),
        ]
        selected = diversify_candidates(ranked, max_positions=10, max_per_sector=10, max_per_theme=3)
        selected_ranks = [s["rank"] for s in selected]
        assert selected_ranks == [1, 2, 3, 5]  # 4위(AI 4번째)만 빠짐

    def test_max_positions_caps_result(self):
        ranked = [_stock(i, f"sector{i}", f"theme{i}") for i in range(1, 21)]
        selected = diversify_candidates(ranked, max_positions=7, max_per_sector=2, max_per_theme=2)
        assert len(selected) == 7

    def test_sector_limit_applies_independently_of_theme(self):
        ranked = [
            _stock(1, "반도체", "AI"),
            _stock(2, "반도체", "로봇"),
            _stock(3, "반도체", "2차전지"),  # sector 한도(2) 초과로 제외돼야 함
            _stock(4, "바이오", "바이오"),
        ]
        selected = diversify_candidates(ranked, max_positions=10, max_per_sector=2, max_per_theme=10)
        selected_ranks = [s["rank"] for s in selected]
        assert selected_ranks == [1, 2, 4]

    def test_missing_sector_or_theme_not_penalized(self):
        """Sector/Theme 매핑이 안 된 종목(None)은 그 축의 집중도 제한에서
        제외하고 통과시킨다 - 결측을 이유로 부당하게 탈락시키지 않는다는
        프로젝트 원칙과 동일."""
        ranked = [_stock(i, None, None) for i in range(1, 6)]
        selected = diversify_candidates(ranked, max_positions=5, max_per_sector=1, max_per_theme=1)
        assert len(selected) == 5

    def test_empty_input(self):
        assert diversify_candidates([], max_positions=7, max_per_sector=2, max_per_theme=2) == []
