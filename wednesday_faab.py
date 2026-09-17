#!/usr/bin/env python3
"""
WEDNESDAY run: the FAAB waiver report. Meant to run after your league's
waiver process has finished (ESPN typically processes waivers Wednesday
early morning). Looks at just-processed transactions for the given week:
who won each contested player, what they paid vs. the next-highest bid, how
many teams bid, and flags a "Big Spender" -- a single winning bid that ate
up 40%+ (BIG_SPENDER_PCT in faab_report.py) of what a team had left going
into that week.

Usage:
  python wednesday_faab.py                # auto-detects current week
  python wednesday_faab.py --week 5        # force a specific week
  python wednesday_faab.py --no-groupme    # print only, skip GroupMe
"""
import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fantasy_football import config, espn_client, faab_report, banter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--no-groupme", action="store_true")
    args = parser.parse_args()

    league = espn_client.connect()
    week = args.week or espn_client.get_current_week(league)
    # Waivers process overnight into Wednesday for the week that's *in
    # progress* (not the prior week) -- e.g. Wednesday of week 5 processes
    # week 5's waiver claims (players added ahead of week 5's games).
    report = faab_report.compute_faab_report(league, week)

    print(faab_report.format_faab_table(report))

    awards = banter.generate_faab_awards(report)
    if awards:
        print("\n=== FAAB AWARDS ===")
        for title, line in awards:
            print(f"{title}: {line}")

    if not args.no_groupme and config.GROUPME_BOT_ID:
        from fantasy_football import groupme_bot
        if config.GROUPME_ACCESS_TOKEN:
            from fantasy_football import faab_image
            img_path = faab_image.render_faab_report(week, report, "faab_report.png")
            groupme_bot.post_faab_report_image(week, img_path, awards)
        else:
            # Falls back to the plain-text table if no personal access token
            # is set up yet -- see SETUP.md to enable the image post.
            groupme_bot.post_faab_report(report, awards)
        print("\nPosted to GroupMe.")


if __name__ == "__main__":
    sys.exit(main())
