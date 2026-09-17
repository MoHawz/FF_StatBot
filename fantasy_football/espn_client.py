"""
Thin wrapper around the `espn_api` library that gives us a clean, stable
data shape to build power rankings / stats / GroupMe messages from,
independent of espn_api's own internal object model (which can change).
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from espn_api.football import League

from . import config


@dataclass
class TeamWeek:
    team_id: int
    team_name: str
    owner: str
    week: int
    score: float
    opponent_id: Optional[int]
    opponent_name: Optional[str]
    opponent_score: Optional[float]
    is_win: Optional[bool]
    is_tie: bool = False


@dataclass
class TeamSeason:
    team_id: int
    team_name: str
    owner: str
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    standing: int
    acquisitions: int
    trades: int
    drops: int
    weeks: list = field(default_factory=list)  # list[TeamWeek], in week order


def connect(year: int = None) -> League:
    """Create an authenticated (or public) League connection."""
    year = year or config.SEASON_YEAR or datetime.now().year
    config.require("LEAGUE_ID")
    return League(
        league_id=config.LEAGUE_ID,
        year=year,
        espn_s2=config.ESPN_S2,
        swid=config.ESPN_SWID,
    )


def _owner_name(team) -> str:
    owners = getattr(team, "owners", None) or []
    if owners:
        o = owners[0]
        if isinstance(o, dict):
            first = o.get("firstName", "")
            last = o.get("lastName", "")
            name = f"{first} {last}".strip()
            if name:
                return name
        elif isinstance(o, str):
            return o
    return team.team_name


def get_all_team_seasons(league: League, through_week: int = None) -> list:
    """
    Returns a list[TeamSeason], one per franchise, each carrying a week-by-week
    breakdown (score, opponent, win/loss) up through `through_week`
    (defaults to the league's current week).
    """
    through_week = through_week or getattr(league, "current_week", None) or league.settings.reg_season_count

    teams_by_id = {t.team_id: t for t in league.teams}
    seasons = []

    for team in league.teams:
        weeks = []
        for wk_idx, (score, outcome, sched) in enumerate(
            zip(team.scores, team.outcomes, team.schedule), start=1
        ):
            if wk_idx > through_week:
                break
            # espn_api reports outcomes as short codes ('W'/'L'/'T'/'U'), not
            # the full words -- comparing against "WIN"/"TIE" never matched,
            # so is_win/is_tie were silently always False. Accept both forms
            # in case a future espn_api version spells them out.
            outcome_str = str(outcome).upper() if outcome is not None else ""
            if score in (None, 0) and outcome_str in ("", "U", "UNDECIDED"):
                # not played yet / bye week
                continue
            opp = sched
            opp_id = getattr(opp, "team_id", None)
            opp_score = None
            if opp_id is not None and opp_id in teams_by_id:
                opp_team = teams_by_id[opp_id]
                idx0 = wk_idx - 1
                if idx0 < len(opp_team.scores):
                    opp_score = opp_team.scores[idx0]
            is_tie = outcome_str in ("T", "TIE")
            is_win = None if is_tie else outcome_str in ("W", "WIN")
            weeks.append(
                TeamWeek(
                    team_id=team.team_id,
                    team_name=team.team_name,
                    owner=_owner_name(team),
                    week=wk_idx,
                    score=score,
                    opponent_id=opp_id,
                    opponent_name=getattr(opp, "team_name", None),
                    opponent_score=opp_score,
                    is_win=is_win,
                    is_tie=is_tie,
                )
            )

        seasons.append(
            TeamSeason(
                team_id=team.team_id,
                team_name=team.team_name,
                owner=_owner_name(team),
                wins=team.wins,
                losses=team.losses,
                ties=team.ties,
                points_for=team.points_for,
                points_against=team.points_against,
                standing=team.standing,
                acquisitions=team.acquisitions,
                trades=team.trades,
                drops=team.drops,
                weeks=weeks,
            )
        )
    return seasons


def get_current_week(league: League) -> int:
    return getattr(league, "current_week", 1)
