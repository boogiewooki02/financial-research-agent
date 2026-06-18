from __future__ import annotations

from config.settings import PROJECT_ROOT, SETTINGS, Settings


SELECTORS = {
    "report_rows": "table.board_list_table04 tbody tr",
    "cells": "td",
    "pdf_link": "a[href*='/download/'][href$='.pdf'], a.pdf-download[data-url]",
    "report_id_source": "img[onclick*='add_hit']",
}


__all__ = ["PROJECT_ROOT", "SETTINGS", "SELECTORS", "Settings"]
