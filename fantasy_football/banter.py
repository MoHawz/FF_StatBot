"""
Turns the numbers into league-appropriate trash talk for GroupMe.

Every award below is backed by an actual stat (this week's scores, luck,
consistency, streaks, rank movement) -- this isn't just random insults, it's
insults with receipts, which is funnier and means nobody can credibly argue
with the bot. Each award category has several phrasing variants so the bot
doesn't say the exact same line every week; the variant is picked
deterministically from (week, team) so a re-run of the same week reproduces
the same message (useful for testing) but different weeks/teams get
different flavor.

Tune freely -- TEMPLATES is just a dict of format strings, no code changes
needed to reword or add lines. `{team}`, `{score}`, `{opp}`, `{margin}`,
`{n}` etc. are filled in per-category; see each award's .format() call for
what's available.
"""
import random
from typing import List

from . import season_stats
from .espn_client import TeamSeason
from .power_rankings import PowerRankingRow

TEMPLATES = {
    "top_score": [
        "{team} dropped {score} points on the league like it owed them money.",
        "{team} put up {score} -- somebody check the waiver wire, that's not legal.",
        "{team} led the league with {score}. Everybody else, take notes.",
    ],
    "bottom_score": [
        "{team} mustered a whopping {score} points. Did the lineup submit itself?",
        "{team} scored {score}. Bold strategy going into the bye week early.",
        "{team} put up {score} -- the kicker probably outscored the whole bench.",
    ],
    "blowout": [
        "{winner} put a {margin}-point beatdown on {loser} ({winner_score} - {loser_score}). Somebody call it.",
        "{winner} demolished {loser} by {margin}. {loser}, that one's going in the family group chat.",
        "{winner} vs {loser} wasn't a matchup, it was a mugging. {margin}-point margin.",
    ],
    "closest": [
        "{winner} survived {loser} by a razor-thin {margin} points. Somebody's stomach hurts.",
        "{winner} escaped with a {margin}-point win over {loser}. Bench points are still crying.",
        "{winner} edged {loser} by {margin}. Every point-decision this week actually mattered.",
    ],
    "riser": [
        "{team} is rocketing up the power rankings, +{n} spots this week. Somebody's paying attention to the waiver wire.",
        "{team} climbed {n} spots. Buy the hype or fade it -- your call.",
        "{team} moved up {n} spots this week. Respect where it's due.",
    ],
    "faller": [
        "{team} fell {n} spots this week. Rough week to be a fan.",
        "{team} is in free fall, -{n} spots. Time for a pep talk.",
        "{team} dropped {n} spots. The power rankings do not care about your feelings.",
    ],
    "lucky": [
"{team} is winning {luck_pts} percentage points more than their scores actually deserve. Somebody's schedule fairy is working overtime.",
        "{team}'s record is carrying their season -- their all-play number says they've been getting away with it.",
        "{team} keeps finding the softest matchup every single week. Enjoy it while it lasts.",
    ],
    "unlucky": [
        "{team} would have a much better record in literally any other schedule. Tough beats all year.",
        "{team} keeps running into buzzsaws -- their all-play number is way better than their actual record.",
        "{team}'s schedule has been an absolute gauntlet. The football gods owe them one.",
    ],
    "consistent": [
        "{team} shows up every single week like clockwork ({stdev} stdev). Boring, but effective.",
        "{team} is the most reliable team in the league -- you know exactly what you're getting.",
    ],
    "volatile": [
        "{team} is a rollercoaster ({stdev} stdev) -- nobody, including {team}, knows what's coming next.",
        "{team} either drops 160 or drops 60, there is no in-between.",
    ],
    "win_streak": [
        "{team} is riding a {n}-game win streak. Somebody get in front of this before it's too late.",
        "{team} has won {n} straight. The rest of the league should be nervous.",
    ],
    "lose_streak": [
        "{team} has dropped {n} straight. Time to start selling off the roster.",
        "{team} is on a {n}-game skid. It's not looking good.",
    ],
    "bench_tax": [
        "{team} left {points} points on the bench this week. That's a whole extra player's worth of 'oops.'",
    ],
    "big_spender": [
        "\U0001F911 {team} dropped ${paid} on {player} -- {pct}% of what they had left. Bold, or desperate. Maybe both.",
        "\U0001F911 {team} went all-in for {player} at ${paid}, torching {pct}% of their remaining budget in one move.",
    ],
    "faab_overpaid": [
        "{team} paid ${paid} for {player}, ${overpaid} more than they needed to. Money well... spent?",
        "{team} could've had {player} for a lot less -- ${overpaid} over the next bid. Hope he pans out.",
    ],
    "faab_bargain": [
        "{team} snagged {player} for just ${paid} with {bidders} teams in on it. Absolute heist.",
        "{team} got {player} at a discount -- ${paid} against real competition. Well played.",
    ],
    "faab_contested": [
        "{player} drew {bidders} different bids this week. Somebody clearly needed him.",
    ],
    "lock_of_week": [
        "{favorite} over {underdog}: {pct}% to win. This one's over before it starts.",
    ],
    "toss_up": [
        "{home} vs {away}: {pct}% / {pct2}%. Coin flip. Set your alarms, this one'll come down to Monday night.",
    ],
}


