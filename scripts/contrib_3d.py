import json
import os
import sys
import urllib.request

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount contributionLevel weekday } }
      }
    }
  }
}
"""

LEVELS = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]
TOPS = ["#161b2e", "#0e7490", "#06b6d4", "#22d3ee", "#a5f3fc"]

WEEK_DX, WEEK_DY = 15, 1.2
DAY_DX, DAY_DY = 4, 6
MIN_HEIGHT, MAX_HEIGHT = 1.5, 46
MARGIN = 18
TITLE_SPACE = 22

RISE_DELAY = 0.3
RISE_STEP = 0.025
RISE_DURATION = 1.2
WAVE_PERIOD = 6
WAVE_STEP = 0.045
SPARK_CELLS = 8
SPARK_PERIOD = 2.8
EASE_OUT = "0.2 0.8 0.2 1"


def fetch_calendar(login, token):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        body = json.load(response)
    if "errors" in body:
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def shade(hex_color, factor):
    channels = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(c * factor):02x}" for c in channels)


def bar_height(count, level, peak):
    if level == 0:
        return MIN_HEIGHT
    return MIN_HEIGHT + 5 + (MAX_HEIGHT - MIN_HEIGHT - 5) * (min(count, peak) / peak) ** 0.5


def points(*corners):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in corners)


def rising_polygon(fill, flat, full, delay, extra=""):
    duration = delay + RISE_DURATION
    return (
        f'<polygon fill="{fill}"{extra} points="{full}">'
        f'<animate attributeName="points" values="{flat};{flat};{full}" keyTimes="0;{delay / duration:.3f};1" '
        f'calcMode="spline" keySplines="0 0 1 1;{EASE_OUT}" dur="{duration:.2f}s"/></polygon>'
    )


def render(calendar):
    cells = {
        (week, day["weekday"]): (day["contributionCount"], LEVELS.index(day["contributionLevel"]))
        for week, entry in enumerate(calendar["weeks"])
        for day in entry["contributionDays"]
    }
    counts = sorted(count for count, _ in cells.values() if count)
    peak = counts[int(len(counts) * 0.95)] if counts else 1
    weeks = len(calendar["weeks"])
    rise_end = RISE_DELAY + weeks * RISE_STEP + RISE_DURATION

    origin_x = MARGIN + 7 * DAY_DX
    origin_y = MARGIN + TITLE_SPACE + MAX_HEIGHT
    width = origin_x + (weeks + 1) * WEEK_DX + MARGIN
    height = origin_y + (weeks + 1) * WEEK_DY + 8 * DAY_DY + MARGIN

    def project(week, day, z=0):
        return (
            origin_x + week * WEEK_DX - day * DAY_DX,
            origin_y + week * WEEK_DY + day * DAY_DY - z,
        )

    shapes = []
    for (week, day), (count, level) in sorted(cells.items(), key=lambda c: (c[0][0] + c[0][1], c[0][0])):
        z = bar_height(count, level, peak)
        back = project(week, day)
        right = project(week + 1, day)
        front = project(week + 1, day + 1)
        left = project(week, day + 1)
        lift = lambda p, h=z: (p[0], p[1] - h)
        flat = lambda p: lift(p, MIN_HEIGHT)
        color = TOPS[level]
        delay = RISE_DELAY + week * RISE_STEP
        faces = (
            (shade(color, 0.55), (left, front, lift(front), lift(left)), (left, front, flat(front), flat(left)), ""),
            (shade(color, 0.35), (front, right, lift(right), lift(front)), (front, right, flat(right), flat(front)), ""),
            (color, (lift(back), lift(right), lift(front), lift(left)), (flat(back), flat(right), flat(front), flat(left)),
             ' stroke="#0b1020" stroke-width=".4"' + (' filter="url(#glow)"' if level >= 3 else "")),
        )
        for fill, full, start, extra in faces:
            if level:
                shapes.append(rising_polygon(fill, points(*start), points(*full), delay, extra))
            else:
                shapes.append(f'<polygon fill="{fill}"{extra} points="{points(*full)}"/>')
        if level:
            shapes.append(
                f'<polygon fill="#e0fbff" opacity="0" points="{points(*faces[2][1])}">'
                f'<animate attributeName="opacity" values="0;.4;0;0" keyTimes="0;.1;.35;1" dur="{WAVE_PERIOD}s" '
                f'begin="{rise_end + week * WAVE_STEP:.2f}s" repeatCount="indefinite"/></polygon>'
            )

    busiest = sorted((cell for cell, (count, _) in cells.items() if count), key=lambda c: -cells[c][0])[:SPARK_CELLS]
    sparks = []
    for index, (week, day) in enumerate(busiest):
        x, y = project(week + 0.5, day + 0.5, bar_height(*cells[(week, day)], peak))
        for particle in range(3):
            begin = rise_end + index * 0.35 + particle * SPARK_PERIOD / 3
            drift = (particle - 1) * 3
            sparks.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.4" fill="#cffafe" opacity="0">'
                f'<animate attributeName="cy" values="{y:.1f};{y - 34:.1f}" dur="{SPARK_PERIOD}s" begin="{begin:.2f}s" repeatCount="indefinite"/>'
                f'<animate attributeName="cx" values="{x:.1f};{x + drift:.1f}" dur="{SPARK_PERIOD}s" begin="{begin:.2f}s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="0;1;0" dur="{SPARK_PERIOD}s" begin="{begin:.2f}s" repeatCount="indefinite"/>'
                f'</circle>'
            )

    total = f"{calendar['totalContributions']:,}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">'
        '<defs>'
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1020"/><stop offset="1" stop-color="#1a0b2e"/></linearGradient>'
        '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        '</defs>'
        '<style>text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;fill:#7d8590}'
        '.n{fill:#22d3ee;font-weight:700}.s{fill:#ff3df2}</style>'
        '<rect width="100%" height="100%" rx="12" fill="url(#bg)"/>'
        f'<text x="{MARGIN}" y="{MARGIN + 14}"><tspan class="n">{total}</tspan> contributions '
        '<tspan class="s">//</tspan> last 12 months</text>'
        f'{"".join(shapes)}'
        f'<g filter="url(#glow)">{"".join(sparks)}</g>'
        '</svg>\n'
    )


if __name__ == "__main__":
    login, output_path = sys.argv[1], sys.argv[2]
    with open(output_path, "w") as output:
        output.write(render(fetch_calendar(login, os.environ["GITHUB_TOKEN"])))
