from pmg.m14_draft_copy import Draft, bump


def test_bump():
    assert bump(Draft(title="t")).version == 2


def test_original_untouched():
    d = Draft(title="t")
    bump(d)
    assert d.version == 1
