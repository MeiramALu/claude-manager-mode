"""Status line: chat size, cost of one step, session cost.

Example: ctx 87k/117k 74%  (117k = point where the chat auto-compacts) · step ~$0.04 · session $1.23
Settings: "statusLine": {"type": "command", "command": "python <path>/statusline.py"}
"""
import json, os, sys

# $ per token to re-read the cached context once (cache read price)
CACHE_READ = {"opus": 0.5e-6, "sonnet": 0.3e-6, "haiku": 0.1e-6}


def window():
    v = os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW", "").lower().replace("_", "")
    try:
        return int(float(v[:-1]) * 1000) if v.endswith("k") else int(v)
    except ValueError:
        return 0


def compact_point(w):
    """Claude Code auto-compacts at window - 20k (reply reserve) - 13k (buffer)."""
    return max(w - 33_000, w // 2)


def from_transcript(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400_000))
            lines = f.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return 0
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") != "assistant" or d.get("isSidechain"):
            continue
        u = (d.get("message") or {}).get("usage") or {}
        n = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
        if n:
            return n
    return 0


def main():
    d = json.load(sys.stdin)
    cw = d.get("context_window") or {}
    cu = cw.get("current_usage") or {}
    n = sum(cu.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    if not n:
        n = from_transcript(d.get("transcript_path", ""))
    w = compact_point(window() or cw.get("context_window_size") or 200_000)
    mid = ((d.get("model") or {}).get("id") or "").lower()
    price = next((p for k, p in CACHE_READ.items() if k in mid), CACHE_READ["opus"])
    share = n / w if w else 0
    color = "\033[31m" if share >= 0.9 else "\033[33m" if share >= 0.7 else "\033[32m"
    parts = [f"{color}ctx {n // 1000}k/{w // 1000}k {share:.0%}\033[0m", f"step ~${n * price:.2f}"]
    cost = (d.get("cost") or {}).get("total_cost_usd")
    if cost is not None:
        parts.append(f"session ${cost:.2f}")
    print(" · ".join(parts))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1251/cp866
    except Exception:
        pass
    try:
        main()
    except Exception:
        print("ctx ?")
