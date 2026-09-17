"""
Turns the numbers into league-appropriate trash talk for GroupMe.

Every award below is backed by an actual stat (this week's scores, luck,
consistency, streaks, rank movement) -- this isn't just random insults, it's
insults with receipts, which is funnier and means nobody can credibly argue
with the bot.

Staying fresh across a 17-week season: each category has ~10 phrasing
variants (not 2-3), and instead of picking one at random each time (which
can and will repeat a line in back-to-back weeks purely by chance), `_pick`
draws from a per-category "shuffle bag" persisted in a small local JSON
file (see BanterState below) -- every variant gets used once before any of
them repeat, and the picker won't hand you the same line twice in a row
even across a reshuffle. With 10 variants per category and a handful of
awards firing most weeks, that's a full season-plus before you'd ever see
a repeat in a single category, and repeats that do happen won't be
adjacent. Bump TEMPLATES with more lines any time -- no code changes
needed, they just join the rotation.

Tune freely -- TEMPLATES is just a dict of format strings. `{team}`,
`{score}`, `{opp}`, `{margin}`, `{n}` etc. are filled in per-category; see
each award's .format() call for what's available.
"""
import json
import os
import random
from typing import List, Optional

from . import season_stats
from .espn_client import TeamSeason
from .power_rankings import PowerRankingRow

BANTER_STATE_FILE = "banter_state.json"

