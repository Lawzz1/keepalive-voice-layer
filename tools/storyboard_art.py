"""The storyboard drawings, as SVG fragments on a 640x360 viewBox.

Kept apart from the sheet and the animatic so both draw the same pictures: if a
shot changes on set, it changes here once.
"""

W, GREY, RED, GREEN, BLUE = "#e9ecf2", "#8f97a6", "#ff5b5d", "#2ec28a", "#57b9ff"

_POSES = {
    "stand": "M0 -62 L0 -26 M0 -52 L-16 -34 M0 -52 L16 -34 M0 -26 L-13 0 M0 -26 L13 0",
    "walk": "M0 -62 L0 -26 M0 -52 L-18 -40 M0 -52 L17 -36 M0 -26 L-17 0 M0 -26 L15 0",
    "clutch": "M0 -62 L0 -26 M0 -52 L-10 -44 M0 -52 L-6 -46 M0 -26 L-14 0 M0 -26 L14 0",
    "run": "M0 -62 L2 -26 M0 -54 L-20 -48 M0 -54 L20 -62 M2 -26 L-18 -2 M2 -26 L20 -6",
    "kneel": "M0 -52 L0 -24 M0 -44 L-16 -18 M0 -44 L14 -18 M0 -24 L-22 -2 L4 -2",
}


def stick(x, y, colour=W, pose="stand", scale=1.0, width=5):
    head = -74 if pose != "kneel" else -64
    return (f'<g transform="translate({x},{y}) scale({scale})" stroke="{colour}" '
            f'stroke-width="{width}" fill="none" stroke-linecap="round" stroke-linejoin="round">'
            f'<circle cx="0" cy="{head}" r="12" fill="{colour}"/>'
            f'<path d="{_POSES[pose]}"/></g>')


def lying(x, y, colour=W, scale=1.0, width=5):
    return (f'<g transform="translate({x},{y}) scale({scale})" stroke="{colour}" '
            f'stroke-width="{width}" fill="none" stroke-linecap="round">'
            f'<circle cx="-84" cy="0" r="12" fill="{colour}"/>'
            f'<path d="M-70 0 L10 0 M-40 0 L-30 -18 M10 0 L60 -10 M10 0 L60 10"/></g>')


def phone(x, y, w=22, h=40, screen=True):
    dot = (f'<circle cx="{x + w / 2}" cy="{y + h * 0.55}" r="5" fill="none" '
           f'stroke="{BLUE}" stroke-width="2"/>') if screen else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="#0d1219" '
            f'stroke="{GREEN}" stroke-width="2.5"/>{dot}')


def room(floor=250):
    return (f'<rect x="0" y="0" width="640" height="360" fill="#12161d"/>'
            f'<rect x="0" y="{floor}" width="640" height="{360 - floor}" fill="#181d26"/>'
            f'<line x1="0" y1="{floor}" x2="640" y2="{floor}" stroke="#2d3542" stroke-width="2"/>'
            f'<rect x="54" y="{floor - 120}" width="84" height="120" fill="none" stroke="#242c39" stroke-width="2"/>'
            f'<rect x="512" y="{floor - 84}" width="82" height="84" fill="none" stroke="#242c39" stroke-width="2"/>')


_CHEST = (f'<rect x="0" y="0" width="640" height="360" fill="#101620"/>'
          f'<rect x="0" y="276" width="640" height="84" fill="#171d27"/>'
          f'<path d="M50 276 Q210 196 340 206 Q470 214 600 276" stroke="{W}" stroke-width="5" fill="none"/>'
          f'<circle cx="304" cy="176" r="12" fill="{RED}"/>'
          f'<path d="M304 164 L304 136 M304 176 L286 200 M304 176 L322 200" stroke="{RED}" '
          f'stroke-width="5" stroke-linecap="round"/>')

PANEL_SVG = {
    "1": room() + stick(300, 250, W, "walk", 1.25),

    "2": room() + stick(300, 250, W, "clutch", 1.25),

    "3": room() + lying(330, 244, W, 1.15) + stick(470, 250, RED, "run", 1.2) + phone(258, 218),

    "4": ('<rect x="0" y="0" width="640" height="360" fill="#101620"/>'
          '<rect x="0" y="266" width="640" height="94" fill="#171d27"/>'
          '<rect x="206" y="62" width="132" height="240" rx="14" fill="#0b1119" stroke="#2ec28a" stroke-width="3"/>'
          '<rect x="222" y="86" width="100" height="14" rx="6" fill="#1e2937"/>'
          f'<circle cx="272" cy="176" r="30" fill="none" stroke="{BLUE}" stroke-width="4"/>'
          f'<circle cx="272" cy="176" r="46" fill="none" stroke="{BLUE}" stroke-width="2" opacity=".4"/>'
          '<rect x="222" y="244" width="100" height="12" rx="6" fill="#1e2937"/>'
          f'<path d="M470 118 L352 168" stroke="{RED}" stroke-width="9" stroke-linecap="round"/>'
          f'<circle cx="486" cy="110" r="17" fill="{RED}"/>'),

    "5": (_CHEST
          + f'<circle cx="304" cy="202" r="30" fill="none" stroke="{RED}" stroke-width="2.5" opacity=".5"/>'
          + f'<circle cx="304" cy="202" r="46" fill="none" stroke="{RED}" stroke-width="2" opacity=".25"/>'
          + phone(92, 246, 30, 52)),

    "6": (_CHEST
          + '<path d="M372 58 h226 v70 h-158 l-26 26 v-26 h-42 z" fill="#19202b" stroke="#2b3442" stroke-width="2"/>'
          + '<text x="392" y="92" fill="#9aa4b4" font-size="18" font-family="Menlo">A rib pop can happen.</text>'
          + '<text x="392" y="116" fill="#9aa4b4" font-size="18" font-family="Menlo">Do not stop.</text>'
          + phone(92, 246, 30, 52)),

    "7": (room() + lying(300, 246, W, 1.0) + stick(372, 250, RED, "kneel", 1.0)
          + phone(250, 222, 18, 32)
          + '<path d="M44 46 L92 46 M68 24 L68 68" stroke="#4a5568" stroke-width="2"/>'
          + '<text x="104" y="52" fill="#5c667a" font-size="17" font-family="Menlo">камера отходит назад</text>'),

    "8": ('<rect x="0" y="0" width="640" height="360" fill="#07090d"/>'
          '<rect x="156" y="30" width="328" height="300" rx="18" fill="#0b1119" stroke="#2ec28a" stroke-width="3"/>'
          '<rect x="182" y="58" width="170" height="14" rx="7" fill="#1e2937"/>'
          f'<circle cx="320" cy="166" r="58" fill="none" stroke="{BLUE}" stroke-width="5"/>'
          '<text x="320" y="176" fill="#cfd6e2" font-size="30" font-family="Menlo" text-anchor="middle">110</text>'
          '<text x="182" y="266" fill="#7f8b9c" font-size="17" font-family="Menlo">CPR 1:32 · 168 compressions</text>'
          '<text x="182" y="292" fill="#7f8b9c" font-size="17" font-family="Menlo">EMS handover ready</text>'
          '<path d="M18 18 L112 74 M622 18 L528 74" stroke="#29323f" stroke-width="3"/>'),
}
