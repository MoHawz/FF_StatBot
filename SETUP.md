# Setup

Three things need to be collected once, then the automation runs on its own.

## 1. ESPN league access (`ESPN_S2` / `ESPN_SWID`)

Only needed if your league is private (most are). Skip this if ESPN lets you
view the league without logging in.

1. In a web browser (signed in to ESPN Fantasy), go to your league.
2. Open developer tools: `F12` (Windows) or `Cmd+Option+I` (Mac).
3. Go to the **Application** tab (Chrome) or **Storage** tab (Firefox) → **Cookies** → `https://fantasy.espn.com`.
4. Find the row named `espn_s2` — copy its **Value** (a very long string).
5. Find the row named `SWID` — copy its **Value** (looks like `{ABCD1234-...}`, including the curly braces).
6. Put both into your `.env` file as `ESPN_S2=...` and `ESPN_SWID=...`.

These don't expire quickly, but if the scripts suddenly start failing to
authenticate, re-grab them the same way.

## 2. GroupMe bot (`GROUPME_BOT_ID`)

1. Go to https://dev.groupme.com/bots and log in with the GroupMe account
   that's in your league's group.
2. Click **Create Bot**.
3. Pick the group you want it to post in.
4. Give it a name (e.g. "Power Rankings Bot") and optionally an avatar URL.
5. Click **Submit**, then copy the **Bot ID** it shows you.
6. Put it in `.env` as `GROUPME_BOT_ID=...`.

That's it — no further approval needed, the bot can post immediately.

### Optional: posting the power rankings as an image (`GROUPME_ACCESS_TOKEN`)

By default the power rankings post as plain text, which GroupMe collapses
behind a "Read more..." tap once it gets long — annoying to read on a
phone. To post it as one glanceable graphic instead, GroupMe requires
uploading through its Image Service, which needs a **personal** access
token (bots can't upload images themselves, only post them once they
already have a groupme.com URL):

1. Go to https://dev.groupme.com and log in with the GroupMe account
   that's in your league's group (this can be the same account used for
   the bot above, or any member's).
2. Your **Access Token** is shown right on that page after logging in
   (top right, or under "Access Token").
3. Put it in `.env` as `GROUPME_ACCESS_TOKEN=...`. Treat it like a
   password — it's tied to your personal GroupMe account, not just this
   bot.

With this set, all three scripts automatically post their tables as images
instead of text -- `tuesday_recap.py` (power rankings), `wednesday_faab.py`
(FAAB report), and `sunday_predictions.py` ("Close Enough for Now"
predictions). Without it, everything still works, it just falls back to
the plain-text versions. Either way, the banter/awards lines always post as
their own follow-up text message in the same run, unchanged.

## 3. Google Sheet (`GOOGLE_SERVICE_ACCOUNT_JSON` / `GOOGLE_SHEET_ID`)

1. Go to https://console.cloud.google.com/ and create a project (or use an
   existing one).
2. Enable the **Google Sheets API** and **Google Drive API** for that project
   (APIs & Services → Library → search each → Enable).
3. Go to **APIs & Services → Credentials → Create Credentials → Service account**.
   Give it any name (e.g. "ff-power-rankings"), skip the optional role/access
   steps, and click Done.
4. Click into the new service account → **Keys** tab → **Add Key → Create new
   key → JSON**. This downloads a `.json` file — save it as
   `service_account.json` next to this script (or anywhere; just point
   `GOOGLE_SERVICE_ACCOUNT_JSON` at its path). **Keep this file private** —
   it's a credential.
5. Open the JSON file and copy the `client_email` value (looks like
   `ff-power-rankings@your-project.iam.gserviceaccount.com`).
6. Create (or open) the Google Sheet you want rankings written to, click
   **Share**, and share it with that `client_email` address as an **Editor**.
7. Copy the Sheet's ID from its URL:
   `https://docs.google.com/spreadsheets/d/`**`THIS_PART_IS_THE_ID`**`/edit`
8. Put it in `.env` as `GOOGLE_SHEET_ID=...`.

## Optional: personalizing the image cards (`LEAGUE_DISPLAY_NAME` / `BOT_NAME`)

The rendered image cards (power rankings, FAAB report, predictions) show a
subtitle and a footer caption. By default these are generic placeholders
("Fantasy League" / "Stat Bot") so the code itself never names your actual
league or bot -- handy if you keep this repo public. To personalize them,
add to `.env`:

```
LEAGUE_DISPLAY_NAME=Your League Name
BOT_NAME=Your Bot's Name
```

Purely cosmetic -- nothing else depends on these.

## Optional: your league logo (`LOGO_PATH`)

If you have a logo/crest image, point `LOGO_PATH` in `.env` at it (an
absolute path, or one relative to wherever you run the scripts from):

```
LOGO_PATH=./assets/logo.png
```

The image itself is never committed -- only the path -- so put it wherever
you like on your machine; a good spot is an `assets/` folder next to this
script (already gitignored). Works best as a badge/crest-style image, PNG,
on a plain white or transparent background -- a wide logo will get
letterboxed down to fit the small badge size these cards use.

When set, every rendered card (power rankings, FAAB report, predictions,
and the season trend chart) shows a small crisp version of it in the
header corner, plus a large, very faint version of it as a background
watermark. Leave it unset and everything renders exactly as before, just
without a logo.

The color scheme on all four -- maroon header, black background, white
text -- is Mississippi State's official brand maroon (`#5D1725`). To use
different colors, edit the constants at the top of `fantasy_football/branding.py`.

## Keeping the banter fresh (`banter_state.json`)

The trash-talk lines (awards, FAAB call-outs, prediction banter) rotate
through ~6-10 phrasing variants per category instead of a fixed one-liner,
so a 17-week season doesn't repeat itself. A small `banter_state.json` file
gets created next to the scripts the first time they run -- it just tracks
which variants have already been used per category so nothing repeats until
the whole set has been shown once, and it never hands back the same line
two weeks in a row. It's regenerated automatically and gitignored; delete
it any time to reset the rotation, or leave it alone and it'll keep
tracking itself all season.

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env    # then fill in .env with the values above
```

There are three separate weekly scripts, matching the league's actual
weekly rhythm -- run each manually any time, or have them scheduled:

```bash
python tuesday_recap.py       # Tue AM, after MNF + ESPN's stat corrections:
                               #   power rankings + banter awards for the week that just ended
python wednesday_faab.py      # Wed AM, after waivers process:
                               #   who won what, overpaid/bargain calls, Big Spender flags
python sunday_predictions.py  # Sun ~noon ET, once rosters are close to locked:
                               #   "Close Enough for Now" matchup predictions for THIS week,
                               #   using each starter's real NFL matchup, not last week's fantasy opponent
```

Each accepts `--week N` to force a specific week and `--no-groupme` to
print without posting. Once your credentials are in place, tell Claude and
it can set these up to run automatically on that schedule and post straight
to GroupMe without you doing anything.
