"""
Weekly power rankings.

A clean rewrite of the old spreadsheet's weighted-formula approach (both the
2022 workbook and the later "Credit: /u/GATOR7862" template you sent over).
Same idea -- blend several signals into one score -- but reworked so every
component is well-understood, sourced only from ESPN's own API (no
FantasyPros scraping / third-party shared sheets to break), and sane in the
first couple weeks of a season when sample sizes are tiny.

Components (weights are constants below, easy to retune):

  1. Win %              (25%) - season win percentage
  2. Points per game     (20%) - recency-weighted (see RECENCY_HALF_LIFE
                                   below): recent weeks count more than early
                                   ones, so a hot/cold streak actually moves
                                   the score, without a hard cliff at "last
                                   3 weeks."
  3. All-play %          (15%) - if you played every other team's score every
                                   week, what % of those games would you have
                                   won? Strips out schedule luck.
  4. Strength of schedule(10%) - average quality (recency-weighted PPG) of
                                   the opponents you've actually played so
                                   far. Rewards teams doing well against a
                                   tough slate; the all-play% component
                                   above already looks at *your* scores
                                   in isolation, this looks at *who you beat*.
  5. Consistency         (10%) - negative standard deviation of weekly
                                   score, shrunk toward the league-average
                                   stdev early in the season (see
                                   SHRINKAGE_GAMES) so 1-2 flukey games don't
                                   brand a team "inconsistent" for the year.
  6. Roster strength     (20%) - ESPN's own projected points for this
                                   week's actual starting lineup (see
                                   roster_strength.py). Optional: pass
                                   `roster_strength_scores` in; if you don't
                                   have it (e.g. offline testing), weights
                                   are redistributed proportionally across
                                   the other five so the formula still works.
"""
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Dict, List, Optional

from .espn_client import TeamSeason

WEIGHTS = {
    "win_pct": 0.25,
    "ppg": 0.20,
    "all_play_pct": 0.15,
    "sos": 0.10,
    "consistency": 0.10,
    "roster_strength": 0.20,
}

# Recency weighting: weight of a week `n` weeks ago = 0.5 ** (n / HALF_LIFE).
# HALF_LIFE=4 means a week 4 games ago counts half as much as this week.
RECENCY_HALF_LIFE = 4.0

# Below this many games played, a team's own stdev is blended with the
# league-wide stdev so early-season noise doesn't dominate. Fully the
# league average at 0 games, fully the team's own by SHRINKAGE_GAMES.
SHRINKAGE_GAMES = 6


@dataclass
class PowerRankingRow:
    rank: int
    team_id: int
    team_name: str
    owner: str
    power_score: float
    win_pct: float
    ppg: float
    recency_weighted_ppg: float
    all_play_pct: float
    sos: float
    consistency_stdev: float
    roster_strength: Optional[float]
    wins: int
    losses: int
    ties: int
    movement: int = 0  # vs. last week's rank, filled in by caller if available


def _zscores(values: List[float]) -> List[float]:
    m = mean(values)
    sd = pstdev(values) or 1.0  # avoid div by zero when everyone is tied
    return [(v - m) / sd for v in values]


def _recency_weighted_avg(scores: List[float]) -> float:
    if not scores:
        return 0.0
    n = len(scores)
    weights = [0.5 ** ((n - 1 - i) / RECENCY_HALF_LIFE) for i in range(n)]
    return sum(s * w for s, w in zip(scores, weights)) / sum(weights)


def _all_play_pct(team_season: TeamSeason, all_seasons: List[TeamSeason]) -> float:
    """% of hypothetical matchups won if this team played every other
    team's score in every week that's been played so far."""
    wins = 0
    total = 0
    for tw in team_season.weeks:
        others_scores = [
            w.score
            for other in all_seasons
            if other.team_id != team_season.team_id
            for w in other.weeks
            if w.week == tw.week
        ]
        for other_score in others_scores:
            total += 1
            if tw.score > other_score:
                wins += 1
            elif tw.score == other_score:
                wins += 0.5
    return (wins / total) if total else 0.0


def _strength_of_schedule(team_season: TeamSeason, ppg_by_team: Dict[int, float]) -> float:
    """Average recency-weighted PPG of the opponents actually played so far."""
    opp_qualities = [
        ppg_by_team[w.opponent_id]
        for w in team_season.weeks
        if w.opponent_id is not None and w.opponent_id in ppg_by_team
    ]
    return mean(opp_qualities) if opp_qualities else 0.0


