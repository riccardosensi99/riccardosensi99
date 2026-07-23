#!/usr/bin/env python3
import json
import os
import re
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

USER = os.getenv("GITHUB_REPOSITORY_OWNER", "riccardosensi99")
TOKEN = os.getenv("GITHUB_TOKEN", "")
OUT = Path("profile")
OUT.mkdir(parents=True, exist_ok=True)

BG = "#1a1b27"
BORDER = "#30363d"
TEXT = "#c0caf5"
MUTED = "#a9b1d6"
ACCENT = "#70a5fd"
PURPLE = "#bb9af7"
GREEN = "#9ece6a"

LANG_COLORS = {
    "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Dart": "#00B4AB",
    "PHP": "#4F5D95", "Python": "#3572A5", "HTML": "#e34c26",
    "CSS": "#563d7c", "Vue": "#41b883", "Shell": "#89e051",
    "Java": "#b07219", "Kotlin": "#A97BFF", "C#": "#178600",
}


def request_json(url):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-card-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def request_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def svg_shell(width, height, title, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <defs>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="{ACCENT}"/><stop offset="100%" stop-color="{PURPLE}"/></linearGradient>
  </defs>
  <rect width="{width}" height="{height}" rx="14" fill="{BG}"/>
  <rect x="1" y="1" width="{width-2}" height="{height-2}" rx="13" fill="none" stroke="{BORDER}"/>
  <text x="24" y="34" fill="{ACCENT}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="18" font-weight="700">{escape(title)}</text>
  {body}
</svg>'''


def fetch_repos():
    repos = []
    for page in range(1, 6):
        chunk = request_json(f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&type=owner&sort=updated")
        repos.extend(chunk)
        if len(chunk) < 100:
            break
    return [repo for repo in repos if not repo.get("fork")]


def fetch_contribution_levels():
    today = date.today()
    start = today - timedelta(days=364)
    url = f"https://github.com/users/{USER}/contributions?from={start.isoformat()}&to={today.isoformat()}"
    html = request_text(url)
    matches = re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="([0-4])"', html)
    levels = {day: int(level) for day, level in matches}
    if not levels:
        raise RuntimeError("Could not parse GitHub contribution calendar")
    return levels


def generate_stats(user, repos, levels):
    stars = sum(repo.get("stargazers_count", 0) for repo in repos)
    forks = sum(repo.get("forks_count", 0) for repo in repos)
    active_days = sum(1 for level in levels.values() if level > 0)
    values = [
        (str(len(repos)), "Public repositories"),
        (str(stars), "Stars earned"),
        (str(user.get("followers", 0)), "Followers"),
        (str(active_days), "Active days / year"),
    ]
    body = []
    for i, (value, label) in enumerate(values):
        x = 95 + i * 185
        body.append(f'<text x="{x}" y="92" text-anchor="middle" fill="url(#accent)" font-family="Segoe UI, Ubuntu, sans-serif" font-size="34" font-weight="700">{value}</text>')
        body.append(f'<text x="{x}" y="120" text-anchor="middle" fill="{MUTED}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="12">{label}</text>')
        if i < len(values) - 1:
            body.append(f'<line x1="{x+92}" y1="58" x2="{x+92}" y2="136" stroke="{BORDER}"/>')
    body.append(f'<text x="24" y="162" fill="{MUTED}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="12">{escape(user.get("name") or USER)} · {len(repos)} original repositories · {forks} forks</text>')
    OUT.joinpath("stats.svg").write_text(svg_shell(760, 185, "GitHub Stats", "\n  ".join(body)), encoding="utf-8")


def generate_languages(repos):
    totals = defaultdict(int)
    for repo in repos:
        try:
            languages = request_json(repo["languages_url"])
            for language, size in languages.items():
                totals[language] += size
        except Exception as exc:
            print(f"Skipping languages for {repo.get('name')}: {exc}")
    top = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:8]
    total = sum(size for _, size in top) or 1
    body = []
    cursor = 24.0
    for language, size in top:
        width = 712 * size / total
        color = LANG_COLORS.get(language, "#7aa2f7")
        body.append(f'<rect x="{cursor:.1f}" y="54" width="{max(width, 2):.1f}" height="10" fill="{color}"/>')
        cursor += width
    for i, (language, size) in enumerate(top):
        col = i % 2
        row = i // 2
        x = 34 + col * 355
        y = 92 + row * 25
        pct = size * 100 / total
        color = LANG_COLORS.get(language, "#7aa2f7")
        body.append(f'<circle cx="{x}" cy="{y-4}" r="5" fill="{color}"/>')
        body.append(f'<text x="{x+14}" y="{y}" fill="{TEXT}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="12">{escape(language)} {pct:.1f}%</text>')
    OUT.joinpath("top-langs.svg").write_text(svg_shell(760, 205, "Most Used Languages", "\n  ".join(body)), encoding="utf-8")


def streaks(levels):
    ordered = sorted((datetime.strptime(day, "%Y-%m-%d").date(), level) for day, level in levels.items())
    longest = running = 0
    for _, level in ordered:
        running = running + 1 if level > 0 else 0
        longest = max(longest, running)
    today = date.today()
    index = len(ordered) - 1
    while index >= 0 and ordered[index][0] > today:
        index -= 1
    if index >= 0 and ordered[index][0] == today and ordered[index][1] == 0:
        index -= 1
    current = 0
    if index >= 0 and ordered[index][0] in (today, today - timedelta(days=1)):
        while index >= 0 and ordered[index][1] > 0:
            current += 1
            index -= 1
    return current, longest


def generate_streak(levels):
    current, longest = streaks(levels)
    active_days = sum(1 for level in levels.values() if level > 0)
    values = [(current, "Current streak"), (longest, "Longest streak"), (active_days, "Active days / year")]
    body = []
    for i, (value, label) in enumerate(values):
        x = 127 + i * 253
        body.append(f'<text x="{x}" y="103" text-anchor="middle" fill="url(#accent)" font-family="Segoe UI, Ubuntu, sans-serif" font-size="38" font-weight="700">{value}</text>')
        body.append(f'<text x="{x}" y="131" text-anchor="middle" fill="{MUTED}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">{label}</text>')
        if i < 2:
            body.append(f'<line x1="{x+126}" y1="58" x2="{x+126}" y2="150" stroke="{BORDER}"/>')
    OUT.joinpath("streak.svg").write_text(svg_shell(760, 175, "Contribution Streak", "\n  ".join(body)), encoding="utf-8")


def generate_contributions(levels):
    today = date.today()
    start = today - timedelta(days=364)
    start -= timedelta(days=(start.weekday() + 1) % 7)
    palette = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
    cells = []
    for offset in range(371):
        day = start + timedelta(days=offset)
        if day > today:
            break
        week = offset // 7
        weekday = (day.weekday() + 1) % 7
        level = levels.get(day.isoformat(), 0)
        x = 25 + week * 13
        y = 55 + weekday * 13
        cells.append(f'<rect x="{x}" y="{y}" width="10" height="10" rx="2" fill="{palette[level]}"><title>{day.isoformat()}</title></rect>')
    cells.append(f'<text x="24" y="168" fill="{MUTED}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">Public contribution activity for the last 12 months</text>')
    OUT.joinpath("contributions.svg").write_text(svg_shell(760, 185, "Contribution Activity", "\n  ".join(cells)), encoding="utf-8")


def main():
    user = request_json(f"https://api.github.com/users/{USER}")
    repos = fetch_repos()
    levels = fetch_contribution_levels()
    generate_stats(user, repos, levels)
    generate_languages(repos)
    generate_streak(levels)
    generate_contributions(levels)
    print("Generated:", ", ".join(str(path) for path in sorted(OUT.glob("*.svg"))))


if __name__ == "__main__":
    main()
