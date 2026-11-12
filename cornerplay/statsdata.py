"""Numbers for the Stats window, worked out from the play-session log.

The log (playtime.sessions()) holds [key, start, end] for every session Cornerplay saw: the
games it starts itself, and Steam games while Cornerplay runs (steamrun.py). Steam's own
totals go further back but have no dates, so weekly and yearly numbers come from the log only.
"""
import time
from datetime import date, datetime, timedelta

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def _day(t):
    d = date.fromtimestamp(t)
    return f"{d.day} {MONTHS[d.month - 1]}"  # not strftime: that follows the system's language, not the app's


def _overlap(s, e, lo, hi):
    return max(0, min(e, hi) - max(s, lo))


def weekly(log, now=None, weeks=12):
    """Hours per week (weeks start on Monday, local time), oldest first, the current week last.
    [{"label": "3 Nov", "hours": 4.5}]"""
    now = now or time.time()
    today = datetime.fromtimestamp(now).date()
    monday = today - timedelta(days=today.weekday())
    out = []
    for i in range(weeks - 1, -1, -1):
        start = monday - timedelta(weeks=i)
        lo = datetime.combine(start, datetime.min.time()).timestamp()
        hi = datetime.combine(start + timedelta(weeks=1), datetime.min.time()).timestamp()
        secs = sum(_overlap(s, e, lo, hi) for _, s, e in log)
        out.append({"label": f"{start.day} {MONTHS[start.month - 1][:3]}", "hours": round(secs / 3600, 1)})
    return out


def years(log):
    """The years the log has sessions in, newest first."""
    return sorted({datetime.fromtimestamp(s).year for _, s, _e in log}, reverse=True)


def year_summary(log, year, title_of, finished_at=None):
    """Your year in Cornerplay: hours, games, the most played, the busiest month, the longest
    session, games started for the first time, and games finished.
    title_of(key) -> title or "" (a game no longer in the library). finished_at: {key: time}."""
    lo = datetime(year, 1, 1).timestamp()
    hi = datetime(year + 1, 1, 1).timestamp()
    per_game, per_month = {}, [0.0] * 12
    longest = (0, "", 0)
    first_seen = {}
    for key, s, e in log:
        first_seen[key] = min(first_seen.get(key, s), s)
        secs = _overlap(s, e, lo, hi)
        if not secs:
            continue
        per_game[key] = per_game.get(key, 0) + secs
        per_month[datetime.fromtimestamp(max(s, lo)).month - 1] += secs
        if e - s > longest[0]:
            longest = (e - s, key, s)
    by_title = {}  # one game bought on two stores is one game here
    for key, secs in per_game.items():
        t = title_of(key)
        if t:
            prev = by_title.get(t, (0, key))
            by_title[t] = (prev[0] + secs, prev[1])
    top = sorted(((secs, key, t) for t, (secs, key) in by_title.items()), key=lambda x: -x[0])[:5]
    busiest = max(range(12), key=lambda m: per_month[m]) if any(per_month) else -1
    new = sorted({t for t in (title_of(k) for k, s in first_seen.items() if lo <= s < hi) if t})
    finished = sorted({t for t in (title_of(k) for k, when in (finished_at or {}).items() if lo <= when < hi) if t})
    return {
        "year": year,
        "hours": round(sum(per_game.values()) / 3600, 1),
        "games": len(by_title),
        "top": [{"key": k, "title": t, "hours": round(secs / 3600, 1)} for secs, k, t in top],
        "months": [round(m / 3600, 1) for m in per_month],
        "busiestMonth": MONTHS[busiest] if busiest >= 0 else "",
        "busiestHours": round(per_month[busiest] / 3600, 1) if busiest >= 0 else 0,
        "longest": {"title": title_of(longest[1]), "hours": round(longest[0] / 3600, 1),
                    "date": _day(longest[2]) if longest[2] else ""}
                   if longest[1] and title_of(longest[1]) else {},
        "newGames": new[:30], "newCount": len(new),
        "finished": finished, "finishedCount": len(finished),
    }


def backlog(counts):
    """{"playing": n, "want": n, "finished": n, "dropped": n} -> the share of the backlog done.
    The backlog is what you meant to play: playing, want to play and finished."""
    total = counts.get("playing", 0) + counts.get("want", 0) + counts.get("finished", 0)
    return {"total": total, "done": counts.get("finished", 0),
            "percent": round(100 * counts.get("finished", 0) / total) if total else 0}
