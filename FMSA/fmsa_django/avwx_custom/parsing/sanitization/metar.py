"""METAR sanitization support."""

# module
from avwx_custom.parsing.sanitization.base import sanitize_list_with, sanitize_string_with
from avwx_custom.parsing.sanitization.cleaners.base import CleanerListType
from avwx_custom.parsing.sanitization.cleaners.cleaners import OnlySlashes, TrimWxCode
from avwx_custom.parsing.sanitization.cleaners.joined import (
    JoinedCloud,
    JoinedRunwayVisibility,
    JoinedTimestamp,
    JoinedWind,
)
from avwx_custom.parsing.sanitization.cleaners.remove import RemoveFromMetar
from avwx_custom.parsing.sanitization.cleaners.replace import CURRENT, ReplaceItem
from avwx_custom.parsing.sanitization.cleaners.separated import (
    SeparatedAltimeterLetter,
    SeparatedCloudAltitude,
    SeparatedCloudQualifier,
    SeparatedDistance,
    SeparatedFirstTemperature,
    SeparatedSecondTemperature,
    SeparatedTemperatureTrailingDigit,
    SeparatedWindUnit,
)
from avwx_custom.parsing.sanitization.cleaners.visibility import RunwayVisibilityUnit, VisibilityGreaterThan
from avwx_custom.parsing.sanitization.cleaners.wind import (
    DoubleGust,
    EmptyWind,
    MisplaceWindKT,
    NonGGust,
    RemoveVrbLeadingDigits,
    WindLeadingMistype,
)

METAR_REPL = {
    **CURRENT,
    "Z/ ": "Z ",
}


clean_metar_string = sanitize_string_with(METAR_REPL)


CLEANERS: CleanerListType = [
    OnlySlashes,
    EmptyWind,
    TrimWxCode,
    SeparatedDistance,
    SeparatedFirstTemperature,
    SeparatedCloudAltitude,
    SeparatedSecondTemperature,
    SeparatedAltimeterLetter,
    SeparatedTemperatureTrailingDigit,
    SeparatedWindUnit,
    SeparatedCloudQualifier,
    RemoveFromMetar,
    ReplaceItem,
    VisibilityGreaterThan,
    MisplaceWindKT,
    RunwayVisibilityUnit,
    DoubleGust,
    WindLeadingMistype,
    NonGGust,
    RemoveVrbLeadingDigits,
    JoinedCloud,
    JoinedTimestamp,
    JoinedWind,
    JoinedRunwayVisibility,
    ### Other wind fixes
]

clean_metar_list = sanitize_list_with(CLEANERS)
