"""Tests for prompt construction."""

from appworld_a2a_runner.prompt import build_prompt, serialize_supervisor


class TestSerializeSupervisor:
    """Tests for serialize_supervisor."""

    def test_none_returns_empty(self):
        assert serialize_supervisor(None) == ""

    def test_string_passthrough(self):
        assert serialize_supervisor("Alice") == "Alice"

    def test_dict_serializes_to_json(self):
        result = serialize_supervisor({"name": "Alice", "role": "manager"})
        assert '"name": "Alice"' in result
        assert '"role": "manager"' in result

    def test_dict_sorted_keys(self):
        result = serialize_supervisor({"z_key": "last", "a_key": "first"})
        assert result.index("a_key") < result.index("z_key")

    def test_other_type_uses_str(self):
        assert serialize_supervisor(42) == "42"


class TestBuildPrompt:
    """Tests for build_prompt."""

    def test_basic_prompt_structure(self):
        prompt = build_prompt(
            instruction="Do the task",
            supervisor="Boss",
            app_descriptions={"app1": "desc1"},
        )
        assert "I am your supervisor:" in prompt
        assert "Boss" in prompt
        assert "The task you are to complete is:" in prompt
        assert "Do the task" in prompt
        assert "The applications available to you" in prompt
        assert "app1" in prompt

    def test_none_supervisor(self):
        prompt = build_prompt(
            instruction="Do it",
            supervisor=None,
            app_descriptions={},
        )
        assert "I am your supervisor:\n\n" in prompt

    def test_dict_supervisor(self):
        prompt = build_prompt(
            instruction="Do it",
            supervisor={"name": "Alice"},
            app_descriptions={},
        )
        assert '"name": "Alice"' in prompt

    def test_multiple_app_descriptions(self):
        apps = {"email": "Send emails", "calendar": "Manage events"}
        prompt = build_prompt(
            instruction="Schedule meeting",
            supervisor=None,
            app_descriptions=apps,
        )
        assert "email" in prompt
        assert "calendar" in prompt
