"""Tests for discord_bot.response_router."""

from discord_bot.response_router import route_response


def test_no_markers():
    routed = route_response("Just some plain text.")
    assert routed.public == "Just some plain text."
    assert routed.whispers == []
    assert routed.public_announcements == []


def test_public_marker_extracted():
    text = (
        "Private reply to player.\n\n"
        "[PUBLIC]The NPC sheathes his blade and joins the party.[/PUBLIC]"
    )
    routed = route_response(text)
    assert routed.public == "Private reply to player."
    assert routed.public_announcements == [
        "The NPC sheathes his blade and joins the party."
    ]


def test_multiple_public_markers():
    text = (
        "Some DM text.\n\n"
        "[PUBLIC]First observable thing.[/PUBLIC]\n"
        "More DM text.\n"
        "[PUBLIC]Second observable thing.[/PUBLIC]"
    )
    routed = route_response(text)
    assert "Some DM text." in routed.public
    assert "More DM text." in routed.public
    assert routed.public_announcements == [
        "First observable thing.",
        "Second observable thing.",
    ]


def test_public_and_private_markers_together():
    text = (
        "Reply to player.\n\n"
        "[PUBLIC]The door opens.[/PUBLIC]\n\n"
        "[PRIVATE:Thorin]You notice a trap.[/PRIVATE]"
    )
    routed = route_response(text)
    assert routed.public == "Reply to player."
    assert routed.public_announcements == ["The door opens."]
    assert routed.whispers == [("Thorin", "You notice a trap.")]


def test_public_marker_with_mental_model():
    text = (
        "[MENTAL MODEL]DM notes here.[/MENTAL MODEL]\n"
        "Visible text.\n"
        "[PUBLIC]Something everyone sees.[/PUBLIC]"
    )
    routed = route_response(text)
    assert "DM notes" not in routed.public
    assert routed.public_announcements == ["Something everyone sees."]


def test_empty_public_marker():
    text = "Reply.\n[PUBLIC][/PUBLIC]"
    routed = route_response(text)
    assert routed.public == "Reply."
    assert routed.public_announcements == []


def test_existing_private_marker_still_works():
    text = "Narration.\n[PRIVATE:Gandalf]Secret info.[/PRIVATE]"
    routed = route_response(text)
    assert routed.public == "Narration."
    assert routed.whispers == [("Gandalf", "Secret info.")]
    assert routed.public_announcements == []
