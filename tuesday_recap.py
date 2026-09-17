#!/usr/bin/env python3
"""
TUESDAY run: the week-in-review. Meant to run after Monday Night Football
has finished and ESPN's own stat corrections have settled (Tuesday morning
is the safe bet) -- i.e. this looks *backward* at the week that just ended.

This is one of three separate weekly entrypoints:
  - tuesday_recap.py     (this file) -- recap + power rankings + banter awards
  - wednesday_faab.py    -- FAAB waiver report, after Wednesday's waiver run
  - sunday_predictions.py -- "Close Enough for Now" matchup predictions,
                             meant to run once rosters are effectively locked
                             (the user's call: ~noon ET Sunday)

What this one does:
  1. Connects to your ESPN league
  2. Pulls this season's data through the most recently completed week
  3. Computes power rankings
  4. Writes them to your Google Sheet (if configured)
  5. Posts the rankings table AND the week's banter/awards to GroupMe in the
     same run (if configured) -- these always go out together, not as
     separate messages
  6. Runs the season-long Monte Carlo playoff simulator and prints/optionally
     posts odds (a rougher, team-level "how's the playoff picture trending"
     view -- the precise, real-NFL-matchup-based prediction for THIS week
     specifically is sunday_predictions.py's job, not this script's)

Configuration is via environment variables -- see SETUP.md.

Usage:
  python tuesday_recap.py                  # auto-detects current week
  python tuesday_recap.py --week 5         # force a specific week
  python tuesday_recap.py --no-groupme     # compute + write sheet, skip GroupMe
  python tuesday_recap.py --no-sheet       # compute only, skip Google Sheets
  python tuesday_recap.py --sim-only       # just print playoff odds
"""
import argparse
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fantasy_football import config, espn_client, power_rankings, playoff_sim, roster_strength


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--no-groupme", action="store_true")
    parser.add_argument("--no-sheet", action="store_true")
    parser.add_argument("--sim-only", action="store_true")
    parser.add_argument("--sim-trials", type=int, default=10000)
    parser.add_argument("--prev-ranks-file", default="prev_ranks.json",
                         help="local cache of last week's ranks, used for movement arrows")
    args = parser.parse_args()

    league = espn_client.connect()
    week = args.week or espn_client.get_current_week(league)
    # ESPN's "current_week" points at the upcoming week once games are live;
    # for a wrap-up we usually want the most recently *completed* week.
    through_week = week - 1 if week > 1 else 1

    print(f"Pulling league data through week {through_week}...")
    team_seasons = espn_client.get_all_team_seasons(league, through_week=through_week)

    if not args.sim_only:
        try:
            with open(args.prev_ranks_file) as f:
                previous_ranks = {int(k): v for k, v in json.load(f).items()}
        except FileNotFoundError:
            previous_ranks = {}

        roster_scores = None
        try:
            rs_rows = roster_strength.compute_roster_strength(league, week)
            roster_scores = roster_strength.as_score_dict(rs_rows)
        except Exception as e:
            print(f"(roster strength unavailable this week: {e})")

        rows = power_rankings.compute_power_rankings(
            team_seasons, previous_ranks=previous_ranks, roster_strength_scores=roster_scores
        )

        print("\n=== POWER RANKINGS ===")
        for r in rows:
            print(f"{r.rank:>2}. {r.team_name:<20} {r.power_score:>5}  ({r.wins}-{r.losses}-{r.ties})")

        with open(args.prev_ranks_file, "w") as f:
            json.dump({r.team_id: r.rank for r in rows}, f)

        if not args.no_sheet and config.GOOGLE_SHEET_ID:
            from fantasy_football import sheets_writer
            url = sheets_writer.write_weekly_power_rankings(through_week, rows)
            print(f"\nWrote to Google Sheet: {url}")

        from fantasy_football import banter
        bench_pts = None
        try:
            from fantasy_football.season_stats import bench_points_left_on_table
            bench_pts = {
                r["team"]: r["bench_points_left"]
                for r in bench_points_left_on_table(league, range(through_week, through_week + 1))
            }
        except Exception as e:
            print(f"(bench points unavailable this week: {e})")

        awards = banter.generate_weekly_awards(through_week, rows, team_seasons, bench_points=bench_pts)
        print("\n=== WEEK AWARDS ===")
        for title, line in awards:
            print(f"{title}: {line}")

        if not args.no_groupme and config.GROUPME_BOT_ID:
            from fantasy_football import groupme_bot, rankings_image, movement_reasons
            if config.GROUPME_ACCESS_TOKEN:
                reasons = None
                try:
                    reasons = movement_reasons.compute_movement_reasons(rows, team_seasons, league, through_week)
                except Exception as e:
                    print(f"(movement reasons unavailable this week: {e})")
                img_path = rankings_image.render_power_rankings(through_week, rows, "power_rankings.png", reasons=reasons)
                groupme_bot.post_power_rankings_image(through_week, img_path)
            else:
                # Falls back to the plain-text table if no personal access
                # token is set up yet -- see SETUP.md to enable the image post.
                groupme_bot.post_power_rankings(through_week, rows)
            groupme_bot.post_awards(through_week, awards)
            print("\nPosted to GroupMe.")

    # --- Playoff odds ---
    print("\n=== PLAYOFF ODDS (Monte Carlo) ===")
    sim_teams = {
        ts.team_id: playoff_sim.SimTeam(
            team_id=ts.team_id,
            name=ts.team_name,
            scores_so_far=[w.score for w in ts.weeks],
            wins=ts.wins,
            losses=ts.losses,
            ties=ts.ties,
            points_allowed_so_far=[w.opponent_score for w in ts.weeks if w.opponent_score is not None],
        )
        for ts in team_seasons
    }
    remaining_schedule = playoff_sim.build_remaining_schedule_from_espn(league, through_week)
    playoff_team_count = getattr(league.settings, "playoff_team_count", 6)

    if not remaining_schedule:
        print("(Regular season is over -- run this against the live playoff bracket instead.)")
    else:
        next_week_means = None
        try:
            next_week_means = roster_strength.as_score_dict(
                roster_strength.compute_roster_strength(league, week)
            )
        except Exception as e:
            print(f"(next-week projections unavailable, falling back to season avg: {e})")

        results = playoff_sim.run_simulation(
            sim_teams, remaining_schedule, playoff_team_count=playoff_team_count,
            n_trials=args.sim_trials, next_week_projected_means=next_week_means,
        )
        for r in results:
            print(f"{r.name:<20} playoffs {r.made_playoffs_pct:>5}%   champ {r.champion_pct:>5}%")


if __name__ == "__main__":
    sys.exit(main())
