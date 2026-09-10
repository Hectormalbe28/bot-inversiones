from uuid import uuid4


def generate_request_id() -> str:
    return str(uuid4())


def generate_correlation_id() -> str:
    return str(uuid4())