def _pick(category: str, seed) -> str:
    return random.Random(str(seed)).choice(TEMPLATES[category])


def generate_weekly_awards(
    week: int,
    rows: List[PowerRankingRow],
    team_seasons: List[TeamSeason],
    bench_points: dict = None,
) -> List[tuple]:
    """Returns a list of (emoji_title, line) tuples, ready to hand to
    banter.format_awards_message() or your own formatting."""
    awards = []
    hl = season_stats.this_week_highlights(team_seasons, week)

    if hl["top_score"]:
        t = hl["top_score"]
        awards.append(("\U0001F451 Boss of the Week", _pick("top_score", (week, t["team"])).format(**t)))
    if hl["bottom_score"]:
        t = hl["bottom_score"]
        awards.append(("\U0001F4A9 Didn't Show Up", _pick("bottom_score", (week, t["team"])).format(**t)))
    if hl["blowout"]:
        b = hl["blowout"]
        awards.append(("\U0001F528 Mercy Rule", _pick("blowout", (week, b["winner"])).format(**b)))
    if hl["closest"] and hl["closest"] != hl["blowout"]:
        c = hl["closest"]
        awards.append(("\U0001F62C Nail-Biter", _pick("closest", (week, c["winner"])).format(**c)))

    # Rank movement (requires previous_ranks to have been supplied to compute_power_rankings)
    movers = [r for r in rows if r.movement != 0]
    if movers:
        riser = max(movers, key=lambda r: r.movement)
        if riser.movement > 0:
            awards.append(("\U0001F680 Rocket Ship", _pick("riser", (week, riser.team_name)).format(team=riser.team_name, n=riser.movement)))
        faller = min(movers, key=lambda r: r.movement)
        if faller.movement < 0:
            awards.append(("\U0001F4C9 Free Fall", _pick("faller", (week, faller.team_name)).format(team=faller.team_name, n=abs(faller.movement))))

    # Luck (season-cumulative all-play vs actual record -- single-week luck is too noisy to be meaningful).
    # Also too noisy in the first couple weeks regardless of framing (1-2 games isn't a sample), so
    # skip this category entirely until there's enough season to say anything real.
    games_played = max((len(ts.weeks) for ts in team_seasons), default=0)
    luck_rows = season_stats.luckiest_and_unluckiest(team_seasons) if games_played >= 3 else []
    if luck_rows:
        luckiest = luck_rows[0]
        if luckiest["luck_pts"] > 0:
            awards.append(("\U0001F340 Luck Dragon", _pick("lucky", (week, luckiest["team"])).format(team=luckiest["team"], luck_pts=luckiest["luck_pts"])))
        unluckiest = luck_rows[-1]
        if unluckiest["luck_pts"] < 0:
            awards.append(("\U0001F480 Snake-Bitten", _pick("unlucky", (week, unluckiest["team"])).format(team=unluckiest["team"], luck_pts=unluckiest["luck_pts"])))

    # Consistency
    consist = season_stats.most_consistent(team_seasons)
    if len(consist) >= 2:
        stable = consist[0]
        awards.append(("\U0001F3AF Human Metronome", _pick("consistent", (week, stable["team"])).format(team=stable["team"], stdev=stable["stdev"])))
        volatile = consist[-1]
        if volatile["team"] != stable["team"]:
            awards.append(("\U0001F3A2 Human Rollercoaster", _pick("volatile", (week, volatile["team"])).format(team=volatile["team"], stdev=volatile["stdev"])))

    # Streaks
    streaks = season_stats.current_streaks(team_seasons)
    hottest = max(streaks.items(), key=lambda kv: kv[1], default=(None, 0))
    if hottest[1] >= 3:
        awards.append(("\U0001F525 On Fire", _pick("win_streak", (week, hottest[0])).format(team=hottest[0], n=hottest[1])))
    coldest = min(streaks.items(), key=lambda kv: kv[1], default=(None, 0))
    if coldest[1] <= -3:
        awards.append(("\U0001F9CA Ice Cold", _pick("lose_streak", (week, coldest[0])).format(team=coldest[0], n=abs(coldest[1]))))

    # Bench mismanagement, if bench_points was supplied (e.g. from
    # season_stats.bench_points_left_on_table for just this week)
    if bench_points:
        worst_team, worst_points = max(bench_points.items(), key=lambda kv: kv[1])
        if worst_points > 15:
            awards.append(("\U0001FA91 Bench Tax", _pick("bench_tax", (week, worst_team)).format(team=worst_team, points=round(worst_points, 1))))

    return awards


