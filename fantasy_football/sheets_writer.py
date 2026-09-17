"""
Writes weekly power rankings (and other tabs) to a Google Sheet using a
service account. See SETUP.md for how to create the service account and
share the sheet with it.
"""
from datetime import datetime
from typing import List

import gspread
from google.oauth2.service_account import Credentials

from . import config
from .power_rankings import PowerRankingRow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

POWER_RANKINGS_HEADER = [
    "Rank", "Team", "Owner", "Power Score", "Move", "W", "L", "T",
    "Win %", "PPG", "Recency-Weighted PPG", "All-Play %", "SOS",
    "Consistency (StDev)", "Roster Strength (proj)",
]

HISTORY_HEADER = ["Week", "Team", "Owner", "Power Score", "Rank", "Updated"]


def client() -> gspread.Client:
    config.require("GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_SHEET_ID")
    creds = Credentials.from_service_account_file(config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES)
    return gspread.authorize(creds)


def get_or_create_worksheet(sh, title: str, rows=100, cols=20):
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=rows, cols=cols)


def _style_power_rankings_sheet(ws, n_rows: int):
    """Bold/colored header, frozen header row, sensible column widths and
    number formats, and green/red shading on the Move column so movers pop
    out without having to read the raw number -- meant to make this
    actually pleasant to open on a phone, not just technically correct."""
    n_cols = len(POWER_RANKINGS_HEADER)

    ws.format(f"A1:{gspread.utils.rowcol_to_a1(1, n_cols)}", {
        "backgroundColor": {"red": 0.12, "green": 0.23, "blue": 0.37},
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "horizontalAlignment": "CENTER",
    })
    ws.freeze(rows=1)

    # percent-format the two ratio columns (Win % is col I, All-Play % is col L)
    ws.format(f"I2:I{n_rows + 1}", {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}})
    ws.format(f"L2:L{n_rows + 1}", {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}})
    # bold the Power Score column so it's the one thing your eye jumps to
    ws.format(f"D2:D{n_rows + 1}", {"textFormat": {"bold": True}, "horizontalAlignment": "CENTER"})
    ws.format(f"E2:E{n_rows + 1}", {"horizontalAlignment": "CENTER"})

    # conditional formatting: green text for positive Move, red for negative
    body = {
        "requests": [
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": n_rows + 1,
                                     "startColumnIndex": 4, "endColumnIndex": 5}],
                        "booleanRule": {
                            "condition": {"type": "NUMBER_GREATER", "values": [{"userEnteredValue": "0"}]},
                            "format": {"textFormat": {"foregroundColor": {"red": 0.15, "green": 0.6, "blue": 0.25}, "bold": True}},
                        },
                    },
                    "index": 0,
                }
            },
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": n_rows + 1,
                                     "startColumnIndex": 4, "endColumnIndex": 5}],
                        "booleanRule": {
                            "condition": {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "0"}]},
                            "format": {"textFormat": {"foregroundColor": {"red": 0.75, "green": 0.15, "blue": 0.15}, "bold": True}},
                        },
                    },
                    "index": 1,
                }
            },
        ]
    }
    ws.spreadsheet.batch_update(body)

    try:
        ws.columns_auto_resize(0, n_cols)
    except Exception:
        pass  # not critical if the API version/permissions don't support this


def write_weekly_power_rankings(week: int, rows: List[PowerRankingRow], sheet_id: str = None):
    """Writes a dated tab (e.g. 'Wk 5 Power Rankings') plus updates a running
    'Power Rankings History' tab used for trend charts."""
    gc = client()
    sheet_id = sheet_id or config.GOOGLE_SHEET_ID
    sh = gc.open_by_key(sheet_id)

    # 1) Snapshot tab for this week
    ws = get_or_create_worksheet(sh, f"Wk {week} Power Rankings")
    ws.clear()
    ws.update(
        [POWER_RANKINGS_HEADER]
        + [
            [
                r.rank, r.team_name, r.owner, r.power_score, r.movement,
                r.wins, r.losses, r.ties, r.win_pct, r.ppg, r.recency_weighted_ppg,
                r.all_play_pct, r.sos, r.consistency_stdev, r.roster_strength,
            ]
            for r in rows
        ],
    )
    try:
        _style_power_rankings_sheet(ws, len(rows))
    except Exception as e:
        print(f"(sheet formatting skipped: {e})")

    # 2) Append to running history tab: one row per team per week, good for
    #    building a trend line chart across the season.
    hist = get_or_create_worksheet(sh, "Power Rankings History", rows=2000, cols=10)
    if hist.row_values(1) != HISTORY_HEADER:
        hist.insert_row(HISTORY_HEADER, 1)
        hist.format("A1:F1", {"textFormat": {"bold": True}})
        hist.freeze(rows=1)

    # Drop any rows already logged for this week so reruns overwrite instead
    # of piling up duplicates (rows for a week are always written as one
    # contiguous block, so a single min/max range covers them).
    week_str = str(week)
    existing_week_rows = [
        i for i, r in enumerate(hist.get_all_values()[1:], start=2)
        if r and r[0] == week_str
    ]
    if existing_week_rows:
        hist.delete_rows(min(existing_week_rows), max(existing_week_rows))

    now = datetime.now().isoformat(timespec="minutes")
    hist.append_rows(
        [[week, r.team_name, r.owner, r.power_score, r.rank, now] for r in rows],
        value_input_option="USER_ENTERED",
    )
    return ws.url
