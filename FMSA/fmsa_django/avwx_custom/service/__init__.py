""".. include:: ../../docs/service.md"""

from avwx_custom.service.base import Service
from avwx_custom.service.files import NoaaGfs, NoaaNbm
from avwx_custom.service.scrape import (
    Amo,
    Aubom,
    Avt,
    FaaNotam,
    Mac,
    Nam,
    Noaa,
    Olbs,
    get_service,
)

__all__ = (
    "get_service",
    "Noaa",
    "Amo",
    "Aubom",
    "Avt",
    "Mac",
    "Nam",
    "Olbs",
    "FaaNotam",
    "NoaaGfs",
    "NoaaNbm",
    "Service",
)
