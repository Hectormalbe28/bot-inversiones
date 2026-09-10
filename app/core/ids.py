from uuid import uuid4


def generate_request_id() -> str:
    """Generate a UUID4 string for request identification."""
    return str(uuid4())


def generate_correlation_id() -> str:
    """Generate a UUID4 string for correlation across operations."""
    return str(uuid4())