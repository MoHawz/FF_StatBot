"""
Generates a short, factual "why" line for each team's power-rankings
movement -- e.g. "Lost Justin Jefferson (IR)", "Lost 3 straight", "Only 78.4
pts, usually 105.2" -- meant to sit under the team/record line on the
rendered power-rankings image so a mover isn't just a bare arrow.

This is deliberately conservative: a reason is only generated when it
plausibly explains the *direction* the team actually moved (a team that
climbed only gets positive reasons, a team that fell only gets negative
ones), and only when a signal clears a real threshold -- so most weeks,
most teams show no reason at all rather than a forced, meaningless one.
Silence is a valid answer here.

Signals, in priority order (first match wins, one reason per team):
  Falling:
    1. a rostered player with real fantasy value is OUT / on IR
    2. currently on a losing streak of 2+
    3. this week's score well below their own recent average
  Rising:
    1. currently on a winning streak of 2+
    2. this week's score well above their own recent average

Injury status is read from the team's *current* roster (as of when this
runs), not a historical snapshot from the week being reported on -- close
enough for a "heads up, this is probably why" caption, not meant to be a
perfectly retroactive audit trail.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

from .espn_client import TeamSeason
from .power_rankings import PowerRankingRow

# injuryStatus values worth calling out -- deliberately excludes
# QUESTIONABLE/DOUBTFUL/DAY_TO_DAY, which are too common week-to-week to be
# a meaningful "reason" on their own.
NOTABLE_INJURY_STATUSES = {"INJURY_RESERVE", "OUT", "SUSPENSION"}
# Minimum projected-points-per-game for a hurt player to be worth naming
# (skip bench-depth injuries that wouldn't move the needle).
NOTABLE_PLAYER_PPG_THRESHOLD = 8.0

LOSING_STREAK_THRESHOLD = 2
WINNING_STREAK_THRESHOLD = 2
LOW_WEEK_RATIO = 0.80   # this week's score below 80% of recent average
HIGH_WEEK_RATIO = 1.20  # this week's score above 120% of recent average


def _current_streaks_by_id(team_seasons: List[TeamSeason]) -> Dict[int, int]:
    """Same logic as season_stats.current_streaks, but keyed by team_id
    (season_stats keys by name, which is a weaker join key)."""
    out = {}
    for ts in team_seasons:
        streak = 0
        for w in ts.weeks:
            if w.is_tie:
                streak = 0
            elif w.is_win:
                streak = streak + 1 if streak >= 0 else 1
            else:
                streak = streak - 1 if streak <= 0 else -1
        out[ts.team_id] = streak
    return out


def _hurt_starter(team) -> Optional[str]:
    """Returns 'Player Name (IR)' / 'Player Name (OUT)' for the most
    valuable rostered player currently flagged OUT/IR/suspended, or None."""
    candidates = []
    for p in getattr(team, "roster", []):
        status = getattr(p, "injuryStatus", None)
        if status not in NOTABLE_INJURY_STATUSES:
            continue
        ppg = getattr(p, "projected_avg_points", None) or 0.0
        if ppg < NOTABLE_PLAYER_PPG_THRESHOLD:
            continue
        candidates.append((ppg, p.name, status))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, name, status = candidates[0]
    tag = "IR" if status == "INJURY_RESERVE" else status.replace("_", " ").title()
    return f"Lost {name} ({tag})"


def compute_movement_reasons(
    rows: List[PowerRankingRow],
    team_seasons: List[TeamSeason],
    league,
    through_week: int,
) -> Dict[int, str]:
    """Returns {team_id: reason_text} -- only for teams where a real signal
    was found; teams with no strong reason simply aren't in the dict."""
    streaks = _current_streaks_by_id(team_seasons)
    seasons_by_id = {ts.team_id: ts for ts in team_seasons}
    teams_by_id = {t.team_id: t for t in league.teams}

    reasons: Dict[int, str] = {}

    for row in rows:
        if row.movement == 0:
            continue

        ts = seasons_by_id.get(row.team_id)
        this_week = next((w for w in ts.weeks if w.week == through_week), None) if ts else None
        streak = streaks.get(row.team_id, 0)
        team = teams_by_id.get(row.team_id)

        if row.movement < 0:  # fell in the rankings -- look for a negative signal
            hurt = _hurt_starter(team) if team else None
            if hurt:
                reasons[row.team_id] = hurt
            elif streak <= -LOSING_STREAK_THRESHOLD:
                reasons[row.team_id] = f"Lost {abs(streak)} straight"
            elif this_week and row.recency_weighted_ppg > 0 and this_week.score < row.recency_weighted_ppg * LOW_WEEK_RATIO:
                reasons[row.team_id] = f"Only {this_week.score:.1f} pts, usually {row.recency_weighted_ppg:.1f}"

        else:  # climbed in the rankings -- look for a positive signal
            if streak >= WINNING_STREAK_THRESHOLD:
                reasons[row.team_id] = f"Won {streak} straight"
            elif this_week and row.recency_weighted_ppg > 0 and this_week.score > row.recency_weighted_ppg * HIGH_WEEK_RATIO:
                reasons[row.team_id] = f"{this_week.score:.1f} pts, usually {row.recency_weighted_ppg:.1f}"

    return reasons