def format_awards_message(week: int, awards: List[tuple]) -> str:
    lines = [f"\U0001F3C6 WEEK {week} AWARDS \U0001F3C6"]
    for title, line in awards:
        lines.append(f"{title}: {line}")
    return "\n".join(lines)


def generate_faab_awards(report) -> List[tuple]:
    """report: a faab_report.FaabReport."""
    awards = []
    week = report.week

    for b in report.budgets:
        if b.is_big_spender:
            pct = round(100 * b.biggest_bid_this_week / b.remaining_before_this_week)
            # find the player they spent big on
            claim = next((c for c in report.claims if c.winning_team == b.team and c.paid == b.biggest_bid_this_week), None)
            player = claim.player if claim else "someone"
            awards.append(("\U0001F911 Big Spender", _pick("big_spender", (week, b.team)).format(
                team=b.team, paid=b.biggest_bid_this_week, pct=pct, player=player)))

    if report.claims:
        biggest_overpay = report.claims[0]  # already sorted desc by overpaid
        if biggest_overpay.overpaid > 0 and biggest_overpay.bidders > 1:
            awards.append(("\U0001F4B8 Overpaid", _pick("faab_overpaid", (week, biggest_overpay.winning_team)).format(
                team=biggest_overpay.winning_team, player=biggest_overpay.player, overpaid=biggest_overpay.overpaid, paid=biggest_overpay.paid)))

        contested = [c for c in report.claims if c.bidders > 1]
        if contested:
            bargain = min(contested, key=lambda c: c.paid)
            awards.append(("\U0001F48E Bargain Bin", _pick("faab_bargain", (week, bargain.winning_team)).format(
                team=bargain.winning_team, player=bargain.player, paid=bargain.paid, bidders=bargain.bidders)))

            most_wanted = max(contested, key=lambda c: c.bidders)
            awards.append(("\U0001F440 Most Wanted", _pick("faab_contested", (week, most_wanted.player)).format(
                player=most_wanted.player, bidders=most_wanted.bidders)))

    return awards


def generate_prediction_banter(predictions: List) -> List[tuple]:
    """predictions: list of weekly_prediction.MatchupPrediction."""
    awards = []
    if not predictions:
        return awards
    week = predictions[0].week

    locks = [p for p in predictions if p.confidence == "Lock"]
    if locks:
        biggest = max(locks, key=lambda p: max(p.home_win_pct, p.away_win_pct))
        fav, dog, pct = (
            (biggest.home_team, biggest.away_team, biggest.home_win_pct)
            if biggest.home_win_pct > biggest.away_win_pct
            else (biggest.away_team, biggest.home_team, biggest.away_win_pct)
        )
        awards.append(("\U0001F512 Lock of the Week", _pick("lock_of_week", (week, fav)).format(favorite=fav, underdog=dog, pct=pct)))

    toss_ups = [p for p in predictions if p.confidence == "Toss-Up"]
    if toss_ups:
        closest = min(toss_ups, key=lambda p: abs(p.home_win_pct - p.away_win_pct))
        awards.append(("\U0001FA99 Coin Flip", _pick("toss_up", (week, closest.home_team)).format(
            home=closest.home_team, away=closest.away_team, pct=closest.home_win_pct, pct2=closest.away_win_pct)))

    return awards
