from find_oss.github_tools import READ_ONLY_TOOL_NAMES, build_github_tools


def test_custom_tool_registry_is_read_only() -> None:
    forbidden = ("create", "update", "delete", "write", "merge", "comment", "fork")
    assert READ_ONLY_TOOL_NAMES
    assert not any(word in name for name in READ_ONLY_TOOL_NAMES for word in forbidden)


def test_tool_registry_exposes_bounded_search_and_inspection() -> None:
    tools = build_github_tools("token")
    names = {tool.name for tool in tools}

    assert names == set(READ_ONLY_TOOL_NAMES)
    assert "search_github_repositories" in names
    assert "search_open_github_issues" in names
    assert "inspect_github_rate_limit" in names
