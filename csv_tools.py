"""Helpers for building safe CSV downloads."""

import csv
import io
import re

# Phone numbers and plain digits are safe, even when they start with "+".
_PLAIN_NUMBER = re.compile(r"\+?[0-9 ]+")

# Spreadsheet programs treat cells starting with these characters as formulas.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    """Return a CSV-safe cell value.

    Text that starts with a formula character gets a leading apostrophe, so
    Excel and Google Sheets show it as plain text instead of running it.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    if _PLAIN_NUMBER.fullmatch(value):
        return value
    if value.startswith(_FORMULA_STARTS):
        return "'" + value
    return value


def build_csv(headers, rows):
    """Build CSV text from a header list and a list of rows.

    A UTF-8 byte order mark is added at the start so Excel shows Amharic
    and other non-English text correctly.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return "\ufeff" + buffer.getvalue()