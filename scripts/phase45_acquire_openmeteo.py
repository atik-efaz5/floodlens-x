#!/usr/bin/env python3
"""Download the Phase 4.5 Open-Meteo 3-city discharge + precip snapshot."""

from floodlens.ml.acquire_openmeteo import acquire

if __name__ == "__main__":
    acquire()
