"""Context guard for the task-router-general plugin.

Hook events:
  PostToolUse / UserPromptSubmit — tells the model the real chat size (once per +STEP tokens),
      and near the auto-compact threshold asks it to keep .claude/handoff.md up to date.
  PreCompact — saves a mechanical snapshot (goal, recent requests, changed files, todos) as a fallback.
  SessionStart (compact) — puts .claude/handoff.md and the snapshot back into context after compaction.
  SessionStart (startup/clear/resume) — mentions an unfinished handoff.md if it is fresh.

Usage in hooks.json: python ctx_guard.py <data_dir>. Never fails the session: any error -> silent exit 0.
"""
import json, os, sys, time

STEP = 50_000            # report chat size every +50k tokens
FIRST = 50_000           # first report at 50k
WARN_SHARE = 0.7         # handoff reminder from 70% of the auto-compact window
WARN_STEP = 15_000       # repeat the handoff reminder every +15k
HANDOFF_MAX = 9_000      # chars injected after compaction (handoff.md + auto snapshot)
SNAP_MAX = 3_000         # chars of the automatic snapshot
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


def _text(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def snapshot(path):
    """Mechanical state from the transcript, no model needed: goal, recent requests, changed files, todo list."""
    prompts, files, todos = [], [], []
    try:
        f = open(path, encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    with f:
        for line in f:
            if '"message"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("isSidechain") or d.get("isMeta") or d.get("isCompactSummary"):
                continue
            c = (d.get("message") or {}).get("content")
            if d.get("type") == "user":
                t = _text(c).strip()
                if t and not t.startswith(("<command-", "<local-command", "<system-reminder", "<task-notification", "Caveat:")):
                    prompts.append(" ".join(t.split())[:400])
            elif isinstance(c, list):
                for b in c:
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    i = b.get("input") or {}
                    if b.get("name") in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                        p = i.get("file_path") or i.get("notebook_path")
                        if p and p not in files:
                            files.append(p)
                    elif b.get("name") == "TodoWrite":
                        todos = i.get("todos") or todos
    if not prompts:
        return ""
    parts = ["Первый запрос (цель): " + prompts[0]]
    if len(prompts) > 1:
        parts.append("Последние запросы:\n" + "\n".join("- " + p for p in prompts[1:][-4:]))
    if files:
        parts.append("Изменённые файлы: " + ", ".join(files[-15:]))
    if todos:
        parts.append("Список задач:\n" + "\n".join(f"- [{t.get('status', '?')}] {t.get('content', '')}" for t in todos[:15]))
    return "\n\n".join(parts)[:SNAP_MAX]


def install_statusline(data_dir):
    """Keep a copy of statusline.py at a path that survives plugin updates (the data dir)."""
    try:
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statusline.py")
        dst = os.path.join(data_dir, "statusline.py")
        new = open(src, "rb").read()
        if not os.path.exists(dst) or open(dst, "rb").read() != new:
            os.makedirs(data_dir, exist_ok=True)
            open(dst, "wb").write(new)
    except OSError:
        pass


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.claude/ctx_guard")
    inp = json.load(sys.stdin)
    if inp.get("agent_id"):           # subagents: their context is small and separate
        return
    ev = inp.get("hook_event_name", "")
    hp = handoff_path(inp.get("cwd"))
    snap_p = os.path.join(data_dir, f"{inp.get('session_id', 'x')}.auto.md")

    if ev == "PreCompact":              # fallback state, in case the model never wrote handoff.md
        s = snapshot(inp.get("transcript_path", ""))
        if s:
            os.makedirs(data_dir, exist_ok=True)
            open(snap_p, "w", encoding="utf-8").write(s)
        return

    if ev == "SessionStart":
        install_statusline(data_dir)
        src = inp.get("source")
        if src == "compact":
            parts = []
            if os.path.exists(hp):
                parts.append(f"Состояние работы из {hp} ({age_text(hp)}; точнее, чем выжимка):\n\n"
                             + open(hp, encoding="utf-8", errors="ignore").read()[:HANDOFF_MAX - SNAP_MAX])
            if os.path.exists(snap_p):
                parts.append("Автоснимок из истории перед сжатием:\n\n" + open(snap_p, encoding="utf-8").read())
            if parts:
                out(ev, "Чат был автоматически сжат.\n\n" + "\n\n---\n\n".join(parts))
            return
        if not os.path.exists(hp):
            return
        if time.time() - os.path.getmtime(hp) < 24 * 3600:
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
    prev = st.get("last", 0)
    st = {"size_mark": st.get("size_mark", 0), "warn_mark": st.get("warn_mark", 0), "last": n}
    msgs = []
    if n >= st["size_mark"] + STEP or st["size_mark"] == 0:
        st["size_mark"] = n // STEP * STEP
        msgs.append(f"Размер чата сейчас ≈ {n // 1000} тыс. токенов: каждый шаг модели перечитывает его "
                    f"(≈ ${n * OPUS_CACHE_READ:.2f} за шаг на opus). При таком размере исполнение от ~3–4 шагов "
                    f"дешевле отдавать субагентам (haiku/sonnet), а независимые вызовы делать одной пачкой.")
    w = window()
    grow = n - prev if 0 < prev < n else 0
    if grow and n + 2 * grow >= w * 0.95 and n < w and n >= st["warn_mark"] + grow:
        st["warn_mark"] = n            # fast growth: compaction may come within 1-2 steps
        msgs.append(f"Чат растёт быстро (+{grow // 1000} тыс. за шаг), автосжатие (~{w // 1000} тыс.) может "
                    f"наступить через 1–2 шага. Обнови {hp} сейчас, до следующего большого вывода: цель, "
                    f"сделано, решения, пути, следующий шаг.")
    elif n >= w * WARN_SHARE and n >= st["warn_mark"] + WARN_STEP:
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
