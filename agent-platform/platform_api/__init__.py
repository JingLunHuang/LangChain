"""接入層：API Key 鑑權與路由。"""

__all__ = ["app"]


def __getattr__(name: str):
    if name == "app":
        from .api import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
