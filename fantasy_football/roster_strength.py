"""
Roster / positional strength, sourced entirely from ESPN's own data — no
FantasyPros scraping or third-party shared sheet needed.

Your old sheet ("Power Rankings 2022 ESPN.xlsx" -> Rosters/FP-ROS tabs) built
"roster score" by IMPORTRANGE-ing a volunteer-maintained public Google Sheet
that mirrored FantasyPros' free rest-of-season rankings, name-matching those
players against each roster, and summing the top-N per position. That's a
fragile dependency (it broke once FantasyPros stopped publishing/sharing it
that way, which is why you lost this).

ESPN's own private API -- the same one `espn_client.py` already
authenticates against with your cookies -- carries everything needed to
replace it natively:
  - `Player.projected_total_points` / `projected_avg_points`: ESPN's own
    season projections per player
  - `BoxPlayer.projected_points`: ESPN's own projection for one specific
    week (what `league.box_scores(week)` returns for that team's actual
    starting lineup that week)
  - `Player.posRank`: ESPN's positional ranking for that player

So "roster strength" here is: for a given week, take each team's *actual*
starting lineup (not bench/IR) from ESPN's box score, and sum the starters'
ESPN-projected points for that week. This is simpler than the old sheet,
needs no extra credentials, and never breaks because of a third party.
"""
from dataclasses import dataclass, field
from typing import Dict, List

BENCH_SLOTS = {"BE", "IR"}


@dataclass
class RosterStrengthRow:
    team_id: int
    team_name: str
    starters_projected: float          # ESPN's projected total for this week's starting lineup
    starters_actual: float             # actual total, if the week has been played
    by_position: dict = field(default_factory=dict)  # {position: summed projected points}
    rank: int = 0


def compute_roster_strength(league, week: int) -> List[RosterStrengthRow]:
    """
    week: the week whose starting lineups you want scored (usually the
    upcoming/current week, so this reflects byes/injuries/waiver moves as of
    right now).
    """
    rows: Dict[int, RosterStrengthRow] = {}

    for box in league.box_scores(week=week):
        for team, lineup in ((box.home_team, box.home_lineup), (box.away_team, box.away_lineup)):
            if team in (0, None):
                continue
            team_id = getattr(team, "team_id", None)
            team_name = getattr(team, "team_name", str(team))
            if team_id is None:
                continue

            projected_total = 0.0
            actual_total = 0.0
            by_position = {}
            for p in lineup:
                if p.slot_position in BENCH_SLOTS:
                    continue
                projected_total += p.projected_points or 0.0
                actual_total += p.points or 0.0
                by_position[p.position] = by_position.get(p.position, 0.0) + (p.projected_points or 0.0)

            rows[team_id] = RosterStrengthRow(
                team_id=team_id,
                team_name=team_name,
                starters_projected=round(projected_total, 2),
                starters_actual=round(actual_total, 2),
                by_position={k: round(v, 2) for k, v in by_position.items()},
            )

    ordered = sorted(rows.values(), key=lambda r: r.starters_projected, reverse=True)
    for i, r in enumerate(ordered, start=1):
        r.rank = i
    return ordered


def as_score_dict(rows: List[RosterStrengthRow]) -> Dict[int, float]:
    """Convenience: {team_id: starters_projected} for feeding into power_rankings."""
    return {r.team_id: r.starters_projected for r in rows}
