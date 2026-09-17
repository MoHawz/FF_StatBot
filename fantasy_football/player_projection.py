"""
Real-life-matchup-adjusted player projections.

This is the piece that answers "predict based on the real NFL matchup, not
the fantasy matchup." For each rostered starter, ESPN's box score data
(`league.box_scores(week)`) already carries:
  - `projected_points`: ESPN's own projection for that player, that week
  - `pro_opponent`: the player's actual real-life NFL opponent that week
  - `pro_pos_rank`: where that real-life opponent ranks defending the
    player's position (1 = toughest matchup in the league / allows the
    fewest fantasy points to that position, higher = softer matchup)

So rather than treating "team A's projected score" as one blob, this nudges
each individual starter's own projection up or down based on how good or
bad their specific real-world matchup is, then sums the starters -- which
is a meaningfully more accurate "what should this team score this week"
number than either a flat team average or ESPN's own team-level projected
total (which doesn't expose the matchup reasoning to you).

NOTE on `pro_pos_rank` direction: ESPN doesn't document the exact scale
anywhere public, but the standard convention (1 = stingiest defense against
that position) is what every major fantasy site uses it to mean, and it's
what's assumed below. If a few weeks of live results show scores moving the
wrong direction relative to good/bad matchups, flip the sign on
MATCHUP_ADJ_STRENGTH and it corrects immediately -- everything else stays
the same.
"""
from dataclasses import dataclass
from typing import List, Optional

BENCH_SLOTS = {"BE", "IR"}

# Max swing a matchup can put on a player's own projection, as a fraction.
# 0.12 means the toughest possible matchup vs. the softest possible one is
# up to a 24% swing end to end (+/-12% each).
MATCHUP_ADJ_STRENGTH = 0.12

# Roughly how many "slots" pro_pos_rank spans (32 NFL teams). Used to find
# the midpoint (average matchup) to compare each player's matchup against.
NFL_TEAM_COUNT = 32


@dataclass
class PlayerProjection:
    name: str
    position: str
    slot_position: str
    pro_opponent: str
    pro_pos_rank: int
    base_projection: float
    adjusted_projection: float


def matchup_adjusted_points(base_projection: float, pro_pos_rank: Optional[int]) -> float:
    if not pro_pos_rank:
        return base_projection
    midpoint = (NFL_TEAM_COUNT + 1) / 2
    factor = (pro_pos_rank - midpoint) / midpoint  # ~ -1 (toughest) .. +1 (softest)
    return base_projection * (1 + MATCHUP_ADJ_STRENGTH * factor)


def project_starting_lineup(lineup: List) -> List[PlayerProjection]:
    """lineup: a BoxScore.home_lineup / away_lineup list of BoxPlayer."""
    out = []
    for p in lineup:
        if p.slot_position in BENCH_SLOTS:
            continue
        base = p.projected_points or 0.0
        adjusted = matchup_adjusted_points(base, getattr(p, "pro_pos_rank", None))
        out.append(
            PlayerProjection(
                name=p.name,
                position=p.position,
                slot_position=p.slot_position,
                pro_opponent=getattr(p, "pro_opponent", "None"),
                pro_pos_rank=getattr(p, "pro_pos_rank", 0),
                base_projection=round(base, 2),
                adjusted_projection=round(adjusted, 2),
            )
        )
    return out


def team_matchup_adjusted_total(lineup: List) -> float:
    return round(sum(pp.adjusted_projection for pp in project_starting_lineup(lineup)), 2)
