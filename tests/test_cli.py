from pathlib import Path

from find_oss.cli import main


def test_save_list_update_and_delete_commands(tmp_path: Path, capsys) -> None:
    store_path = tmp_path / "saved.yaml"

    assert main(["--store", str(store_path), "save", "Weekend", "Find issues"]) == 0
    assert main(["--store", str(store_path), "saved", "list"]) == 0
    assert "Weekend" in capsys.readouterr().out

    assert (
        main(
            [
                "--store",
                str(store_path),
                "saved",
                "update",
                "weekend",
                "Find Python issues",
            ]
        )
        == 0
    )
    assert main(["--store", str(store_path), "saved", "delete", "weekend"]) == 0


def test_saved_run_uses_stored_query(tmp_path: Path, monkeypatch) -> None:
    store_path = tmp_path / "saved.yaml"
    main(["--store", str(store_path), "save", "Weekend", "Find issues"])
    received: list[str] = []

    monkeypatch.setattr(
        "find_oss.cli.execute_search",
        lambda query, output_dir: received.append(query),
    )

    assert (
        main(["--store", str(store_path), "saved", "run", "weekend"]) == 0
    )
    assert received == ["Find issues"]
