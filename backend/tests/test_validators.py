import pytest
from app.utils.validators import validate_safe_id


def test_valid_ids():
    assert validate_safe_id("sim_abc123") == "sim_abc123"
    assert validate_safe_id("project-1") == "project-1"
    assert validate_safe_id("MyReport_v2") == "MyReport_v2"


def test_path_traversal_rejected():
    with pytest.raises(ValueError):
        validate_safe_id("../../../etc/passwd")


def test_empty_rejected():
    with pytest.raises(ValueError):
        validate_safe_id("")


def test_special_chars_rejected():
    with pytest.raises(ValueError):
        validate_safe_id("sim;rm -rf /")


def test_none_rejected():
    with pytest.raises(ValueError):
        validate_safe_id(None)