TEMPLATES = {
    "top_score": [
        "{team} dropped {score} points on the league like it owed them money.",
        "{team} put up {score} -- somebody check the waiver wire, that's not legal.",
        "{team} led the league with {score}. Everybody else, take notes.",
        "{team} torched the scoreboard for {score}. The rest of the league is filing a complaint.",
        "{team} posted {score} and made it look easy. It was not easy for anyone else.",
        "{score} points for {team}. That's not a lineup, that's a cheat code.",
        "{team} put the league on notice with {score} this week. Somebody wake up and respond.",
        "Nobody touched {team}'s {score} this week. Not close, not competitive, just done.",
        "{team} scored {score} and is currently accepting congratulations, none of them sincere.",
        "{team} went off for {score}. Somewhere, an opposing GM is refreshing the box score in disbelief.",
    ],
    "bottom_score": [
        "{team} mustered a whopping {score} points. Did the lineup submit itself?",
        "{team} scored {score}. Bold strategy going into the bye week early.",
        "{team} put up {score} -- the kicker probably outscored the whole bench.",
        "{score} points from {team}. The league thanks you for your donation.",
        "{team} scored {score} this week, which is technically still a number.",
        "{team} put up {score} and somehow still had to play the whole game.",
        "{team}'s {score} points is the kind of performance that gets a coach fired, if this were real.",
        "{score}. That's it. That's {team}'s week.",
        "{team} scored {score} -- somewhere, their bench players are relieved they didn't play either.",
        "{team} rounded out the week with {score} points, in last place, alone, deservedly.",
    ],
    "blowout": [
        "{winner} put a {margin}-point beatdown on {loser} ({winner_score} - {loser_score}). Somebody call it.",
        "{winner} demolished {loser} by {margin}. {loser}, that one's going in the family group chat.",
        "{winner} vs {loser} wasn't a matchup, it was a mugging. {margin}-point margin.",
        "{winner} beat {loser} by {margin} points. {loser} should ask for a recount, then accept reality.",
        "{margin}-point blowout: {winner} over {loser}. Not much else to say about that one.",
        "{winner} ran up the score on {loser}, {winner_score} to {loser_score}. Mercy was not considered.",
        "{loser} lost to {winner} by {margin}. Everyone in the league saw that score and winced.",
        "{winner} made {loser} look like a bye week, final margin {margin}.",
        "{winner} over {loser}, {winner_score}-{loser_score}. {loser}'s week is officially cancelled.",
        "That {winner}-{loser} game was over by halftime, on paper -- {margin}-point final margin.",
    ],
    "closest": [
        "{winner} survived {loser} by a razor-thin {margin} points. Somebody's stomach hurts.",
        "{winner} escaped with a {margin}-point win over {loser}. Bench points are still crying.",
        "{winner} edged {loser} by {margin}. Every point-decision this week actually mattered.",
        "{winner} beat {loser} by a gut-punch {margin} points. That one's going to sting for days.",
        "{margin}-point final between {winner} and {loser}. Somebody's lineup decision from Tuesday decided this.",
        "{winner} squeaked past {loser}, {winner_score}-{loser_score}. Closest game of the week, easily.",
        "{loser} came within {margin} points of {winner}. So close, and yet a loss is a loss.",
        "{winner} over {loser} by {margin}. If one waiver claim had gone differently, this flips.",
        "{margin} points separated {winner} and {loser}. Somebody's bench outscored their whole starting lineup by more than that.",
        "{winner} held on against {loser} by the skin of their teeth, {margin} points.",
    ],
    "riser": [
        "{team} is rocketing up the power rankings, +{n} spots this week. Somebody's paying attention to the waiver wire.",
        "{team} climbed {n} spots. Buy the hype or fade it -- your call.",
        "{team} moved up {n} spots this week. Respect where it's due.",
        "{team} jumped {n} spots in the rankings. The rest of the league should be taking notice.",
        "+{n} spots for {team} this week. Somebody's figured something out.",
        "{team} is on the move, up {n} spots. Don't sleep on it.",
        "{team} climbed {n} spots this week -- quietly building something real.",
        "{n} spots in one week for {team}. That's not a fluke, that's a trend.",
        "{team} surged {n} spots up the board. The league's a little different now.",
        "{team} made a real statement this week, +{n} in the power rankings.",
    ],
    "faller": [
        "{team} fell {n} spots this week. Rough week to be a fan.",
        "{team} is in free fall, -{n} spots. Time for a pep talk.",
        "{team} dropped {n} spots. The power rankings do not care about your feelings.",
        "{n} spots down for {team} this week. That's a bad look, no matter how you slice it.",
        "{team} slid {n} spots in the rankings. Somebody needs to fix this roster, fast.",
        "-{n} for {team} this week. The bottom is not that far away anymore.",
        "{team} tumbled {n} spots. The rankings have no sympathy, and neither does this bot.",
        "{team} fell {n} spots -- the kind of week that shows up in the standings for a month.",
        "{n}-spot drop for {team}. That's a full-blown crisis by fantasy football standards.",
        "{team} is sliding, down {n} spots this week alone. Somebody check the waiver wire.",
    ],
    "lucky": [
        "{team} is winning {luck_pts} percentage points more than their scores actually deserve. Somebody's schedule fairy is working overtime.",
        "{team}'s record is carrying their season -- their all-play number says they've been getting away with it.",
        "{team} keeps finding the softest matchup every single week. Enjoy it while it lasts.",
        "{team} has been getting favorable matchups all season -- the all-play numbers don't lie.",
        "{team}'s win total is doing a lot of heavy lifting for a team scoring what they're scoring.",
        "{team} keeps winning the games that matter and losing the ones that don't count. Convenient.",
        "The schedule has been kind to {team}, by about {luck_pts} percentage points' worth of kind.",
        "{team} might be the luckiest team in the league right now, and the numbers back it up.",
        "{team}'s record looks great. {team}'s all-play record looks a lot less great. Make of that what you will.",
        "{team} is out here winning close ones every week. At some point that stops being luck, or does it?",
    ],
    "unlucky": [
        "{team} would have a much better record in literally any other schedule. Tough beats all year.",
        "{team} keeps running into buzzsaws -- their all-play number is way better than their actual record.",
        "{team}'s schedule has been an absolute gauntlet. The football gods owe them one.",
        "{team} has been the unluckiest team in the league by the numbers, full stop.",
        "{team}'s record does not reflect how good this team actually is. The schedule is the problem.",
        "{team} keeps drawing the hot team every single week. That's rough scheduling, not bad play.",
        "If the schedule were fair, {team} would be a completely different story right now.",
        "{team}'s all-play win percentage says they're a playoff team. Their actual record disagrees. The all-play number is right.",
        "{team} has lost more heartbreakers than anyone in the league. It's genuinely not their fault.",
        "{team} is playing better than their record shows, by a wide margin.",
    ],
    "consistent": [
        "{team} shows up every single week like clockwork ({stdev} stdev). Boring, but effective.",
        "{team} is the most reliable team in the league -- you know exactly what you're getting.",
        "{team} doesn't have big weeks or bad weeks, just weeks. Stdev of {stdev} and counting.",
        "{team} is metronomic ({stdev} stdev). No fireworks, no disasters, just steady points.",
        "{team} is the definition of consistent -- {stdev} standard deviation says it all.",
        "You could set your watch by {team}'s scoring. {stdev} stdev, week after week.",
        "{team} doesn't beat you by much or lose by much. Just steady, dependable football.",
        "{team}'s scoring is basically the same number every week ({stdev} stdev). Predictably good.",
        "No drama with {team} -- {stdev} stdev, same team every single Sunday.",
        "{team} is proof that boring wins leagues. {stdev} stdev, all season long.",
    ],
    "volatile": [
        "{team} is a rollercoaster ({stdev} stdev) -- nobody, including {team}, knows what's coming next.",
        "{team} either drops 160 or drops 60, there is no in-between.",
        "{team}'s weekly scores look like a heart monitor ({stdev} stdev). Buckle up.",
        "{team} is either the best team in the league or the worst, depending on the week.",
        "You genuinely cannot predict {team}'s score. {stdev} stdev proves it.",
        "{team} is must-watch television every single week -- feast or famine, {stdev} stdev.",
        "{team}'s consistency rating is 'chaos.' {stdev} standard deviation, no explanation needed.",
        "{team} could put up a season-high or a season-low this week and nobody would be surprised.",
        "{team}'s scores swing wildly week to week ({stdev} stdev). Not a team for the faint of heart.",
        "Opposing {team} is a coin flip every week, and the numbers back that up ({stdev} stdev).",
    ],
    "win_streak": [
        "{team} is riding a {n}-game win streak. Somebody get in front of this before it's too late.",
        "{team} has won {n} straight. The rest of the league should be nervous.",
        "{n} in a row for {team}. This isn't a hot streak anymore, it's a new normal.",
        "{team} keeps winning -- {n} straight now. Somebody needs to figure out how to stop this.",
        "{n}-game win streak for {team}. The league is starting to take notice, finally.",
        "{team} hasn't lost in {n} weeks. At what point does this become a real threat?",
        "{team} is {n} wins deep on their current streak. This is what a contender looks like.",
        "{n} straight wins for {team}. The schedule-makers owe everyone else an apology.",
        "{team} keeps finding ways to win, {n} weeks running now.",
        "{team}'s {n}-game win streak is quietly becoming the story of the season.",
    ],
    "lose_streak": [
        "{team} has dropped {n} straight. Time to start selling off the roster.",
        "{team} is on a {n}-game skid. It's not looking good.",
        "{n} losses in a row for {team}. Somebody stage an intervention.",
        "{team} hasn't won in {n} weeks. The playoffs are getting further away by the day.",
        "{team} is {n} games deep into a losing streak with no end in sight.",
        "{n} straight losses for {team}. At some point this stops being bad luck.",
        "{team} keeps finding new ways to lose, {n} weeks running.",
        "{team}'s {n}-game skid is turning into a full-blown lost season.",
        "{team} hasn't tasted a win in {n} weeks. Somebody check on them.",
        "{n} losses in a row. {team}'s season is hanging by a thread.",
    ],
    "bench_tax": [
        "{team} left {points} points on the bench this week. That's a whole extra player's worth of 'oops.'",
        "{team} benched {points} points worth of production. The lineup card is not your friend this week.",
        "{points} points sat on {team}'s bench doing nothing. That's a self-inflicted loss waiting to happen.",
        "{team} left {points} points at home. Set your lineup, folks.",
        "{team}'s bench outscored their decision-making by {points} points this week.",
        "{points} wasted points for {team}. The right lineup was sitting right there.",
        "{team} could have had {points} more points with better lineup decisions. Could have.",
        "{team} paid the bench tax this week -- {points} points left unclaimed.",
    ],
    "big_spender": [
        "\U0001F911 {team} dropped ${paid} on {player} -- {pct}% of what they had left. Bold, or desperate. Maybe both.",
        "\U0001F911 {team} went all-in for {player} at ${paid}, torching {pct}% of their remaining budget in one move.",
        "\U0001F911 {team} bet {pct}% of their FAAB on {player}. Hope he's worth it.",
        "\U0001F911 {player} just cost {team} ${paid} -- {pct}% of the war chest, gone in one bid.",
        "\U0001F911 {team} emptied the tank for {player}: ${paid}, {pct}% of what they had left.",
        "\U0001F911 That's a commitment -- {team} spent {pct}% of their remaining budget on {player} alone.",
        "\U0001F911 {team} said 'no more waiting' and dropped ${paid} ({pct}% of their budget) on {player}.",
    ],
    "faab_overpaid": [
        "{team} paid ${paid} for {player}, ${overpaid} more than they needed to. Money well... spent?",
        "{team} could've had {player} for a lot less -- ${overpaid} over the next bid. Hope he pans out.",
        "{team} left ${overpaid} on the table for {player}. Somebody didn't scout the competition.",
        "${overpaid} over the next highest bid for {player}. {team} really wanted this one.",
        "{team} paid a {overpaid}-dollar premium for {player}. That's a tax on panic, not talent.",
        "{team} won {player} at ${paid}, ${overpaid} more than anyone else was willing to pay. Confidence, or overpay -- time will tell.",
    ],
    "faab_bargain": [
        "{team} snagged {player} for just ${paid} with {bidders} teams in on it. Absolute heist.",
        "{team} got {player} at a discount -- ${paid} against real competition. Well played.",
        "{player} for ${paid} with {bidders} bidders in the mix? {team} stole that.",
        "{team} won a bidding war for {player} and still only paid ${paid}. Great process.",
        "${paid} for {player}, beating out {bidders} other bidders. {team} played that perfectly.",
        "{team} got the better end of a {bidders}-team bidding war on {player}, at just ${paid}.",
    ],
    "faab_contested": [
        "{player} drew {bidders} different bids this week. Somebody clearly needed him.",
        "{bidders} teams went after {player}. That's the most contested claim of the week.",
        "{player} was the hottest name on waivers -- {bidders} bids and counting.",
        "Everybody wanted {player} this week. {bidders} different bids tells the story.",
    ],
    "lock_of_week": [
        "{favorite} over {underdog}: {pct}% to win. This one's over before it starts.",
        "{favorite} is about as safe a bet as this league gets this week -- {pct}% against {underdog}.",
        "Book it: {favorite} over {underdog}, {pct}% win probability. Nothing to see here.",
        "{underdog} is playing {favorite} this week, and the numbers ({pct}%) are not kind.",
        "{favorite} should win this one comfortably -- {pct}% against {underdog}.",
        "The model likes {favorite} big this week: {pct}% over {underdog}.",
    ],
    "toss_up": [
        "{home} vs {away}: {pct}% / {pct2}%. Coin flip. Set your alarms, this one'll come down to Monday night.",
        "{home} and {away} are basically even this week -- {pct}% to {pct2}%. Anyone's game.",
        "Dead heat: {home} ({pct}%) vs {away} ({pct2}%). This is the game to watch.",
        "{home} vs {away} is as close to a 50/50 as the model gets -- {pct}% / {pct2}%.",
        "Nobody knows how {home} vs {away} goes. {pct}% to {pct2}% says it all.",
        "The closest projection of the week: {home} ({pct}%) vs {away} ({pct2}%).",
    ],
}


