"""Compatibility imports and configuration transport dependencies."""

from fastapi import Request

from presales.http import execute


def quantity_engine(request: Request):
    return request.app.state.quantity_engine


__all__ = ["execute", "quantity_engine"]
