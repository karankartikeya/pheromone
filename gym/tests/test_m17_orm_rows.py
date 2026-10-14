from pmg.m17_orm_rows import BookRow, load


def test_from_rows():
    assert load([BookRow(id=1, title="Dune")])[0].title == "Dune"
