import pytest
from discord_bot.response_router import route_response, RoutedResponse


class TestRouteResponse:
    def test_no_markers_returns_full_text_as_public(self):
        result = route_response("You find a hidden door.")
        assert result.public == "You find a hidden door."
        assert result.whispers == []

    def test_single_marker_extracted_to_whisper(self):
        text = "The party enters the tavern.[PRIVATE:thorin]You recognise the barkeep as an old enemy.[/PRIVATE]"
        result = route_response(text)
        assert result.public == "The party enters the tavern."
        assert result.whispers == [("thorin", "You recognise the barkeep as an old enemy.")]

    def test_multiple_markers_to_different_characters(self):
        text = "[PRIVATE:thorin]The map is fake.[/PRIVATE]The group presses on.[PRIVATE:elara]You sense illusion magic.[/PRIVATE]"
        result = route_response(text)
        assert result.public == "The group presses on."
        assert ("thorin", "The map is fake.") in result.whispers
        assert ("elara", "You sense illusion magic.") in result.whispers

    def test_marker_only_response_has_empty_public(self):
        text = "[PRIVATE:thorin]Just for you.[/PRIVATE]"
        result = route_response(text)
        assert result.public == ""
        assert result.whispers == [("thorin", "Just for you.")]

    def test_character_name_is_preserved_as_written(self):
        text = "[PRIVATE:THORIN]A secret.[/PRIVATE]"
        result = route_response(text)
        assert result.whispers[0][0] == "THORIN"

    def test_multiline_content_in_marker(self):
        text = "[PRIVATE:thorin]Line one.\nLine two.\nLine three.[/PRIVATE]"
        result = route_response(text)
        assert result.whispers[0][1] == "Line one.\nLine two.\nLine three."

    def test_returns_routedresponse_instance(self):
        result = route_response("hello")
        assert isinstance(result, RoutedResponse)

    def test_content_with_leading_trailing_newlines_is_stripped(self):
        # Claude often writes [PRIVATE:name]\ncontent\n[/PRIVATE]
        text = "[PRIVATE:thorin]\nYou see a trapdoor.\n[/PRIVATE]"
        result = route_response(text)
        assert result.whispers[0][1] == "You see a trapdoor."
        assert result.public == ""

    def test_whitespace_only_public_collapses_to_empty(self):
        text = "  \n[PRIVATE:thorin]secret.[/PRIVATE]\n  "
        result = route_response(text)
        assert result.public == ""
        assert result.whispers == [("thorin", "secret.")]

    def test_two_blocks_same_character_produces_two_tuples(self):
        text = "[PRIVATE:thorin]First secret.[/PRIVATE][PRIVATE:thorin]Second secret.[/PRIVATE]"
        result = route_response(text)
        assert len(result.whispers) == 2
        assert result.whispers[0] == ("thorin", "First secret.")
        assert result.whispers[1] == ("thorin", "Second secret.")
