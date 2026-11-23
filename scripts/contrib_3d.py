import json
import math
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

SNAKE_COLOR = "#ff3df2"
SNAKE_CORE = "#ffd6fb"
SNAKE_LENGTH = 120
SNAKE_SPEED = 140
WAVE_PERIOD = 5
WAVE_STEP = 0.045

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


def snake_route(cells):
    targets = sorted(cell for cell, (count, _) in cells.items() if count)
    if not targets:
        return []
    route = [targets[0]]
    remaining = set(targets[1:])
    while remaining:
        week, day = route[-1]
        target = min(remaining, key=lambda c: (abs(c[0] - week) + abs(c[1] - day), c))
        remaining.remove(target)
        while (week, day) != target:
            if week != target[0]:
                week += 1 if target[0] > week else -1
            else:
                day += 1 if target[1] > day else -1
            route.append((week, day))
    week, day = route[-1]
    start = route[0]
    while (week, day) != start:
        if day != start[1]:
            day += 1 if start[1] > day else -1
        else:
            week += 1 if start[0] > week else -1
        route.append((week, day))
    return route


def cubic_point(p0, c1, c2, p1, t):
    u = 1 - t
    return tuple(u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * d for a, b, c, d in zip(p0, c1, c2, p1))


def smooth_path(route_points):
    count = len(route_points)
    commands = [f"M{route_points[0][0]:.1f},{route_points[0][1]:.1f}"]
    distances = [0.0]
    for i in range(count - 1):
        before = route_points[i - 1] if i else route_points[-2]
        start, end = route_points[i], route_points[i + 1]
        after = route_points[i + 2] if i + 2 < count else route_points[1]
        c1 = tuple(s + (e - b) / 6 for s, e, b in zip(start, end, before))
        c2 = tuple(e - (a - s) / 6 for s, e, a in zip(start, end, after))
        commands.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {end[0]:.1f},{end[1]:.1f}")
        samples = [cubic_point(start, c1, c2, end, step / 12) for step in range(13)]
        distances.append(distances[-1] + sum(math.dist(a, b) for a, b in zip(samples, samples[1:])))
    return " ".join(commands), distances


def render(calendar):
    cells = {
        (week, day["weekday"]): (day["contributionCount"], LEVELS.index(day["contributionLevel"]))
        for week, entry in enumerate(calendar["weeks"])
        for day in entry["contributionDays"]
    }
    counts = sorted(count for count, _ in cells.values() if count)
    peak = counts[int(len(counts) * 0.95)] if counts else 1
    heights = {cell: bar_height(count, level, peak) for cell, (count, level) in cells.items()}
    weeks = len(calendar["weeks"])

    origin_x = MARGIN + 7 * DAY_DX
    origin_y = MARGIN + TITLE_SPACE + MAX_HEIGHT
    width = origin_x + (weeks + 1) * WEEK_DX + MARGIN
    height = origin_y + (weeks + 1) * WEEK_DY + 8 * DAY_DY + MARGIN

    def project(week, day, z=0):
        return (
            origin_x + week * WEEK_DX - day * DAY_DX,
            origin_y + week * WEEK_DY + day * DAY_DY - z,
        )

    route = snake_route(cells)
    route_points = [project(w + 0.5, d + 0.5, heights.get((w, d), MIN_HEIGHT) + 2) for w, d in route]
    path, distances = smooth_path(route_points)
    total_distance = distances[-1] or 1
    duration = total_distance / SNAKE_SPEED
    arrival = {}
    for cell, distance in zip(route, distances):
        arrival.setdefault(cell, distance / total_distance)

    shapes = []
    for (week, day), (count, level) in sorted(cells.items(), key=lambda c: (c[0][0] + c[0][1], c[0][0])):
        z = heights[(week, day)]
        back = project(week, day)
        right = project(week + 1, day)
        front = project(week + 1, day + 1)
        left = project(week, day + 1)
        lift = lambda p: (p[0], p[1] - z)
        top = points(lift(back), lift(right), lift(front), lift(left))
        color = TOPS[level]
        shapes.append(f'<polygon fill="{shade(color, 0.55)}" points="{points(left, front, lift(front), lift(left))}"/>')
        shapes.append(f'<polygon fill="{shade(color, 0.35)}" points="{points(front, right, lift(right), lift(front))}"/>')
        glow = ' filter="url(#glow)"' if level >= 3 else ""
        shapes.append(f'<polygon fill="{color}" stroke="#0b1020" stroke-width=".4"{glow} points="{top}"/>')
        if not count:
            continue
        wave_begin = week * WAVE_STEP - WAVE_PERIOD
        shapes.append(
            f'<polygon fill="#e0fbff" opacity="0" points="{top}">'
            f'<animate attributeName="opacity" values="0;.35;0" keyTimes="0;.12;.4" dur="{WAVE_PERIOD}s" '
            f'begin="{wave_begin:.2f}s" repeatCount="indefinite"/></polygon>'
        )
        if (week, day) in arrival:
            moment = arrival[(week, day)]
            shapes.append(
                f'<polygon fill="{SNAKE_COLOR}" opacity="0" points="{top}">'
                f'<animate attributeName="opacity" values="0;0;1;0;0" '
                f'keyTimes="0;{moment:.4f};{min(moment + 0.002, 1):.4f};{min(moment + 0.05, 1):.4f};1" '
                f'dur="{duration:.1f}s" repeatCount="indefinite"/></polygon>'
            )

    snake = []
    for stroke_width, opacity, color, share in ((9, 0.18, SNAKE_COLOR, 1), (5, 0.55, SNAKE_COLOR, 0.7), (2.2, 1, SNAKE_CORE, 0.4)):
        length = SNAKE_LENGTH * share
        snake.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-opacity="{opacity}" '
            f'stroke-linecap="round" stroke-linejoin="round" '
            f'stroke-dasharray="{length:.1f} {total_distance - length:.1f}">'
            f'<animate attributeName="stroke-dashoffset" from="{length:.1f}" to="{length - total_distance:.1f}" '
            f'dur="{duration:.1f}s" repeatCount="indefinite"/></path>'
        )
    snake.append(
        f'<circle r="3.6" fill="#fff">'
        f'<animate attributeName="r" values="3;4.6;3" dur="0.8s" repeatCount="indefinite"/>'
        f'<animateMotion path="{path}" dur="{duration:.1f}s" repeatCount="indefinite"/></circle>'
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
        f'.n{{fill:#22d3ee;font-weight:700}}.s{{fill:{SNAKE_COLOR}}}</style>'
        f'<rect width="100%" height="100%" rx="12" fill="url(#bg)"/>'
        f'<text x="{MARGIN}" y="{MARGIN + 14}"><tspan class="n">{total}</tspan> contributions '
        f'<tspan class="s">//</tspan> last 12 months</text>'
        f'{"".join(shapes)}'
        f'<g filter="url(#glow)">{"".join(snake)}</g>'
        '</svg>\n'
    )


if __name__ == "__main__":
    login, output_path = sys.argv[1], sys.argv[2]
    with open(output_path, "w") as output:
        output.write(render(fetch_calendar(login, os.environ["GITHUB_TOKEN"])))
