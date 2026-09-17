#!/usr/bin/env python3
"""
SUNDAY run: "Close Enough for Now" -- the weekly matchup predictor. Meant
to run once rosters are about as locked as they're going to get. The user's
call: ~noon ET on Sunday, right before the bulk of the day's games kick off.
Anything that already played (Thursday night, early London games) is locked
in regardless by that point, which is fine -- the name is honest about what
this is: the closest read we can get, not a claim of certainty.

Unlike tuesday_recap.py's season-long playoff simulator (team-level,
historical averages), this looks at just the CURRENT week and scores it
player-by-player using each starter's real NFL matchup (see
player_projection.py) -- a lineup facing a rough set of real-life matchups
gets pulled down, a lineup catching a soft set gets bumped up, individually
per player rather than as one team-level blob.

Also logs each week's picks (whichever team had the higher win probability,
Toss-Ups included) to a "Skip's Predictions" sheet tab, and grades last
week's picks against the actual results once they're in -- that running
W-L record is what shows up at the top of the predictions image.

Usage:
  python sunday_predictions.py                # auto-detects current week
  python sunday_predictions.py --week 5        # force a specific week
  python sunday_predictions.py --no-groupme    # print only, skip GroupMe
  python sunday_predictions.py --no-sheet      # skip grading/logging picks
"""
import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fantasy_football import config, espn_client, weekly_prediction, banter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--no-groupme", action="store_true")
    parser.add_argument("--no-sheet", action="store_true")
    parser.add_argument("--sim-trials", type=int, default=20000)
    args = parser.parse_args()

    league = espn_client.connect()
    week = args.week or espn_client.get_current_week(league)

    # We want stdev from *completed* weeks only, so pull team history
    # through the week before this one.
    through_week = week - 1 if week > 1 else 1
    team_seasons = espn_client.get_all_team_seasons(league, through_week=through_week)

    predictions = weekly_prediction.predict_week(league, week, team_seasons, n_trials=args.sim_trials)

    print(f"=== CLOSE ENOUGH FOR NOW: WEEK {week} PREDICTIONS ===")
    for p in predictions:
        print(f"{p.home_team} ({p.home_projected}, {p.home_win_pct}%) vs "
              f"{p.away_team} ({p.away_projected}, {p.away_win_pct}%)  [{p.confidence}]")

    banter_lines = banter.generate_prediction_banter(predictions)
    if banter_lines:
        print("\n=== BANTER ===")
        for title, line in banter_lines:
            print(f"{title}: {line}")

    record = None
    if not args.no_sheet and config.GOOGLE_SHEET_ID:
        from fantasy_football import prediction_record, sheets_writer
        sh = sheets_writer.client().open_by_key(config.GOOGLE_SHEET_ID)
        last_completed_week = week - 1
        record = prediction_record.grade_pending(sh, league, last_completed_week) if last_completed_week >= 1 else (0, 0)
        prediction_record.record_predictions(sh, predictions)
        print(f"\n{config.BOT_NAME}'s record through Week {last_completed_week}: {record[0]}-{record[1]}")

    if not args.no_groupme and config.GROUPME_BOT_ID:
        from fantasy_football import groupme_bot
        if config.GROUPME_ACCESS_TOKEN:
            from fantasy_football import predictions_image
            img_path = predictions_image.render_predictions(week, predictions, "predictions.png", record=record)
            groupme_bot.post_predictions_image(week, img_path, banter_lines)
        else:
            # Falls back to the plain-text table if no personal access token
            # is set up yet -- see SETUP.md to enable the image post.
            groupme_bot.post_predictions(week, predictions, banter_lines)
        print("\nPosted to GroupMe.")


if __name__ == "__main__":
    sys.exit(main())
