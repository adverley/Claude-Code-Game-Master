from discord_bot.message_buffer import MessageBuffer


class TestMessageBuffer:
    def test_add_and_get_all(self):
        buf = MessageBuffer(max_size=5)
        buf.add("Erik", "Thorin", "I don't trust this merchant")
        buf.add("Sara", "Elara", "agreed")

        messages = buf.get_all()
        assert len(messages) == 2
        assert messages[0]["discord_name"] == "Erik"
        assert messages[0]["character_name"] == "Thorin"
        assert messages[0]["content"] == "I don't trust this merchant"
        assert "is_command" not in messages[0]

    def test_rolling_window_evicts_oldest(self):
        buf = MessageBuffer(max_size=3)
        buf.add("A", "CharA", "msg1")
        buf.add("B", "CharB", "msg2")
        buf.add("C", "CharC", "msg3")
        buf.add("D", "CharD", "msg4")

        messages = buf.get_all()
        assert len(messages) == 3
        assert messages[0]["discord_name"] == "B"  # oldest surviving

    def test_get_delta_returns_new_messages(self):
        buf = MessageBuffer(max_size=50)
        buf.add("Erik", "Thorin", "hello")
        buf.add("Sara", "Elara", "hi")

        buf.mark_sent()  # mark current position

        buf.add("Erik", "Thorin", "I search the room")
        buf.add("Tom", "Gandalf", "me too")

        delta = buf.get_delta()
        assert len(delta) == 2
        assert delta[0]["content"] == "I search the room"

    def test_get_delta_empty_when_nothing_new(self):
        buf = MessageBuffer(max_size=50)
        buf.add("Erik", "Thorin", "hello")
        buf.mark_sent()

        delta = buf.get_delta()
        assert len(delta) == 0

    def test_format_delta_for_claude(self):
        buf = MessageBuffer(max_size=50)
        buf.add("Erik", "Thorin", "let's be careful")
        buf.add("Sara", "Elara", "I agree, stay alert")

        delta = buf.get_delta()
        formatted = buf.format_for_claude(delta, active_player="Erik", active_character="Thorin", command_text="I search the room")

        assert "Erik (playing Thorin)" in formatted
        assert "Sara (playing Elara)" in formatted
        assert "Active player: Erik (Thorin)" in formatted
        assert "Action: I search the room" in formatted

    def test_get_delta_after_eviction(self):
        """Regression: _sent_index must adjust when deque evicts old messages."""
        buf = MessageBuffer(max_size=3)
        buf.add("A", "CharA", "msg1")
        buf.add("B", "CharB", "msg2")
        buf.add("C", "CharC", "msg3")  # buffer now full

        buf.mark_sent()  # _sent_index = 3

        # New messages evict old ones
        buf.add("D", "CharD", "msg4")
        buf.add("E", "CharE", "msg5")

        delta = buf.get_delta()
        assert len(delta) == 2
        assert delta[0]["content"] == "msg4"
        assert delta[1]["content"] == "msg5"

    def test_get_delta_many_evictions_after_mark(self):
        """All messages evicted after mark_sent should appear in delta."""
        buf = MessageBuffer(max_size=3)
        buf.add("A", "CharA", "msg1")
        buf.mark_sent()

        # Add enough to fill and overflow
        for i in range(5):
            buf.add("X", "CharX", f"new{i}")

        delta = buf.get_delta()
        # Buffer holds last 3: new2, new3, new4 — all unsent
        assert len(delta) == 3
        assert delta[0]["content"] == "new2"

    def test_add_stores_timestamp(self):
        buf = MessageBuffer(max_size=5)
        buf.add("Erik", "Thorin", "test")
        msg = buf.get_all()[0]
        assert "timestamp" in msg
