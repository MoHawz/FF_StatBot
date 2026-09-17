"""
Monte Carlo playoff / championship odds calculator.

This is a Python port of the logic in "Playoff Calculator wk 3 2021.xlsm":
for each team, take the mean and population standard deviation of its
weekly scores so far, then simulate the rest of the season (and the
playoff bracket) thousands of times by drawing a random score for each
team each week from Normal(mean, stdev) -- exactly what the old sheet did
with `=NORMINV(RAND(), mean, stdev)`. Whoever's simulated score is higher
wins that matchup. Repeating this thousands of times and tallying how
often each team makes the playoffs / wins the bowl / wins the championship
gives clean, explainable odds.

Usage is intentionally decoupled from ESPN's live schedule object so it can
also be driven by historical/sample data (useful for testing without
credentials).
"""
import random
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Dict, List, Optional, Tuple


#: How much an opponent's defensive strength can move a team's simulated
#: mean, as a fraction. 0.15 means facing the league's stingiest defense vs.
#: its most generous one can swing your expected score by up to +/-15%.
#: Independent draws (no opponent adjustment at all) is OPPONENT_ADJ_STRENGTH=0.
OPPONENT_ADJ_STRENGTH = 0.15


@dataclass
class SimTeam:
    team_id: int
    name: str
    scores_so_far: List[float]          # actual weekly scores played so far
    wins: int
    losses: int
    ties: int = 0
    points_allowed_so_far: List[float] = field(default_factory=list)  # opponents' scores against this team

    @property
    def avg(self) -> float:
        return mean(self.scores_so_far) if self.scores_so_far else 100.0

    @property
    def stdev(self) -> float:
        return pstdev(self.scores_so_far) if len(self.scores_so_far) > 1 else 15.0

    @property
    def avg_allowed(self) -> float:
        """Average points this team's opponents have scored against them --
        a simple, explainable stand-in for "defense," used to nudge the
        other side's simulated score up or down depending who they're
        facing. Falls back to this team's own scoring average when we don't
        have opponent-score history (keeps the adjustment a no-op rather
        than skewing things on missing data)."""
        return mean(self.points_allowed_so_far) if self.points_allowed_so_far else self.avg


@dataclass
class SimResult:
    team_id: int
    name: str
    made_playoffs_pct: float
    won_bowl_pct: float          # reached/won the top bracket final (i.e. league champion game)
    champion_pct: float
    avg_final_seed: float


def _draw_score(
    team: SimTeam,
    mean_override: float = None,
    opponent: SimTeam = None,
    league_avg_allowed: float = None,
) -> float:
    mean_val = mean_override if mean_override is not None else team.avg
    if opponent is not None and league_avg_allowed:
        # Positive opp_factor = this opponent allows more than a league-average
        # defense (a soft matchup, so bump the mean up); negative = a tough
        # matchup, so pull it down. This is what "opponent-adjusted scoring"
        # buys you over pure independent draws: two teams with identical
        # season averages get different simulated outcomes depending who
        # they're actually facing that week.
        opp_factor = (opponent.avg_allowed - league_avg_allowed) / league_avg_allowed
        mean_val = mean_val * (1 + OPPONENT_ADJ_STRENGTH * opp_factor)
    return max(0.0, random.gauss(mean_val, team.stdev))


def _league_avg_allowed(teams: Dict[int, SimTeam]) -> float:
    vals = [t.avg_allowed for t in teams.values()]
    return mean(vals) if vals else 100.0


def _simulate_remaining_regular_season(
    teams: Dict[int, SimTeam],
    remaining_schedule: List[List[Tuple[int, int]]],
    next_week_projected_means: Dict[int, float] = None,
    league_avg_allowed: float = None,
) -> Dict[int, SimTeam]:
    """
    remaining_schedule: list of weeks, each week a list of (team_id_a, team_id_b) matchups
    still left to play. Mutates copies of the SimTeam records with simulated
    outcomes and returns them.

    next_week_projected_means: optional {team_id: projected_points}, applied
    ONLY to the first week in remaining_schedule. ESPN only projects one week
    out (based on that week's actual starting lineups), so this lets the very
    next matchup be simulated around "what ESPN thinks this lineup scores
    this week" instead of the team's flat season average -- meaningfully
    better for the game that's about to happen. Every week after that still
    uses each team's historical avg/stdev, since there's no lineup-specific
    projection for weeks further out yet.
    """
    sim_teams = {
        tid: SimTeam(t.team_id, t.name, list(t.scores_so_far), t.wins, t.losses, t.ties, list(t.points_allowed_so_far))
        for tid, t in teams.items()
    }
    league_avg_allowed = league_avg_allowed if league_avg_allowed is not None else _league_avg_allowed(sim_teams)

    for wk_idx, week in enumerate(remaining_schedule):
        means = next_week_projected_means if (wk_idx == 0 and next_week_projected_means) else {}
        for a_id, b_id in week:
            a, b = sim_teams[a_id], sim_teams[b_id]
            score_a = _draw_score(a, means.get(a_id), opponent=b, league_avg_allowed=league_avg_allowed)
            score_b = _draw_score(b, means.get(b_id), opponent=a, league_avg_allowed=league_avg_allowed)
            a.scores_so_far.append(score_a)
            b.scores_so_far.append(score_b)
            a.points_allowed_so_far.append(score_b)
            b.points_allowed_so_far.append(score_a)
            if score_a > score_b:
                a.wins += 1
                b.losses += 1
            elif score_b > score_a:
                b.wins += 1
                a.losses += 1
            else:
                a.ties += 1
                b.ties += 1
    return sim_teams


