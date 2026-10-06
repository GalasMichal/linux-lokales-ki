ALLOWED = {"host", "port", "debug"}


def validate(data: dict) -> dict:
    # BUG: does not reject unknown keys
    return data
