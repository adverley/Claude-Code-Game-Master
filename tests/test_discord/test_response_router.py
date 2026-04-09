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

    def test_closing_tag_with_name_is_matched(self):
        # Claude sometimes repeats the name in the closing tag
        text = "Public.[PRIVATE:Aldric Ironfeld]Secret.[/PRIVATE:Aldric Ironfeld]"
        result = route_response(text)
        assert result.public == "Public."
        assert result.whispers == [("Aldric Ironfeld", "Secret.")]

    def test_complex_composed_block(self):
        text = "The party enters the tavern.[PRIVATE:thorin]You recognise the barkeep as an old enemy.[/PRIVATE] The barkeep seems a friendly guy."
        result = route_response(text)
        assert result.public == "The party enters the tavern. The barkeep seems a friendly guy."
        assert result.whispers == [("thorin", "You recognise the barkeep as an old enemy.")]


    def test_two_blocks_same_character_produces_two_tuples(self):
        text = "[PRIVATE:thorin]First secret.[/PRIVATE][PRIVATE:thorin]Second secret.[/PRIVATE]"
        result = route_response(text)
        assert len(result.whispers) == 2
        assert result.whispers[0] == ("thorin", "First secret.")
        assert result.whispers[1] == ("thorin", "Second secret.")




class TestMentalModelStripping:
    def test_mental_model_block_is_stripped_from_public(self):
        text = "[MENTAL MODEL]\nWHERE: Tavern\nWHEN: Evening\n[/MENTAL MODEL]\nThe party enters."
        result = route_response(text)
        assert result.public == "The party enters."
        assert result.whispers == []

    def test_mental_model_only_response_has_empty_public(self):
        text = "[MENTAL MODEL]WHERE: Keep\nWHEN: Dawn[/MENTAL MODEL]"
        result = route_response(text)
        assert result.public == ""

    def test_mental_model_stripped_private_still_routed(self):
        text = (
            "[MENTAL MODEL]\nWHERE: Dungeon\n[/MENTAL MODEL]\n"
            "Torches flicker.[PRIVATE:elara]You hear a whisper.[/PRIVATE]"
        )
        result = route_response(text)
        assert result.public == "Torches flicker."
        assert result.whispers == [("elara", "You hear a whisper.")]
