"""
Builds the "power ranking shift over the season" chart for the end-of-year
presentation -- one small-multiple mini line chart per team, rank-by-week,
so "went from 1st to 3rd" reads as an obvious downward line at a glance.

Why small multiples instead of one big chart with all 12 teams' lines on it:
a 12-line rank chart crosses itself constantly (every trade of places is a
crossing), which makes both color-matching *and* the lines themselves
unreadable well before you get to 12 series -- see
dataviz/references/marks-and-anatomy.md ("past ~4 converging series, small
multiples is usually right") and choosing-a-form.md (categorical color only
reliably supports up to ~8 series before folding to "Other"/faceting). One
mini-chart per team sidesteps that entirely: each panel only ever has one
line, so there's no color-identity problem to solve, and "trended up/down"
is exactly what a rank line answers on its own.

Each panel's line is colored by *direction* (green = finished better than
they started, red = finished worse, gray = unchanged) -- a status encoding,
kept separate from the maroon/white/black brand palette the rest of this
project uses, same reasoning as branding.py's module docstring.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

from . import branding, config, espn_client, power_rankings, roster_strength


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


COLOR_BG = _hex(branding.BLACK)
COLOR_PANEL = "#1c1c1c"
COLOR_TEXT = _hex(branding.WHITE)
COLOR_SUBTEXT = _hex(branding.GRAY_SUBTEXT)
COLOR_GRID = "#333333"
COLOR_GOOD = _hex(branding.STATUS_GOOD)     # finished better than they started
COLOR_CRITICAL = _hex(branding.STATUS_BAD)  # finished worse
COLOR_NEUTRAL = _hex(branding.STATUS_NEUTRAL)  # unchanged

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_PATH_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
try:
    fm.fontManager.addfont(_FONT_PATH)
    fm.fontManager.addfont(_FONT_PATH_REG)
    _BOLD_FONT = fm.FontProperties(fname=_FONT_PATH).get_name()
    _REG_FONT = fm.FontProperties(fname=_FONT_PATH_REG).get_name()
except Exception:
    _BOLD_FONT = _REG_FONT = "DejaVu Sans"


def compute_weekly_ranks(league, through_week: int = None, include_roster_strength: bool = False) -> Dict[int, Dict[int, int]]:
    """
    Returns {week: {team_id: rank}} by recomputing power rankings
    cumulatively through each completed week -- the same math
    tuesday_recap.py uses, just replayed across the whole season so far.

    include_roster_strength=True matches the live weekly rankings more
    exactly, but re-fetches box scores for every past week (slower, and
    somewhat beside the point for a season-shape chart) -- off by default.
    """
    through_week = through_week or (espn_client.get_current_week(league) - 1)
    through_week = max(through_week, 1)

    weekly_ranks: Dict[int, Dict[int, int]] = {}
    for wk in range(1, through_week + 1):
        team_seasons = espn_client.get_all_team_seasons(league, through_week=wk)
        roster_scores = None
        if include_roster_strength:
            try:
                roster_scores = roster_strength.as_score_dict(roster_strength.compute_roster_strength(league, wk))
            except Exception:
                roster_scores = None
        rows = power_rankings.compute_power_rankings(team_seasons, roster_strength_scores=roster_scores)
        weekly_ranks[wk] = {r.team_id: r.rank for r in rows}
    return weekly_ranks


def render_season_trend(
    weekly_ranks: Dict[int, Dict[int, int]],
    team_names: Dict[int, str],
    out_path: str,
    subtitle: Optional[str] = None,
) -> str:
    """
    weekly_ranks: {week: {team_id: rank}}, e.g. from compute_weekly_ranks().
    team_names: {team_id: display name}.
    """
    weeks = sorted(weekly_ranks.keys())
    if not weeks:
        raise ValueError("weekly_ranks is empty -- nothing to chart")

    team_ids = list(team_names.keys())
    n_teams = len(team_ids)
    series = {}
    for tid in team_ids:
        series[tid] = [weekly_ranks[wk].get(tid) for wk in weeks]

    # sort panels by final known rank, so the grid reads like a leaderboard
    def _final_rank(tid):
        vals = [r for r in series[tid] if r is not None]
        return vals[-1] if vals else n_teams
    team_ids.sort(key=_final_rank)

    cols = 3 if n_teams <= 9 else 4
    rows = -(-n_teams // cols)  # ceil

    fig_w_in, fig_h_in, dpi = cols * 3.4, rows * 2.6, 150
    fig = plt.figure(figsize=(fig_w_in, fig_h_in), dpi=dpi, facecolor=COLOR_BG)

    # watermark first, so it sits *behind* the subplot grid added next --
    # each panel's own opaque background will cover it within panel bounds,
    # leaving it visible only in the margins/gutters (see branding.py)
    logo = branding.load_logo()
    if logo:
        fig_w_px, fig_h_px = int(fig_w_in * dpi), int(fig_h_in * dpi)
        wm_size = int(min(fig_w_px, fig_h_px) * 0.55)
        watermark = branding.flat_tint(logo, opacity=0.05, tint=branding.WHITE, max_size=(wm_size, wm_size))
        if watermark:
            wm_arr = np.asarray(watermark)
            wx = (fig_w_px - wm_arr.shape[1]) // 2
            wy = (fig_h_px - wm_arr.shape[0]) // 2
            fig.figimage(wm_arr, xo=wx, yo=wy, zorder=0)

    axes = fig.subplots(rows, cols)
    axes_flat = axes.flatten() if n_teams > 1 else [axes]

    for i, tid in enumerate(team_ids):
        ax = axes_flat[i]
        ax.set_facecolor(COLOR_PANEL)
        ranks = series[tid]
        xs = [wk for wk, r in zip(weeks, ranks) if r is not None]
        ys = [r for r in ranks if r is not None]

        start_rank, end_rank = ys[0], ys[-1]
        shift = start_rank - end_rank  # positive = improved (moved toward rank 1)
        if shift > 0:
            color = COLOR_GOOD
            shift_text = f"▲ {shift}"
        elif shift < 0:
            color = COLOR_CRITICAL
            shift_text = f"▼ {abs(shift)}"
        else:
            color = COLOR_NEUTRAL
            shift_text = "―"

        ax.plot(xs, ys, color=color, linewidth=2, solid_joinstyle="round", solid_capstyle="round", zorder=3)
        ax.scatter([xs[-1]], [ys[-1]], color=color, s=44, zorder=4, edgecolors=COLOR_PANEL, linewidths=2)

        ax.invert_yaxis()
        ax.set_ylim(n_teams + 0.6, 0.4)
        ax.set_xlim(min(weeks) - 0.3, max(weeks) + 0.3)
        ax.set_yticks([1, n_teams])
        ax.set_yticklabels(["1st", f"{n_teams}th"], fontsize=8, color=COLOR_SUBTEXT, fontproperties=_REG_FONT)
        ax.set_xticks([min(weeks), max(weeks)])
        ax.set_xticklabels([f"Wk {min(weeks)}", f"Wk {max(weeks)}"], fontsize=8, color=COLOR_SUBTEXT, fontproperties=_REG_FONT)
        ax.grid(True, color=COLOR_GRID, linewidth=0.6, zorder=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(length=0)

        team_label = team_names.get(tid, str(tid))
        ax.set_title(team_label, fontsize=12, color=COLOR_TEXT, fontproperties=_BOLD_FONT, loc="left", pad=6)
        ax.text(
            0.98, 0.94, shift_text, transform=ax.transAxes, ha="right", va="top",
            fontsize=11, color=color, fontproperties=_BOLD_FONT,
        )

    # hide any unused grid cells (when n_teams doesn't fill the last row)
    for j in range(n_teams, len(axes_flat)):
        axes_flat[j].axis("off")

    fig.suptitle(
        f"{subtitle or config.LEAGUE_DISPLAY_NAME} — Power Ranking Trend",
        fontsize=20, color=COLOR_TEXT, fontproperties=_BOLD_FONT, x=0.02, ha="left", y=0.985,
    )
    fig.text(
        0.02, 0.945, f"Season through Week {max(weeks)}  •  green = finished higher than they started, red = lower",
        fontsize=11, color=COLOR_SUBTEXT, fontproperties=_REG_FONT, ha="left",
    )

    fig.tight_layout(rect=[0, 0, 1, 0.90])
    fig.savefig(out_path, facecolor=COLOR_BG)
    plt.close(fig)
    return out_path
