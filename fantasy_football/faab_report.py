"""
Wednesday FAAB report -- replaces the manual copy-paste-from-ESPN-emails
spreadsheet the user used to keep. Pulls the week's waiver transactions
straight from the API: who won each contested player, what they paid, how
that compares to the next-highest bid, how many teams bid, and who blew a
big chunk of their remaining budget on one claim ("Big Spender": a single
winning bid that's at least BIG_SPENDER_PCT of what the team had left
going into that week -- default 40%, per the user's call).
"""
from dataclasses import dataclass, field
from typing import Dict, List

BIG_SPENDER_PCT = 0.40


@dataclass
class ClaimResult:
    player: str
    winning_team: str
    paid: int
    next_highest_bid: int
    overpaid: int          # paid minus next-highest competing bid (or full paid if uncontested)
    bidders: int


@dataclass
class TeamBudgetStatus:
    team: str
    spent_this_week: int
    remaining_budget: int         # as of now (after this week's processing)
    remaining_before_this_week: int
    is_big_spender: bool           # made a single winning bid >= BIG_SPENDER_PCT of remaining-before
    biggest_bid_this_week: int


@dataclass
class FaabReport:
    week: int
    claims: List[ClaimResult]
    budgets: List[TeamBudgetStatus]


def compute_faab_report(league, week: int) -> FaabReport:
    txns = league.transactions(scoring_period=week, types={"WAIVER", "WAIVER_ERROR"})

    # group all bids (won or lost) by the player they were trying to ADD
    by_player: Dict[str, list] = {}
    spent_this_week: Dict[str, int] = {t.team_name: 0 for t in league.teams}
    biggest_bid: Dict[str, int] = {t.team_name: 0 for t in league.teams}

    for t in txns:
        add_names = [i.player for i in t.items if getattr(i, "type", "") == "ADD"]
        if not add_names:
            continue
        team_name = t.team.team_name
        bid = t.bid_amount or 0
        for player in add_names:
            by_player.setdefault(player, []).append({"team": team_name, "bid": bid, "status": t.status})
        if t.status == "EXECUTED" and bid > 0:
            spent_this_week[team_name] = spent_this_week.get(team_name, 0) + bid
            biggest_bid[team_name] = max(biggest_bid.get(team_name, 0), bid)

    claims = []
    for player, bids in by_player.items():
        winner = next((b for b in bids if b["status"] == "EXECUTED"), None)
        if not winner or winner["bid"] <= 0:
            continue  # free/uncontested pickup with no FAAB spent -- not interesting for this report
        others = [b["bid"] for b in bids if b is not winner]
        next_highest = max(others) if others else 0
        overpaid = (winner["bid"] - next_highest) if next_highest else winner["bid"]
        claims.append(
            ClaimResult(
                player=player,
                winning_team=winner["team"],
                paid=winner["bid"],
                next_highest_bid=next_highest,
                overpaid=overpaid,
                bidders=len(bids),
            )
        )
    claims.sort(key=lambda c: c.overpaid, reverse=True)

    budgets = []
    for team in league.teams:
        remaining_now = league.settings.acquisition_budget - team.acquisition_budget_spent
        remaining_before = remaining_now + spent_this_week.get(team.team_name, 0)
        big_bid = biggest_bid.get(team.team_name, 0)
        is_big_spender = remaining_before > 0 and (big_bid / remaining_before) >= BIG_SPENDER_PCT
        budgets.append(
            TeamBudgetStatus(
                team=team.team_name,
                spent_this_week=spent_this_week.get(team.team_name, 0),
                remaining_budget=remaining_now,
                remaining_before_this_week=remaining_before,
                is_big_spender=is_big_spender,
                biggest_bid_this_week=big_bid,
            )
        )
    budgets.sort(key=lambda b: b.remaining_budget)

    return FaabReport(week=week, claims=claims, budgets=budgets)


def format_faab_table(report: FaabReport) -> str:
    lines = [f"\U0001F4B0 WEEK {report.week} FAAB REPORT \U0001F4B0"]
    if not report.claims:
        lines.append("No contested waiver claims this week.")
    for c in report.claims:
        lines.append(f"{c.player}: {c.winning_team} won at ${c.paid} ({c.bidders} bidders, beat next bid by ${c.overpaid})")
    lines.append("")
    lines.append("Budgets remaining:")
    for b in report.budgets:
        tag = " \U0001F911 BIG SPENDER" if b.is_big_spender else ""
        lines.append(f"{b.team}: ${b.remaining_budget} left{tag}")
    return "\n".join(lines)
