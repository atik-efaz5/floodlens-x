"""Structured API errors. Never attach filesystem paths, secrets, or tracebacks."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException


def api_error(status_code: int, error_code: str, message: Optional[str] = None, **extra) -> None:
    detail = {"error_code": error_code, "message": message or error_code}
    detail.update({key: value for key, value in extra.items() if value is not None})
    raise HTTPException(status_code=status_code, detail=detail)
