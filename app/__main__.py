import uvicorn

from app.core.config import Settings
from app.main import create_app


def main() -> None:
    settings = Settings()
    uvicorn.run(
        create_app(settings), host=settings.app_host, port=settings.app_port, access_log=False
    )


if __name__ == "__main__":
    main()
