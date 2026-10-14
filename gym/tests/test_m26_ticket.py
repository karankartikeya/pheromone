from pmg.m26_ticket import Ticket


def test_escalated():
    assert Ticket(title="x", priority="high").escalated is True


def test_strip_and_enum_value():
    t = Ticket(title="  hi ")
    assert t.title == "hi" and t.priority == "low"
