"""
Tracks Skip's Sunday matchup picks against actual results, so the weekly
predictions image can show a running "how right has Skip been" W-L record.

Each Sunday run does two things against the "Skip's Predictions" sheet tab:
  1. Grades any previously-logged picks for weeks that have since finished
     (fills in the actual winner and whether the pick was correct), using
     each team's real result for that week.
  2. Logs this week's fresh picks, ungraded -- there's nothing to compare
     them against yet, so they'll be graded next time this runs.

The "pick" for a matchup is whichever team weekly_prediction.py gave the
higher win probability to -- Toss-Ups included, since a 51% lean is still
a pick, and grading it is what makes the win probability meaningful.
"""
from typing import List, Tuple

import gspread

from .espn_client import get_all_team_seasons
from .sheets_writer import get_or_create_worksheet
from .weekly_prediction import MatchupPrediction

SHEET_TAB = "Skip's Predictions"
HEADER = ["Week", "Home Team", "Away Team", "Picked Team", "Pick %", "Confidence", "Actual Winner", "Correct"]


def _ensure_header(ws):
    if ws.row_values(1) != HEADER:
        ws.insert_row(HEADER, 1)
        ws.format(f"A1:{gspread.utils.rowcol_to_a1(1, len(HEADER))}", {"textFormat": {"bold": True}})
        ws.freeze(rows=1)


def _pick(p: MatchupPrediction) -> Tuple[str, float]:
    if p.home_win_pct >= p.away_win_pct:
        return p.home_team, p.home_win_pct
    return p.away_team, p.away_win_pct


def record_predictions(sh, predictions: List[MatchupPrediction]) -> None:
    """Logs this week's picks, ungraded, for grading on a future run. If
    this week was already logged (e.g. a rerun), its old rows are dropped
    first so reruns overwrite instead of duplicating -- same as
    sheets_writer's Power Rankings History tab."""
    ws = get_or_create_worksheet(sh, SHEET_TAB, rows=1000, cols=len(HEADER))
    _ensure_header(ws)
    if not predictions:
        return

    week_str = str(predictions[0].week)
    existing = [
        i for i, r in enumerate(ws.get_all_values()[1:], start=2)
        if r and r[0] == week_str
    ]
    if existing:
        ws.delete_rows(min(existing), max(existing))

    rows = []
    for p in predictions:
        picked_team, pick_pct = _pick(p)
        rows.append([p.week, p.home_team, p.away_team, picked_team, pick_pct, p.confidence, "", ""])
    ws.append_rows(rows, value_input_option="USER_ENTERED")


def grade_pending(sh, league, through_week: int) -> Tuple[int, int]:
    """Fills in actual results for any ungraded rows whose week is <=
    through_week (the last fully-completed week), then returns the
    cumulative (wins, losses) across every graded row."""
    ws = get_or_create_worksheet(sh, SHEET_TAB, rows=1000, cols=len(HEADER))
    _ensure_header(ws)

    values = ws.get_all_values()
    pending = [
        (i, r) for i, r in enumerate(values[1:], start=2)
        if r and r[0].strip().isdigit() and int(r[0]) <= through_week and not r[6]
    ]

    if pending:
        weeks_needed = {int(r[0]) for _, r in pending}
        team_seasons = get_all_team_seasons(league, through_week=max(weeks_needed))
        result_by_team_week = {
            (tw.week, ts.team_name): tw for ts in team_seasons for tw in ts.weeks
        }

        updates = []
        for row_num, r in pending:
            week, picked_team = int(r[0]), r[3]
            tw = result_by_team_week.get((week, picked_team))
            if tw is None or tw.is_tie:
                continue  # bye, tie, or missing data -- leave ungraded
            actual_winner = picked_team if tw.is_win else tw.opponent_name
            correct = "Yes" if tw.is_win else "No"
            updates.append({
                "range": f"G{row_num}:H{row_num}",
                "values": [[actual_winner, correct]],
            })

        if updates:
            ws.batch_update(updates, value_input_option=gspread.utils.ValueInputOption.user_entered)
            values = ws.get_all_values()

    wins = sum(1 for r in values[1:] if len(r) > 7 and r[7] == "Yes")
    losses = sum(1 for r in values[1:] if len(r) > 7 and r[7] == "No")
    return wins, losses
