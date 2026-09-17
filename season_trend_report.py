#!/usr/bin/env python3
"""
Builds the season-long "power ranking trend" chart for the end-of-year
presentation -- a small-multiple grid, one mini rank-by-week line per team,
so a team's climb or slide across the season is obvious at a glance. See
fantasy_football/season_trend_chart.py for the design reasoning.

This is a standalone, on-demand script (not part of the Tuesday/Wednesday/
Sunday weekly cadence) -- run it whenever you want an updated season-shape
chart, most usefully right before building the year-end deck.

Usage:
  python season_trend_report.py                  # through the most recently completed week
  python season_trend_report.py --through-week 8  # force a cutoff
  python season_trend_report.py --with-roster-strength  # slower, more exact per-week match to the live weekly rankings
"""
import argparse
import sys

from fantasy_football import espn_client, season_trend_chart


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--through-week", type=int, default=None)
    parser.add_argument("--with-roster-strength", action="store_true")
    parser.add_argument("--out", default="season_trend.png")
    args = parser.parse_args()

    league = espn_client.connect()
    through_week = args.through_week or (espn_client.get_current_week(league) - 1)
    through_week = max(through_week, 1)

    print(f"Computing weekly power rankings for weeks 1-{through_week}...")
    weekly_ranks = season_trend_chart.compute_weekly_ranks(
        league, through_week=through_week, include_roster_strength=args.with_roster_strength
    )
    team_names = {t.team_id: t.team_name for t in league.teams}

    out_path = season_trend_chart.render_season_trend(weekly_ranks, team_names, args.out)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    sys.exit(main())