def _load_state(path: str = BANTER_STATE_FILE) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict, path: str = BANTER_STATE_FILE) -> None:
    try:
        with open(path, "w") as f:
            json.dump(state, f)
    except OSError:
        pass  # non-fatal -- banter still works this run, just won't remember rotation for next time


class BanterState:
    """
    A per-category "shuffle bag": every variant in TEMPLATES[category] gets
    drawn once, in a random order, before any of them repeat -- and the
    reshuffle at the end of a bag is checked against the last-drawn variant
    so you never get the same line twice in a row even across that seam.
    Much stronger freshness guarantee than plain random.choice(), which can
    (and eventually will) repeat a line in back-to-back weeks by chance.

    Persisted to a small local JSON file between runs, since each weekly
    script is a fresh process -- same idea as prev_ranks.json for movement
    arrows. Call .save() once at the end of a real run; skip it (or use a
    fresh BanterState()) for a test/dry run so testing doesn't burn through
    the season's rotation.
    """

    def __init__(self, path: str = BANTER_STATE_FILE, load: bool = True):
        self.path = path
        self._state = _load_state(path) if load else {}
        self._rng = random.Random()

    def pick(self, category: str) -> str:
        variants = TEMPLATES[category]
        n = len(variants)
        if n == 0:
            return ""
        if n == 1:
            return variants[0]

        cat_state = self._state.setdefault(category, {"bag": [], "last": None})
        if not cat_state["bag"]:
            bag = list(range(n))
            self._rng.shuffle(bag)
            if cat_state["last"] is not None and bag[0] == cat_state["last"]:
                swap_at = self._rng.randrange(1, n)
                bag[0], bag[swap_at] = bag[swap_at], bag[0]
            cat_state["bag"] = bag

        idx = cat_state["bag"].pop(0)
        cat_state["last"] = idx
        return variants[idx]

    def save(self) -> None:
        _save_state(self._state, self.path)


