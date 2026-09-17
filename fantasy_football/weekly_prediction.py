"""
"Close Enough for Now" -- the Sunday-lock weekly matchup predictor.

Meant to run once rosters are as final as they're going to get (the user's
call: ~noon ET Sunday, right before the bulk of games kick off -- whatever
already played on Thursday/early Sunday London games is locked in regardless,
and that's fine by design). At that moment:

  1. Pull each matchup's actual starting lineups from `league.box_scores(week)`
  2. Score each starter with the real-NFL-matchup-adjusted projection from
     player_projection.py (not last week's fantasy opponent, not a flat
     season average -- their own projection nudged by their own real
     opponent's positional matchup rank)
  3. Sum to a team total for the week
  4. Run a quick Monte Carlo per game (team's historical week-to-week stdev
     as the spread around that matchup-adjusted mean) to get a win
     probability, not just a raw score projection

The name is deliberately honest: this is "as close as we can get, given
that rosters can still move a little right up to kickoff" -- not a claim of
certainty.
"""
import random
from dataclasses import dataclass
from statistics import pstdev
from typing import List, Optional

from . import player_projection
from .espn_client import TeamSeason

DEFAULT_STDEV = 20.0


@dataclass
class MatchupPrediction:
    week: int
    home_team: str
    away_team: str
    home_projected: float
    away_projected: float
    home_win_pct: float
    away_win_pct: float
    confidence: str  # "Lock", "Favored", "Toss-Up"
    home_starters: list
    away_starters: list


def _confidence_label(favorite_win_pct: float) -> str:
    if favorite_win_pct >= 80:
        return "Lock"
    if favorite_win_pct >= 62:
        return "Favored"
    return "Toss-Up"


def _team_stdev(team_seasons: List[TeamSeason]) -> dict:
    out = {}
    for ts in team_seasons:
        scores = [w.score for w in ts.weeks]
        out[ts.team_id] = pstdev(scores) if len(scores) > 1 else DEFAULT_STDEV
    return out


def predict_week(
    league,
    week: int,
    team_seasons: List[TeamSeason],
    n_trials: int = 20000,
) -> List[MatchupPrediction]:
    stdev_by_id = _team_stdev(team_seasons)
    predictions = []

    for box in league.box_scores(week=week):
        if box.home_team in (0, None) or box.away_team in (0, None):
            continue  # bye week

        home_starters = player_projection.project_starting_lineup(box.home_lineup)
        away_starters = player_projection.project_starting_lineup(box.away_lineup)
        home_mean = round(sum(p.adjusted_projection for p in home_starters), 2)
        away_mean = round(sum(p.adjusted_projection for p in away_starters), 2)

        home_sd = stdev_by_id.get(box.home_team.team_id) or DEFAULT_STDEV
        away_sd = stdev_by_id.get(box.away_team.team_id) or DEFAULT_STDEV

        home_wins = 0
        for _ in range(n_trials):
            if random.gauss(home_mean, home_sd) > random.gauss(away_mean, away_sd):
                home_wins += 1
        home_win_pct = round(100 * home_wins / n_trials, 1)
        away_win_pct = round(100 - home_win_pct, 1)

        predictions.append(
            MatchupPrediction(
                week=week,
                home_team=box.home_team.team_name,
                away_team=box.away_team.team_name,
                home_projected=home_mean,
                away_projected=away_mean,
                home_win_pct=home_win_pct,
                away_win_pct=away_win_pct,
                confidence=_confidence_label(max(home_win_pct, away_win_pct)),
                home_starters=home_starters,
                away_starters=away_starters,
            )
        )
    return predictions
