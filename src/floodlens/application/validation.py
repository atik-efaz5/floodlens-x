"""Shared validation for ingest pipelines."""

from __future__ import annotations


def validate_coordinates(latitude: float, longitude: float) -> None:
    if latitude < -90 or latitude > 90:
        raise ValueError(f"latitude out of range: {latitude}")
    if longitude < -180 or longitude > 180:
        raise ValueError(f"longitude out of range: {longitude}")


def validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} cannot be negative: {value}")
