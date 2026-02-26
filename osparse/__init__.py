"""
osparse package - Parse NIH Other Support forms
"""

from .parse_cpos import extract_lines, parse_projects

__all__ = ["extract_lines", "parse_projects"]
