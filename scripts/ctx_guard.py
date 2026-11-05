"""Context guard for the task-router-general plugin.

Hook events:
  PostToolUse / UserPromptSubmit — tells the model the real chat size (once per +STEP tokens),
      and near the auto-compact threshold asks it to keep .claude/handoff.md up to date.
  SessionStart (compact) — puts .claude/handoff.md back into context after compaction.
  SessionStart (startup/clear/resume) — mentions an unfinished handoff.md if it is fresh.

Usage in hooks.json: python ctx_guard.py <data_dir>. Never fails the session: any error -> silent exit 0.
"""
import json, os, sys, time

STEP = 50_000            # report chat size every +50k tokens
FIRST = 50_000           # first report at 50k
WARN_SHARE = 0.7         # handoff reminder from 70% of the auto-compact window
WARN_STEP = 15_000       # repeat the handoff reminder every +15k
HANDOFF_MAX = 9_000      # chars of handoff.md injected after compaction
OPUS_CACHE_READ = 0.5e-6  # $ per token


def out(event, text):
    # ASCII-only JSON: safe whatever the console code page is (cp1251 etc.)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}, ensure_ascii=True))


def ctx_size(path):
    """Context size = tokens the last main-thread request read (input + cache)."""
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


def window():
    v = os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW", "").lower().replace("_", "")
    try:
        w = int(float(v[:-1]) * 1000) if v.endswith("k") else int(v)
    except ValueError:
        w = 200_000
    pct = os.environ.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE")
    if pct and pct.isdigit():
        w = int(w * int(pct) / 100)
    return w


def handoff_path(cwd):
    return os.path.normpath(os.path.join(cwd or ".", ".claude", "handoff.md"))


def age_text(p):
    if not os.path.exists(p):
        return "файла ещё нет"
    m = (time.time() - os.path.getmtime(p)) / 60
    return f"обновлён {int(m)} мин назад" if m < 120 else f"обновлён {m / 60:.0f} ч назад"


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.claude/ctx_guard")
    inp = json.load(sys.stdin)
    if inp.get("agent_id"):           # subagents: their context is small and separate
        return
    ev = inp.get("hook_event_name", "")
    hp = handoff_path(inp.get("cwd"))

    if ev == "SessionStart":
        src = inp.get("source")
        if not os.path.exists(hp):
            return
        if src == "compact":
            txt = open(hp, encoding="utf-8", errors="ignore").read()[:HANDOFF_MAX]
            out(ev, f"Чат был автоматически сжат. Ниже — сохранённое перед сжатием состояние работы из {hp} "
                    f"(точнее, чем выжимка):\n\n{txt}")
        elif time.time() - os.path.getmtime(hp) < 24 * 3600:
            out(ev, f"В этом проекте есть незавершённая работа: {hp} ({age_text(hp)}). "
                    f"Если пользователь продолжает её — сначала прочитай этот файл.")
        return

    n = ctx_size(inp.get("transcript_path", ""))
    if n < FIRST:
        return
    os.makedirs(data_dir, exist_ok=True)
    sp = os.path.join(data_dir, f"{inp.get('session_id', 'x')}.json")
    try:
        st = json.load(open(sp))
    except (OSError, ValueError):
        st = {}
    if n < st.get("last", 0) * 0.6:  # chat shrank -> it was compacted: start over
        st = {}
    st = {"size_mark": st.get("size_mark", 0), "warn_mark": st.get("warn_mark", 0), "last": n}
    msgs = []
    if n >= st["size_mark"] + STEP or st["size_mark"] == 0:
        st["size_mark"] = n // STEP * STEP
        msgs.append(f"Размер чата сейчас ≈ {n // 1000} тыс. токенов: каждый шаг модели перечитывает его "
                    f"(≈ ${n * OPUS_CACHE_READ:.2f} за шаг на opus). При таком размере исполнение от ~3–4 шагов "
                    f"дешевле отдавать субагентам (haiku/sonnet), а независимые вызовы делать одной пачкой.")
    w = window()
    if n >= w * WARN_SHARE and n >= st["warn_mark"] + WARN_STEP:
        st["warn_mark"] = n
        msgs.append(f"Автосжатие чата наступит примерно при {w // 1000} тыс. токенов. Состояние работы "
                    f"хранится в {hp} ({age_text(hp)}): цель, что сделано, решения, пути к файлам, следующий шаг, "
                    f"подводные камни — до 60 строк. После сжатия этот файл автоматически вернётся в контекст, "
                    f"поэтому его стоит обновить на ближайшей паузе между этапами.")
    json.dump(st, open(sp, "w"))
    if msgs:
        out(ev, "\n".join(msgs))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
