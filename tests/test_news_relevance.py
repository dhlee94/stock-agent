"""Tests for news body extraction (_strip_html) and relevance tagging
(_tag_and_rank_relevance) in news.py.

news.py imports yfinance/pytz at module load, so stub them before import — the
functions under test are pure and don't touch either.
"""
import os
import sys
import types

for _m in ("yfinance", "pytz"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "tools", "stock"))

import news as N  # noqa: E402


def test_strip_html_removes_tags_and_entities():
    assert N._strip_html("<b>Netflix</b> raises&nbsp;guidance<br/>") == "Netflix raises guidance"
    assert N._strip_html("plain text") == "plain text"


def test_strip_html_empty():
    assert N._strip_html("") is None
    assert N._strip_html(None) is None
    assert N._strip_html("<br/>") is None  # markup only → nothing left


def test_relevance_preserves_domain_articles():
    items = [
        {"title": "Netflix Q4 earnings beat", "snippet": "NFLX reported"},
        {"title": "스트리밍 광고요금제 확산", "snippet": "광고 기반 구독 증가"},   # domain, no ticker
        {"title": "Disney+ loses subscribers", "snippet": "streaming wars"},      # domain
    ]
    tagged, direct = N._tag_and_rank_relevance(items, "NFLX", "넷플릭스", "Netflix")
    assert len(tagged) == 3            # nothing dropped — domain articles survive
    assert direct == 1
    assert tagged[0]["relevance"] == "direct"   # direct ranked first
    assert {it["relevance"] for it in tagged} == {"direct", "contextual"}


def test_relevance_matches_korean_name_and_ticker_base():
    items = [
        {"title": "삼성전자 4분기 실적", "snippet": ""},
        {"title": "005930 거래량 급증", "snippet": ""},
        {"title": "반도체 업황 회복", "snippet": ""},   # domain
    ]
    tagged, direct = N._tag_and_rank_relevance(items, "005930.KS", "삼성전자", None)
    assert direct == 2  # 한글명 + 티커베이스(005930)


def test_relevance_no_tokens_marks_all_direct():
    # 종목 정보가 전혀 없으면 판정 불가 → 전부 direct (보수적으로 유지)
    items = [{"title": "시장 동향"}, {"title": "환율 뉴스"}]
    tagged, direct = N._tag_and_rank_relevance(items, None, None, None)
    assert direct == 2
