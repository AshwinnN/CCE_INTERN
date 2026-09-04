"""Runtime SQL guard boundary."""


def enforce_select_only(sql: str) -> None:
    if not sql.strip().lower().startswith("select"):
        raise PermissionError("only SELECT statements are allowed")
