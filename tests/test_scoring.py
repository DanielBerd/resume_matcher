"""Tests for the reply parser (the only pure logic worth testing at this stage)."""

from resume_matcher.scoring import parse_reply


def test_parses_clean_json():
    score, comment = parse_reply('{"score": 85, "comment": "Strong match on Python skills."}')
    assert score == 85
    assert comment == "Strong match on Python skills."


def test_parses_json_with_surrounding_text():
    reply = 'Sure! Here is my rating:\n{"score": 42, "comment": "Partial overlap."}\nHope that helps.'
    score, comment = parse_reply(reply)
    assert score == 42
    assert comment == "Partial overlap."


def test_falls_back_to_first_number():
    score, _ = parse_reply("I would rate this resume 73 out of 100.")
    assert score == 73


def test_clamps_out_of_range_scores():
    score, _ = parse_reply('{"score": 150, "comment": "too enthusiastic"}')
    assert score == 100


def test_unparseable_reply_scores_zero():
    score, comment = parse_reply("I cannot evaluate this.")
    assert score == 0
    assert "Unparseable" in comment or comment