def generate_weekly_awards(
    week: int,
    rows: List[PowerRankingRow],
    team_seasons: List[TeamSeason],
    bench_points: dict = None,
    banter_state: Optional[BanterState] = None,
) -> List[tuple]:
    """Returns a list of (emoji_title, line) tuples, ready to hand to
    banter.format_awards_message() or your own formatting.

    banter_state: pass a BanterState to control rotation persistence (e.g.
    a fresh, unsaved one for a dry run). Defaults to loading+saving the
    shared banter_state.json if not given -- fine for normal one-shot script
    runs, since each process loads fresh and this is the only place picks
    happen in that process.
    """
    bs = banter_state or BanterState()
    awards = []
    hl = season_stats.this_week_highlights(team_seasons, week)

    if hl["top_score"]:
        t = hl["top_score"]
        awards.append(("\U0001F451 Boss of the Week", bs.pick("top_score").format(**t)))
    if hl["bottom_score"]:
        t = hl["bottom_score"]
        awards.append(("\U0001F4A9 Didn't Show Up", bs.pick("bottom_score").format(**t)))
    if hl["blowout"]:
        b = hl["blowout"]
        awards.append(("\U0001F528 Mercy Rule", bs.pick("blowout").format(**b)))
    if hl["closest"] and hl["closest"] != hl["blowout"]:
        c = hl["closest"]
        awards.append(("\U0001F62C Nail-Biter", bs.pick("closest").format(**c)))

    # Rank movement (requires previous_ranks to have been supplied to compute_power_rankings)
    movers = [r for r in rows if r.movement != 0]
    if movers:
        riser = max(movers, key=lambda r: r.movement)
        if riser.movement > 0:
            awards.append(("\U0001F680 Rocket Ship", bs.pick("riser").format(team=riser.team_name, n=riser.movement)))
        faller = min(movers, key=lambda r: r.movement)
        if faller.movement < 0:
            awards.append(("\U0001F4C9 Free Fall", bs.pick("faller").format(team=faller.team_name, n=abs(faller.movement))))

    # Luck (season-cumulative all-play vs actual record -- single-week luck is too noisy to be meaningful).
    # Also too noisy in the first couple weeks regardless of framing (1-2 games isn't a sample), so
    # skip this category entirely until there's enough season to say anything real.
    games_played = max((len(ts.weeks) for ts in team_seasons), default=0)
    luck_rows = season_stats.luckiest_and_unluckiest(team_seasons) if games_played >= 3 else []
    if luck_rows:
        luckiest = luck_rows[0]
        if luckiest["luck_pts"] > 0:
            awards.append(("\U0001F340 Luck Dragon", bs.pick("lucky").format(team=luckiest["team"], luck_pts=luckiest["luck_pts"])))
        unluckiest = luck_rows[-1]
        if unluckiest["luck_pts"] < 0:
            awards.append(("\U0001F480 Snake-Bitten", bs.pick("unlucky").format(team=unluckiest["team"], luck_pts=unluckiest["luck_pts"])))

    # Consistency
    consist = season_stats.most_consistent(team_seasons)
    if len(consist) >= 2:
        stable = consist[0]
        awards.append(("\U0001F3AF Human Metronome", bs.pick("consistent").format(team=stable["team"], stdev=stable["stdev"])))
        volatile = consist[-1]
        if volatile["team"] != stable["team"]:
            awards.append(("\U0001F3A2 Human Rollercoaster", bs.pick("volatile").format(team=volatile["team"], stdev=volatile["stdev"])))

    # Streaks
    streaks = season_stats.current_streaks(team_seasons)
    hottest = max(streaks.items(), key=lambda kv: kv[1], default=(None, 0))
    if hottest[1] >= 3:
        awards.append(("\U0001F525 On Fire", bs.pick("win_streak").format(team=hottest[0], n=hottest[1])))
    coldest = min(streaks.items(), key=lambda kv: kv[1], default=(None, 0))
    if coldest[1] <= -3:
        awards.append(("\U0001F9CA Ice Cold", bs.pick("lose_streak").format(team=coldest[0], n=abs(coldest[1]))))

    # Bench mismanagement, if bench_points was supplied (e.g. from
    # season_stats.bench_points_left_on_table for just this week)
    if bench_points:
        worst_team, worst_points = max(bench_points.items(), key=lambda kv: kv[1])
        if worst_points > 15:
            awards.append(("\U0001FA91 Bench Tax", bs.pick("bench_tax").format(team=worst_team, points=round(worst_points, 1))))

    if banter_state is None:
        bs.save()
    return awards


