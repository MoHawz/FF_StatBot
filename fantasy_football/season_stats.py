"""
End-of-season "interesting tidbits" generator, meant to feed the year-end
PowerPoint (in the spirit of the old "OTHER STATS" / "It's all won and lost
in the..." slides). Everything here returns plain dicts/lists so it's easy
to drop straight into slide bullets or a table.
"""
from statistics import mean, pstdev
from typing import List

from .espn_client import TeamSeason
from .power_rankings import compute_power_rankings


def biggest_blowout(team_seasons: List[TeamSeason]):
    best = None
    for ts in team_seasons:
        for w in ts.weeks:
            if w.opponent_score is None:
                continue
            margin = w.score - w.opponent_score
            if best is None or margin > best["margin"]:
                best = {
                    "week": w.week, "winner": ts.team_name, "loser": w.opponent_name,
                    "winner_score": w.score, "loser_score": w.opponent_score, "margin": round(margin, 2),
                }
    return best


def closest_game(team_seasons: List[TeamSeason]):
    best = None
    for ts in team_seasons:
        for w in ts.weeks:
            if w.opponent_score is None or w.is_tie:
                continue
            margin = abs(w.score - w.opponent_score)
            if best is None or margin < best["margin"]:
                best = {
                    "week": w.week, "team_a": ts.team_name, "team_b": w.opponent_name,
                    "score_a": w.score, "score_b": w.opponent_score, "margin": round(margin, 2),
                }
    return best


def highest_single_week(team_seasons: List[TeamSeason]):
    best = None
    for ts in team_seasons:
        for w in ts.weeks:
            if best is None or w.score > best["score"]:
                best = {"week": w.week, "team": ts.team_name, "score": w.score}
    return best


def lowest_single_week(team_seasons: List[TeamSeason]):
    worst = None
    for ts in team_seasons:
        for w in ts.weeks:
            if worst is None or w.score < worst["score"]:
                worst = {"week": w.week, "team": ts.team_name, "score": w.score}
    return worst


def most_consistent(team_seasons: List[TeamSeason]):
    rows = []
    for ts in team_seasons:
        scores = [w.score for w in ts.weeks]
        if len(scores) > 1:
            rows.append({"team": ts.team_name, "stdev": round(pstdev(scores), 2), "avg": round(mean(scores), 2)})
    rows.sort(key=lambda r: r["stdev"])
    return rows


def luckiest_and_unluckiest(team_seasons: List[TeamSeason]):
    """
    Compares actual win% to all-play win% (the % of games a team would have
    won if its weekly score were matched against every other team's score
    that week). A team well above its all-play win% got favorable
    matchups ("lucky"); well below means brutal matchups ("unlucky").
    """
    rankings = compute_power_rankings(team_seasons)
    rows = []
    for r in rankings:
        diff = round((r.win_pct - r.all_play_pct) * 100, 1)
        rows.append({"team": r.team_name, "actual_win_pct": r.win_pct, "all_play_pct": r.all_play_pct, "luck_pts": diff})
    rows.sort(key=lambda r: r["luck_pts"], reverse=True)
    return rows


def longest_streaks(team_seasons: List[TeamSeason]):
    results = []
    for ts in team_seasons:
        best_win, best_loss, cur_win, cur_loss = 0, 0, 0, 0
        for w in ts.weeks:
            if w.is_tie:
                cur_win = cur_loss = 0
                continue
            if w.is_win:
                cur_win += 1
                cur_loss = 0
            else:
                cur_loss += 1
                cur_win = 0
            best_win = max(best_win, cur_win)
            best_loss = max(best_loss, cur_loss)
        results.append({"team": ts.team_name, "longest_win_streak": best_win, "longest_loss_streak": best_loss})
    return results


def current_streaks(team_seasons: List[TeamSeason]) -> dict:
    """{team_name: signed_streak} -- positive N = currently on an N-game win
    streak, negative N = currently on an N-game losing streak, 0 = last game
    was a tie or no games played. Used to call out someone riding hot or
    someone in a nosedive."""
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
        out[ts.team_name] = streak
    return out


def this_week_highlights(team_seasons: List[TeamSeason], week: int):
    """Same shape as biggest_blowout/closest_game/highest_single_week/
    lowest_single_week above, but scoped to just one week -- what you want
    for a "this week" GroupMe recap rather than a season-long superlative."""
    this_week = [(ts, w) for ts in team_seasons for w in ts.weeks if w.week == week]

    top = max(this_week, key=lambda tw: tw[1].score, default=None)
    bottom = min(this_week, key=lambda tw: tw[1].score, default=None)

    blowout, closest = None, None
    seen_pairs = set()
    for ts, w in this_week:
        if w.opponent_score is None or w.is_tie:
            continue
        pair = frozenset((ts.team_id, w.opponent_id))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        margin = abs(w.score - w.opponent_score)
        winner, loser = (ts.team_name, w.opponent_name) if w.score > w.opponent_score else (w.opponent_name, ts.team_name)
        winner_score, loser_score = max(w.score, w.opponent_score), min(w.score, w.opponent_score)
        entry = {"winner": winner, "loser": loser, "winner_score": winner_score, "loser_score": loser_score, "margin": round(margin, 2)}
        if blowout is None or margin > blowout["margin"]:
            blowout = entry
        if closest is None or margin < closest["margin"]:
            closest = entry

    return {
        "top_score": {"team": top[0].team_name, "score": top[1].score} if top else None,
        "bottom_score": {"team": bottom[0].team_name, "score": bottom[1].score} if bottom else None,
        "blowout": blowout,
        "closest": closest,
    }


def transactions_summary(team_seasons: List[TeamSeason]):
    rows = [
        {"team": ts.team_name, "acquisitions": ts.acquisitions, "trades": ts.trades, "drops": ts.drops}
        for ts in team_seasons
    ]
    rows.sort(key=lambda r: r["acquisitions"], reverse=True)
    return rows


def bench_points_left_on_table(league, weeks: range):
    """
    Requires live box scores (needs an active ESPN connection). Sums, per
    team, how many points sat on the bench instead of the starting lineup
    each week -- a fun "what could have been" stat for the presentation.
    """
    totals = {}
    for wk in weeks:
        for box in league.box_scores(week=wk):
            for side_team, lineup in ((box.home_team, box.home_lineup), (box.away_team, box.away_lineup)):
                if side_team == 0:
                    continue
                name = getattr(side_team, "team_name", str(side_team))
                bench_pts = sum(p.points for p in lineup if p.slot_position in ("BE", "IR"))
                totals.setdefault(name, 0.0)
                totals[name] += bench_pts
    rows = [{"team": k, "bench_points_left": round(v, 2)} for k, v in totals.items()]
    rows.sort(key=lambda r: r["bench_points_left"], reverse=True)
    return rows


def build_season_report(team_seasons: List[TeamSeason]) -> dict:
    """One-call bundle of everything above, ready to hand to the pptx builder."""
    return {
        "biggest_blowout": biggest_blowout(team_seasons),
        "closest_game": closest_game(team_seasons),
        "highest_single_week": highest_single_week(team_seasons),
        "lowest_single_week": lowest_single_week(team_seasons),
        "most_consistent": most_consistent(team_seasons),
        "luck": luckiest_and_unluckiest(team_seasons),
        "streaks": longest_streaks(team_seasons),
        "transactions": transactions_summary(team_seasons),
        "final_power_rankings": compute_power_rankings(team_seasons),
    }
