"""
Renders the weekly power rankings as a single PNG graphic instead of a wall
of text. GroupMe collapses long text messages behind a "Read more..." tap,
which is exactly the readability complaint this solves -- an image posts as
one glanceable card with no truncation, closer to the old screenshot-a-
spreadsheet habit but built fresh from the live data every week.

Posting it as an actual inline image in GroupMe (not just a link) requires
uploading through GroupMe's own Image Service, which needs a personal
access token (not the bot_id) -- see SETUP.md for the two-minute steps to
grab one. groupme_bot.post_power_rankings_image() handles the upload +
posting once that token is in `.env`.

Colors and the optional logo come from branding.py / config.LOGO_PATH --
see those for the full reasoning.
"""
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

from . import branding, config
from .power_rankings import PowerRankingRow

WIDTH = 900
ROW_HEIGHT = 92
REASON_EXTRA_HEIGHT = 24   # extra vertical space a row gets when it has a "why" line
HEADER_HEIGHT = 130
FOOTER_HEIGHT = 40
PADDING = 24

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(f"{FONT_DIR}{name}", size)
    except OSError:
        return ImageFont.load_default()


F_TITLE = _font("DejaVuSans-Bold.ttf", 36)
F_SUB = _font("DejaVuSans.ttf", 20)
F_RANK = _font("DejaVuSans-Bold.ttf", 30)
F_TEAM = _font("DejaVuSans-Bold.ttf", 26)
F_OWNER = _font("DejaVuSans.ttf", 18)
F_SCORE = _font("DejaVuSans-Bold.ttf", 30)
F_DETAIL = _font("DejaVuSans.ttf", 17)
F_ARROW = _font("DejaVuSans-Bold.ttf", 18)
F_REASON = _font("DejaVuSans.ttf", 16)


def _movement_text(movement: int):
    if movement > 0:
        return f"▲ {movement}", branding.STATUS_GOOD
    if movement < 0:
        return f"▼ {abs(movement)}", branding.STATUS_BAD
    return "—", branding.STATUS_NEUTRAL


def render_power_rankings(
    week: int,
    rows: List[PowerRankingRow],
    out_path: str,
    subtitle: Optional[str] = None,
    reasons: Optional[Dict[int, str]] = None,
) -> str:
    """
    reasons: optional {team_id: "why" text}, e.g. from
    movement_reasons.compute_movement_reasons() -- a short factual line
    ("Lost 3 straight", "Lost Player X (IR)") shown under a mover's record
    line. Teams not in the dict (including any team with movement == 0)
    just get the normal two-line layout -- silence is intentional, not
    every row needs an explanation.
    """
    reasons = reasons or {}

    row_heights = [ROW_HEIGHT + (REASON_EXTRA_HEIGHT if r.team_id in reasons else 0) for r in rows]
    height = HEADER_HEIGHT + sum(row_heights) + FOOTER_HEIGHT
    img = Image.new("RGBA", (WIDTH, height), branding.BLACK + (255,))
    draw = ImageDraw.Draw(img)

    logo = branding.load_logo()

    # header
    draw.rectangle([0, 0, WIDTH, HEADER_HEIGHT], fill=branding.MAROON)
    if logo:
        branding.paste_watermark(img, logo, box=(WIDTH - 340, 0, WIDTH, HEADER_HEIGHT), opacity=0.16)
    draw.text((PADDING, 30), f"WEEK {week} POWER RANKINGS", font=F_TITLE, fill=branding.WHITE)
    draw.text((PADDING, 82), subtitle or config.LEAGUE_DISPLAY_NAME, font=F_SUB, fill=branding.WHITE)
    if logo:
        branding.paste_badge(img, logo, size=76, margin=16)

    max_score = max((r.power_score for r in rows), default=1) or 1

    y_cursor = HEADER_HEIGHT
    for i, r in enumerate(rows):
        row_h = row_heights[i]
        y0 = y_cursor
        y1 = y0 + row_h
        y_cursor = y1
        draw.rectangle([0, y0, WIDTH, y1], fill=(branding.ROW_A if i % 2 == 0 else branding.ROW_B))

        # rank circle, vertically centered on this row (taller when a reason is shown)
        cx, cy, r_rad = 56, y0 + row_h // 2, 30
        circle_color = branding.WHITE if r.rank == 1 else branding.MAROON
        draw.ellipse([cx - r_rad, cy - r_rad, cx + r_rad, cy + r_rad], fill=circle_color)
        rank_text = str(r.rank)
        tw = draw.textlength(rank_text, font=F_RANK)
        draw.text((cx - tw / 2, cy - 18), rank_text, font=F_RANK, fill=branding.MAROON if r.rank == 1 else branding.WHITE)

        # team + owner
        tx = 104
        draw.text((tx, y0 + 16), r.team_name, font=F_TEAM, fill=branding.WHITE)
        draw.text((tx, y0 + 50), f"{r.owner}  •  {r.wins}-{r.losses}{'-' + str(r.ties) if r.ties else ''}  •  {r.ppg} ppg",
                   font=F_OWNER, fill=branding.GRAY_SUBTEXT)

        reason = reasons.get(r.team_id)
        if reason:
            reason_color = branding.STATUS_GOOD if r.movement > 0 else branding.STATUS_BAD
            draw.text((tx, y0 + 72), reason, font=F_REASON, fill=reason_color)

        # power score bar (visual, quick scan of "how far ahead"), pinned
        # near the bottom of the row so it still lines up under the text
        # whether or not this row has the extra reason line
        bar_x0, bar_w, bar_y, bar_h = tx, 320, y0 + row_h - 18, 10
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + bar_w, bar_y + bar_h], radius=5, fill=branding.GRAY_TRACK)
        fill_w = max(6, int(bar_w * (r.power_score / max_score)))
        bar_color = branding.WHITE if r.rank == 1 else branding.MAROON_LIGHT
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + fill_w, bar_y + bar_h], radius=5, fill=bar_color)

        # score + movement, right-aligned, top-anchored to this row
        score_text = f"{r.power_score}"
        stw = draw.textlength(score_text, font=F_SCORE)
        score_x = WIDTH - PADDING - 90
        draw.text((score_x - stw, y0 + 22), score_text, font=F_SCORE, fill=branding.WHITE)

        move_text, move_color = _movement_text(r.movement)
        mtw = draw.textlength(move_text, font=F_ARROW)
        draw.text((WIDTH - PADDING - mtw, y0 + 58), move_text, font=F_ARROW, fill=move_color)

    draw.text((PADDING, height - FOOTER_HEIGHT + 8), f"{config.BOT_NAME}'s Power Rankings",
               font=F_DETAIL, fill=branding.GRAY_SUBTEXT)

    img.convert("RGB").save(out_path, "PNG")
    return out_path