def _seed_teams(sim_teams: Dict[int, SimTeam], playoff_team_count: int) -> List[int]:
    """Standard ESPN tiebreak: wins desc, then total points-for desc."""
    ordered = sorted(
        sim_teams.values(),
        key=lambda t: (t.wins + 0.5 * t.ties, sum(t.scores_so_far)),
        reverse=True,
    )
    return [t.team_id for t in ordered[:playoff_team_count]]


def _simulate_bracket(seeds: List[int], sim_teams: Dict[int, SimTeam], league_avg_allowed: float = None) -> List[int]:
    """
    Single-elimination bracket with byes for top seeds when the field isn't a
    power of two, and reseeding each round (highest remaining seed vs. lowest
    remaining seed) -- matches the common fantasy-playoff format and keeps the
    logic simple/general rather than hard-coding one league's exact bracket.
    Returns the ordered list [champion, runner_up, ...eliminated in reverse order].
    """
    remaining = list(seeds)  # already ordered best-seed-first
    elimination_order = []

    while len(remaining) > 1:
        n = len(remaining)
        # figure out how many byes this round: pad to next power of two conceptually
        next_pow2 = 1
        while next_pow2 < n:
            next_pow2 *= 2
        byes = next_pow2 - n if next_pow2 != n else 0
        # top `byes` seeds advance automatically this round
        byed = remaining[:byes]
        playing = remaining[byes:]

        winners = []
        # pair best vs worst among those playing
        i, j = 0, len(playing) - 1
        while i < j:
            a_id, b_id = playing[i], playing[j]
            a, b = sim_teams[a_id], sim_teams[b_id]
            score_a = _draw_score(a, opponent=b, league_avg_allowed=league_avg_allowed)
            score_b = _draw_score(b, opponent=a, league_avg_allowed=league_avg_allowed)
            if score_a >= score_b:
                winners.append(a_id)
                elimination_order.append(b_id)
            else:
                winners.append(b_id)
                elimination_order.append(a_id)
            i += 1
            j -= 1

        remaining = byed + winners
        # re-sort remaining by original seed order so re-seeding stays consistent
        remaining.sort(key=lambda tid: seeds.index(tid))

    champion = remaining[0]
    return [champion] + list(reversed(elimination_order))


def run_simulation(
    teams: Dict[int, SimTeam],
    remaining_schedule: List[List[Tuple[int, int]]],
    playoff_team_count: int = 6,
    n_trials: int = 10000,
    next_week_projected_means: Dict[int, float] = None,
) -> List[SimResult]:
    """
    teams: {team_id: SimTeam} with scores_so_far/wins/losses reflecting the
           season up to (but not including) the next unplayed week
    remaining_schedule: the rest of the regular-season schedule (see
           _simulate_remaining_regular_season)
    playoff_team_count: how many teams make the playoffs in this league
    n_trials: number of Monte Carlo iterations (10k is plenty for stable %s)
    next_week_projected_means: optional {team_id: ESPN-projected points for
           the very next week}, e.g. from
           roster_strength.as_score_dict(roster_strength.compute_roster_strength(...)).
           See _simulate_remaining_regular_season for why this only affects
           week 1 of the simulation.
    """
    made_playoffs = {tid: 0 for tid in teams}
    won_champ = {tid: 0 for tid in teams}
    reached_final = {tid: 0 for tid in teams}
    seed_sum = {tid: 0 for tid in teams}
    league_avg_allowed = _league_avg_allowed(teams)

    for _ in range(n_trials):
        sim_teams = _simulate_remaining_regular_season(teams, remaining_schedule, next_week_projected_means, league_avg_allowed)
        seeds = _seed_teams(sim_teams, playoff_team_count)
        for pos, tid in enumerate(seeds, start=1):
            made_playoffs[tid] += 1
            seed_sum[tid] += pos
        bracket_result = _simulate_bracket(seeds, sim_teams, league_avg_allowed)
        champion = bracket_result[0]
        won_champ[champion] += 1
        if len(bracket_result) > 1:
            reached_final[bracket_result[0]] += 1
            reached_final[bracket_result[1]] += 1

    results = []
    for tid, t in teams.items():
        results.append(
            SimResult(
                team_id=tid,
                name=t.name,
                made_playoffs_pct=round(100 * made_playoffs[tid] / n_trials, 1),
                won_bowl_pct=round(100 * reached_final.get(tid, 0) / n_trials, 1),
                champion_pct=round(100 * won_champ[tid] / n_trials, 1),
                avg_final_seed=round(seed_sum[tid] / made_playoffs[tid], 2) if made_playoffs[tid] else 0.0,
            )
        )
    results.sort(key=lambda r: r.champion_pct, reverse=True)
    return results


def build_remaining_schedule_from_espn(league, through_week: int) -> List[List[Tuple[int, int]]]:
    """
    Pulls the ESPN league's already-known future matchups (ESPN publishes the
    full regular-season schedule up front) for every week after `through_week`
    through the end of the regular season.
    """
    reg_weeks = league.settings.reg_season_count
    schedule = []
    for wk in range(through_week + 1, reg_weeks + 1):
        seen = set()
        week_matchups = []
        for team in league.teams:
            if team.team_id in seen:
                continue
            idx0 = wk - 1
            if idx0 >= len(team.schedule):
                continue
            opp = team.schedule[idx0]
            opp_id = getattr(opp, "team_id", None)
            if opp_id is None or opp_id == team.team_id:
                continue  # bye
            week_matchups.append((team.team_id, opp_id))
            seen.add(team.team_id)
            seen.add(opp_id)
        schedule.append(week_matchups)
    return schedule
