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

WEEK_DX, WEEK_DY = 9, 2
DAY_DX, DAY_DY = 7, 4.5
MIN_HEIGHT, MAX_HEIGHT = 1.5, 40
MARGIN = 18
TITLE_SPACE = 30

SNAKE_COLOR = "#ff3df2"
SNAKE_SEGMENTS = 14
SNAKE_SPACING = 0.05
SNAKE_SPEED = 90


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
    distances = [0.0]
    for a, b in zip(route_points, route_points[1:]):
        distances.append(distances[-1] + math.dist(a, b))
    total_distance = distances[-1] or 1
    duration = total_distance / SNAKE_SPEED
    head_lead = SNAKE_SEGMENTS * SNAKE_SPACING / duration
    arrival = {}
    for cell, distance in zip(route, distances):
        arrival.setdefault(cell, (distance / total_distance - head_lead) % 1)

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
        if count and (week, day) in arrival:
            moment = arrival[(week, day)]
            shapes.append(
                f'<polygon fill="{SNAKE_COLOR}" opacity="0" points="{top}">'
                f'<animate attributeName="opacity" values="0;.9;0" calcMode="discrete" '
                f'keyTimes="0;{moment:.4f};{min(moment + 0.02, 1):.4f}" dur="{duration:.1f}s" repeatCount="indefinite"/>'
                f'</polygon>'
            )

    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in route_points)
    snake = []
    for segment in reversed(range(SNAKE_SEGMENTS)):
        radius = 3.4 - 1.8 * segment / SNAKE_SEGMENTS
        begin = -(SNAKE_SEGMENTS - segment) * SNAKE_SPACING
        snake.append(
            f'<circle r="{radius:.1f}" fill="{SNAKE_COLOR}" opacity="{1 - 0.6 * segment / SNAKE_SEGMENTS:.2f}">'
            f'<animateMotion path="{path}" dur="{duration:.1f}s" begin="{begin:.2f}s" repeatCount="indefinite"/>'
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
