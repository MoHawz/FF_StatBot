"""
Renders the Sunday "Close Enough for Now" matchup predictions as a single
PNG graphic, matching rankings_image.py / faab_image.py. Same motivation:
one glanceable card instead of a truncated GroupMe text wall. Requires
GROUPME_ACCESS_TOKEN (see SETUP.md); groupme_bot.post_predictions_image()
handles the upload.

The accompanying banter lines stay as a separate plain-text GroupMe
message, same as today -- only the matchup table itself becomes an image.
"""
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from . import config
from .weekly_prediction import MatchupPrediction

WIDTH = 900
HEADER_HEIGHT = 130
ROW_HEIGHT = 110
FOOTER_HEIGHT = 40
PADDING = 24

COLOR_BG = (18, 28, 43)
COLOR_HEADER = (31, 58, 95)
COLOR_ROW_A = (26, 40, 61)
COLOR_ROW_B = (32, 48, 72)
COLOR_TEXT = (240, 240, 240)
COLOR_SUBTEXT = (160, 172, 190)
COLOR_ACCENT = (222, 178, 58)      # gold, "Lock"
COLOR_FAVORED = (90, 140, 210)     # blue, "Favored"
COLOR_TOSSUP = (160, 172, 190)     # grey, "Toss-Up"
COLOR_WINNER = (86, 200, 120)
COLOR_BAR_BG = (52, 68, 94)

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(f"{FONT_DIR}{name}", size)
    except OSError:
        return ImageFont.load_default()


F_TITLE = _font("DejaVuSans-Bold.ttf", 33)
F_SUB = _font("DejaVuSans.ttf", 20)
F_TEAM = _font("DejaVuSans-Bold.ttf", 24)
F_PROJ = _font("DejaVuSans.ttf", 18)
F_PCT = _font("DejaVuSans-Bold.ttf", 22)
F_VS = _font("DejaVuSans.ttf", 16)
F_TAG = _font("DejaVuSans-Bold.ttf", 16)
F_DETAIL = _font("DejaVuSans.ttf", 17)

_TAG_COLOR = {"Lock": COLOR_ACCENT, "Favored": COLOR_FAVORED, "Toss-Up": COLOR_TOSSUP}
# DejaVu Sans has no emoji glyphs (they rendered as tofu boxes), so the
# confidence tag is plain text + color only, same idea as the movement
# arrows on the power-rankings image.


def render_predictions(week: int, predictions: List[MatchupPrediction], out_path: str,
                        subtitle: Optional[str] = None) -> str:
    height = HEADER_HEIGHT + ROW_HEIGHT * max(1, len(predictions)) + FOOTER_HEIGHT
    img = Image.new("RGB", (WIDTH, height), COLOR_BG)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, WIDTH, HEADER_HEIGHT], fill=COLOR_HEADER)
    draw.text((PADDING, 26), "CLOSE ENOUGH FOR NOW", font=F_TITLE, fill=COLOR_TEXT)
    draw.text((PADDING, 68), f"Week {week} Predictions  •  {subtitle or config.LEAGUE_DISPLAY_NAME}",
               font=F_SUB, fill=COLOR_SUBTEXT)

    if not predictions:
        draw.text((PADDING, HEADER_HEIGHT + 20), "No matchups found for this week.",
                   font=F_DETAIL, fill=COLOR_SUBTEXT)
        img.save(out_path, "PNG")
        return out_path

    for i, p in enumerate(predictions):
        y0 = HEADER_HEIGHT + i * ROW_HEIGHT
        draw.rectangle([0, y0, WIDTH, y0 + ROW_HEIGHT], fill=(COLOR_ROW_A if i % 2 == 0 else COLOR_ROW_B))

        home_winner = p.home_win_pct >= p.away_win_pct
        home_color = COLOR_WINNER if home_winner else COLOR_TEXT
        away_color = COLOR_TEXT if home_winner else COLOR_WINNER

        # home (left)
        draw.text((PADDING, y0 + 14), p.home_team, font=F_TEAM, fill=home_color)
        draw.text((PADDING, y0 + 44), f"{p.home_projected} pts", font=F_PROJ, fill=COLOR_SUBTEXT)
        hp_text = f"{p.home_win_pct}%"
        draw.text((PADDING, y0 + 70), hp_text, font=F_PCT, fill=home_color)

        # "vs" + confidence tag, centered
        vs_x = WIDTH // 2
        vtw = draw.textlength("vs", font=F_VS)
        draw.text((vs_x - vtw / 2, y0 + 20), "vs", font=F_VS, fill=COLOR_SUBTEXT)
        tag_color = _TAG_COLOR.get(p.confidence, COLOR_SUBTEXT)
        tag_text = p.confidence.upper()
        ttw = draw.textlength(tag_text, font=F_TAG)
        draw.text((vs_x - ttw / 2, y0 + 50), tag_text, font=F_TAG, fill=tag_color)

        # win-probability bar, centered under the tag
        bar_w, bar_h = 160, 8
        bar_x0, bar_y = vs_x - bar_w // 2, y0 + 82
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + bar_w, bar_y + bar_h], radius=4, fill=COLOR_BAR_BG)
        fill_w = max(4, int(bar_w * (p.home_win_pct / 100)))
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + fill_w, bar_y + bar_h], radius=4,
                                 fill=(COLOR_WINNER if home_winner else (140, 100, 100)))

        # away (right), right-aligned
        right_edge = WIDTH - PADDING
        atw = draw.textlength(p.away_team, font=F_TEAM)
        draw.text((right_edge - atw, y0 + 14), p.away_team, font=F_TEAM, fill=away_color)
        proj_text = f"{p.away_projected} pts"
        ptw = draw.textlength(proj_text, font=F_PROJ)
        draw.text((right_edge - ptw, y0 + 44), proj_text, font=F_PROJ, fill=COLOR_SUBTEXT)
        ap_text = f"{p.away_win_pct}%"
        aptw = draw.textlength(ap_text, font=F_PCT)
        draw.text((right_edge - aptw, y0 + 70), ap_text, font=F_PCT, fill=away_color)

    draw.text((PADDING, height - FOOTER_HEIGHT + 8), f"{config.BOT_NAME}'s Predictions",
               font=F_DETAIL, fill=COLOR_SUBTEXT)

    img.save(out_path, "PNG")
    return out_path
