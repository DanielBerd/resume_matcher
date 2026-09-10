"""Tests for choosing which server model to preselect."""

from resume_matcher.cli import pick_default_model


def test_matches_preferred_name_as_substring():
    models = ["unsloth/gemma-4-e4b-it-qat-GGUF", "unsloth/gemma-4-12b-it-qat-GGUF"]
    assert pick_default_model(models, "gemma-4-12b") == "unsloth/gemma-4-12b-it-qat-GGUF"


def test_match_is_case_insensitive():
    models = ["Unsloth/Gemma-4-26B-A4B-it-QAT"]
    assert pick_default_model(models, "gemma-4-26b-a4b") == models[0]


def test_falls_back_to_first_model():
    models = ["some-other-model", "another-model"]
    assert pick_default_model(models, "gemma-4-12b") == "some-other-model"


def test_empty_preference_uses_first_model():
    assert pick_default_model(["a", "b"], "") == "a"