def format_awards_message(week: int, awards: List[tuple]) -> str:
    lines = [f"\U0001F3C6 WEEK {week} AWARDS \U0001F3C6"]
    for title, line in awards:
        lines.append(f"{title}: {line}")
    return "\n".join(lines)


def generate_faab_awards(report, banter_state: Optional[BanterState] = None) -> List[tuple]:
    """report: a faab_report.FaabReport."""
    bs = banter_state or BanterState()
    awards = []

    for b in report.budgets:
        if b.is_big_spender:
            pct = round(100 * b.biggest_bid_this_week / b.remaining_before_this_week)
            # find the player they spent big on
            claim = next((c for c in report.claims if c.winning_team == b.team and c.paid == b.biggest_bid_this_week), None)
            player = claim.player if claim else "someone"
            awards.append(("\U0001F911 Big Spender", bs.pick("big_spender").format(
                team=b.team, paid=b.biggest_bid_this_week, pct=pct, player=player)))

    if report.claims:
        biggest_overpay = report.claims[0]  # already sorted desc by overpaid
        if biggest_overpay.overpaid > 0 and biggest_overpay.bidders > 1:
            awards.append(("\U0001F4B8 Overpaid", bs.pick("faab_overpaid").format(
                team=biggest_overpay.winning_team, player=biggest_overpay.player, overpaid=biggest_overpay.overpaid, paid=biggest_overpay.paid)))

        contested = [c for c in report.claims if c.bidders > 1]
        if contested:
            bargain = min(contested, key=lambda c: c.paid)
            awards.append(("\U0001F48E Bargain Bin", bs.pick("faab_bargain").format(
                team=bargain.winning_team, player=bargain.player, paid=bargain.paid, bidders=bargain.bidders)))

            most_wanted = max(contested, key=lambda c: c.bidders)
            awards.append(("\U0001F440 Most Wanted", bs.pick("faab_contested").format(
                player=most_wanted.player, bidders=most_wanted.bidders)))

    if banter_state is None:
        bs.save()
    return awards


