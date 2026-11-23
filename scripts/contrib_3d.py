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
LIGHT = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
DARK = ["#21262d", "#0e4429", "#006d32", "#26a641", "#39d353"]

WEEK_DX, WEEK_DY = 7.6, 1.6
DAY_DX, DAY_DY = 6, 4
MIN_HEIGHT, MAX_HEIGHT = 2, 30
MARGIN = 12
TITLE_SPACE = 26


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


def palette_css(colors):
    rules = []
    for level, color in enumerate(colors):
        rules.append(f".t{level}{{fill:{color}}}")
        rules.append(f".l{level}{{fill:{shade(color, 0.78)}}}")
        rules.append(f".r{level}{{fill:{shade(color, 0.62)}}}")
    return "".join(rules)


def bar_height(count, level, peak):
    if level == 0:
        return MIN_HEIGHT
    return MIN_HEIGHT + 4 + (MAX_HEIGHT - MIN_HEIGHT - 4) * (min(count, peak) / peak) ** 0.5


def points(*corners):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in corners)


def render(calendar):
    days = [
        (week, day["weekday"], day["contributionCount"], LEVELS.index(day["contributionLevel"]))
        for week, entry in enumerate(calendar["weeks"])
        for day in entry["contributionDays"]
    ]
    counts = sorted(count for _, _, count, _ in days if count)
    peak = counts[int(len(counts) * 0.95)] if counts else 1
    weeks = len(calendar["weeks"])

    origin_x = MARGIN + 7 * DAY_DX
    origin_y = MARGIN + TITLE_SPACE + MAX_HEIGHT
    width = origin_x + (weeks + 1) * WEEK_DX + MARGIN
    height = origin_y + (weeks + 1) * WEEK_DY + 8 * DAY_DY + MARGIN

    def project(week, weekday, z=0):
        return (
            origin_x + week * WEEK_DX - weekday * DAY_DX,
            origin_y + week * WEEK_DY + weekday * DAY_DY - z,
        )

    shapes = []
    for week, weekday, count, level in sorted(days, key=lambda d: (d[0] + d[1], d[0])):
        z = bar_height(count, level, peak)
        back = project(week, weekday)
        right = project(week + 1, weekday)
        front = project(week + 1, weekday + 1)
        left = project(week, weekday + 1)
        lift = lambda p: (p[0], p[1] - z)
        shapes.append(f'<polygon class="l{level}" points="{points(left, front, lift(front), lift(left))}"/>')
        shapes.append(f'<polygon class="r{level}" points="{points(front, right, lift(right), lift(front))}"/>')
        shapes.append(f'<polygon class="t{level}" points="{points(lift(back), lift(right), lift(front), lift(left))}"/>')

    total = f"{calendar['totalContributions']:,} contributions in the last year"
    style = (
        f"text{{font:600 13px -apple-system,'Segoe UI',Helvetica,Arial,sans-serif;fill:#57606a}}"
        f"{palette_css(LIGHT)}"
        f"@media (prefers-color-scheme:dark){{text{{fill:#8b949e}}{palette_css(DARK)}}}"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}"><style>{style}</style>'
        f'<text x="{MARGIN}" y="{MARGIN + 13}">{total}</text>'
        f'{"".join(shapes)}</svg>\n'
    )


if __name__ == "__main__":
    login, output_path = sys.argv[1], sys.argv[2]
    with open(output_path, "w") as output:
        output.write(render(fetch_calendar(login, os.environ["GITHUB_TOKEN"])))
