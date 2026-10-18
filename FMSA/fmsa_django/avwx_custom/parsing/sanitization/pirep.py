"""PIREP sanitization support."""

from avwx_custom.parsing.sanitization.base import sanitize_string_with
from avwx_custom.parsing.sanitization.cleaners.replace import CURRENT

clean_pirep_string = sanitize_string_with(CURRENT)
