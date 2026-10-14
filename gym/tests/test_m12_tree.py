from pmg.m12_tree import Node


def test_nested():
    tree = Node(name="root", children=[{"name": "a", "children": [{"name": "b"}]}])
    assert tree.size() == 3
