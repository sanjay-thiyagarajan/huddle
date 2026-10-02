from server.engine import privacy


def test_money_buckets():
    assert privacy.money_bucket(0) == "$0-100"
    assert privacy.money_bucket(99.9) == "$0-100"
    assert privacy.money_bucket(100) == "$100-250"
    assert privacy.money_bucket(437) == "$250-500"
    assert privacy.money_bucket(999) == "$500-1000"
    assert privacy.money_bucket(1000) == "$1000+"
    assert privacy.money_bucket(5000) == "$1000+"


def test_hours_buckets():
    assert privacy.hours_bucket(0) == "0-5 h"
    assert privacy.hours_bucket(4.9) == "0-5 h"
    assert privacy.hours_bucket(13) == "10-15 h"
    assert privacy.gap_label_hours(0) == "none"


def test_k_rule():
    two = privacy.reveal_policy(2)
    assert not two.single_limit_detail and "infer your number" in two.warning
    three = privacy.reveal_policy(3)
    assert three.single_limit_detail and three.warning is None


def test_health_text_scan():
    assert privacy.looks_like_health_text("Mum has dementia and insulin")
    assert not privacy.looks_like_health_text("I can do Tuesdays")


def test_leak_guard_detects_and_ignores_token_noise():
    body = '{"x": "ab437cd.1790000000.sig", "y": 12}'
    assert privacy.find_leaks(body, {"Ben": [437]}, viewer="Ana") == []
    assert privacy.find_leaks('{"budget": 437}', {"Ben": [437]}, viewer="Ana")
    assert privacy.find_leaks('{"budget": 437}', {"Ben": [437]}, viewer="Ben") == []
    assert privacy.find_attributed_buckets('Ben: "$250-500"', {"Ben": ["$250-500"]}, "Ana")
