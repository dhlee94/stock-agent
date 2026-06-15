"""Unit tests for the deterministic news ad/spam filter.

news_filter has no heavy deps (only os/typing), so it imports standalone — no
module stubbing needed, unlike test_flows.py.
"""
import os
import sys

# news_filter uses bare sibling imports like the rest of tools/stock, so put that
# dir on the path (matches how the package is loaded at runtime).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "tools", "stock"))

from news_filter import is_ad_or_spam, filter_news, AD_SPAM_MARKERS  # noqa: E402


def test_drops_obvious_ad_markers():
    assert is_ad_or_spam({"title": "[광고] 무료추천 리딩방 지금 입장"})
    assert is_ad_or_spam({"title": "Sponsored: guaranteed return in 30 days"})


def test_keeps_legitimate_news():
    assert not is_ad_or_spam({"title": "삼성전자, 4분기 영업이익 컨센서스 상회"})
    assert not is_ad_or_spam({"title": "Netflix raises full-year guidance"})


def test_does_not_over_drop_common_words():
    # '추천'/'수익률' 단독은 정상 기사에도 흔하므로 떨구면 안 됨 (정밀도 우선)
    assert not is_ad_or_spam({"title": "증권가, 삼성전자 매수 추천 의견 유지"})
    assert not is_ad_or_spam({"title": "올해 코스피 수익률 회복 흐름"})


def test_checks_snippet_and_publisher_fields():
    assert is_ad_or_spam({"title": "종목 분석", "snippet": "카톡방에서 무료추천 받으세요"})
    assert is_ad_or_spam({"title": "오늘의 시황", "publisher": "VIP방 리딩"})


def test_empty_item_is_kept():
    assert not is_ad_or_spam({})
    assert not is_ad_or_spam({"title": None, "snippet": "", "publisher": None})


def test_filter_news_counts_and_preserves_order():
    items = [
        {"title": "정상 실적 뉴스"},
        {"title": "리딩방 수익률 보장 입장각"},
        {"title": "가이던스 상향"},
    ]
    kept, dropped = filter_news(items)
    assert dropped == 1
    assert [k["title"] for k in kept] == ["정상 실적 뉴스", "가이던스 상향"]


def test_markers_are_lowercased_for_matching():
    # 대문자 마커도 잡혀야 함
    assert is_ad_or_spam({"title": "ADVERTISEMENT — buy now"})
    assert AD_SPAM_MARKERS  # sanity: 기본 마커가 비어있지 않음
