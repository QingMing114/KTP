"""Deprecated compatibility package for the former ``app`` entry point."""

from apps.api_gateway.main import create_app


def build_app():
    return create_app()


__deprecated__ = "Use apps.api_gateway.main:create_app for application assembly."