def compute_power_rankings(
    team_seasons: List[TeamSeason],
    previous_ranks: dict = None,
    roster_strength_scores: Optional[Dict[int, float]] = None,
) -> List[PowerRankingRow]:
    """
    team_seasons: output of espn_client.get_all_team_seasons()
    previous_ranks: optional {team_id: rank_last_week} to compute movement arrows
    roster_strength_scores: optional {team_id: score} from
        roster_strength.as_score_dict(). If omitted, that component is
        dropped and its weight redistributed across the rest.
    """
    previous_ranks = previous_ranks or {}
    have_roster_strength = roster_strength_scores is not None and len(roster_strength_scores) > 0

    win_pcts, flat_ppgs, weighted_ppgs, all_plays, consistencies = [], [], [], [], []
    league_stdevs = []

    for ts in team_seasons:
        games = ts.wins + ts.losses + ts.ties
        win_pct = (ts.wins + 0.5 * ts.ties) / games if games else 0.0

        scores = [w.score for w in ts.weeks]
        flat_ppg = mean(scores) if scores else 0.0
        weighted_ppg = _recency_weighted_avg(scores)

        own_stdev = pstdev(scores) if len(scores) > 1 else None
        if own_stdev is not None:
            league_stdevs.append(own_stdev)

        win_pcts.append(win_pct)
        flat_ppgs.append(flat_ppg)
        weighted_ppgs.append(weighted_ppg)
        all_plays.append(_all_play_pct(ts, team_seasons))
        consistencies.append(own_stdev)

    league_avg_stdev = mean(league_stdevs) if league_stdevs else 20.0

    # shrink each team's stdev toward the league average based on games played
    shrunk_consistency = []
    for ts, own_stdev in zip(team_seasons, consistencies):
        games = len(ts.weeks)
        if own_stdev is None:
            shrunk_consistency.append(-league_avg_stdev)
            continue
        weight = min(games / SHRINKAGE_GAMES, 1.0)
        blended = weight * own_stdev + (1 - weight) * league_avg_stdev
        shrunk_consistency.append(-blended)  # negative: lower stdev = better

    ppg_by_team = {ts.team_id: w for ts, w in zip(team_seasons, weighted_ppgs)}
    sos_values = [_strength_of_schedule(ts, ppg_by_team) for ts in team_seasons]

    z_win = _zscores(win_pcts)
    z_ppg = _zscores(weighted_ppgs)
    z_allplay = _zscores(all_plays)
    z_sos = _zscores(sos_values)
    z_consistency = _zscores(shrunk_consistency)

    weights = dict(WEIGHTS)
    if not have_roster_strength:
        dropped = weights.pop("roster_strength")
        remaining = sum(weights.values())
        weights = {k: v + (v / remaining) * dropped for k, v in weights.items()}
        z_roster = [0.0] * len(team_seasons)
    else:
        roster_vals = [roster_strength_scores.get(ts.team_id, 0.0) for ts in team_seasons]
        z_roster = _zscores(roster_vals)

    rows = []
    for i, ts in enumerate(team_seasons):
        composite = (
            weights["win_pct"] * z_win[i]
            + weights["ppg"] * z_ppg[i]
            + weights["all_play_pct"] * z_allplay[i]
            + weights["sos"] * z_sos[i]
            + weights["consistency"] * z_consistency[i]
            + weights.get("roster_strength", 0.0) * z_roster[i]
        )
        rows.append(
            {
                "composite": composite,
                "team_id": ts.team_id,
                "team_name": ts.team_name,
                "owner": ts.owner,
                "win_pct": win_pcts[i],
                "ppg": flat_ppgs[i],
                "weighted_ppg": weighted_ppgs[i],
                "all_play_pct": all_plays[i],
                "sos": sos_values[i],
                "consistency_stdev": -shrunk_consistency[i],
                "roster_strength": roster_strength_scores.get(ts.team_id) if have_roster_strength else None,
                "wins": ts.wins,
                "losses": ts.losses,
                "ties": ts.ties,
            }
        )

    composites = [r["composite"] for r in rows]
    lo, hi = min(composites), max(composites)
    spread = (hi - lo) or 1.0

    rows.sort(key=lambda r: r["composite"], reverse=True)

    result = []
    for rank, r in enumerate(rows, start=1):
        power_score = round(40 + 60 * (r["composite"] - lo) / spread, 1)
        prev_rank = previous_ranks.get(r["team_id"])
        movement = (prev_rank - rank) if prev_rank else 0
        result.append(
            PowerRankingRow(
                rank=rank,
                team_id=r["team_id"],
                team_name=r["team_name"],
                owner=r["owner"],
                power_score=power_score,
                win_pct=round(r["win_pct"], 3),
                ppg=round(r["ppg"], 2),
                recency_weighted_ppg=round(r["weighted_ppg"], 2),
                all_play_pct=round(r["all_play_pct"], 3),
                sos=round(r["sos"], 2),
                consistency_stdev=round(r["consistency_stdev"], 2),
                roster_strength=r["roster_strength"],
                wins=r["wins"],
                losses=r["losses"],
                ties=r["ties"],
                movement=movement,
            )
        )
    return result
