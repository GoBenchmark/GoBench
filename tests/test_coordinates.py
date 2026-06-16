import pytest

from gobench.core.coordinates import coord_to_point, normalize_move, point_to_coord


def test_coordinates_skip_i():
    assert coord_to_point("A19") == (0, 0)
    assert coord_to_point("H1") == (18, 7)
    assert coord_to_point("J1") == (18, 8)
    assert point_to_coord(18, 8) == "J1"
    with pytest.raises(ValueError):
        coord_to_point("I9")


def test_pass_normalizes():
    assert normalize_move("PASS") == "pass"
