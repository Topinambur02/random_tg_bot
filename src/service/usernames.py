import re


_USERNAME = re.compile(r"[A-Za-z0-9_]{1,32}\Z")


def parse_username(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    username = value.removeprefix("@")
    if not _USERNAME.fullmatch(username) or (username.isdigit() and not value.startswith("@")):
        return None
    return username
