from pmg.m28_feature_flags import enabled


def test_extra_flags_kept():
    assert enabled({"beta": True, "dark_mode": True, "x": False}) == ["beta", "dark_mode"]