def generate_prediction_banter(predictions: List, banter_state: Optional[BanterState] = None) -> List[tuple]:
    """predictions: list of weekly_prediction.MatchupPrediction."""
    bs = banter_state or BanterState()
    awards = []
    if not predictions:
        return awards

    locks = [p for p in predictions if p.confidence == "Lock"]
    if locks:
        biggest = max(locks, key=lambda p: max(p.home_win_pct, p.away_win_pct))
        fav, dog, pct = (
            (biggest.home_team, biggest.away_team, biggest.home_win_pct)
            if biggest.home_win_pct > biggest.away_win_pct
            else (biggest.away_team, biggest.home_team, biggest.away_win_pct)
        )
        awards.append(("\U0001F512 Lock of the Week", bs.pick("lock_of_week").format(favorite=fav, underdog=dog, pct=pct)))

    toss_ups = [p for p in predictions if p.confidence == "Toss-Up"]
    if toss_ups:
        closest = min(toss_ups, key=lambda p: abs(p.home_win_pct - p.away_win_pct))
        awards.append(("\U0001FA99 Coin Flip", bs.pick("toss_up").format(
            home=closest.home_team, away=closest.away_team, pct=closest.home_win_pct, pct2=closest.away_win_pct)))

    if banter_state is None:
        bs.save()
    return awards
