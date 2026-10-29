from src.app.storage import SQLiteStore


def test_restart_restores_latest_turns_in_chronological_order(tmp_path):
    database = str(tmp_path / "conversations.db")
    original = SQLiteStore(database)
    original.save_conversation("conversation", "operator")
    for index in range(6):
        original.save_conversation_turn("conversation", "user", f"turn-{index}", {"sequence": index})

    restarted = SQLiteStore(database)
    recent = restarted.list_conversation_turns("conversation", limit=3)
    assert [turn["content"] for turn in recent] == ["turn-3", "turn-4", "turn-5"]
    assert [turn["metadata"]["sequence"] for turn in recent] == [3, 4, 5]
    assert restarted.list_conversation_turns("other", limit=3) == []
