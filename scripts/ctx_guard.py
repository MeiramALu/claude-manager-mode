"""Context guard for the task-router-general plugin.

Hook events:
  PostToolUse / UserPromptSubmit — tells the model the real chat size (once per +STEP tokens),
      and near the auto-compact threshold asks it to keep .handoff.md (project root) up to date.
  PreCompact — saves a mechanical snapshot (goal, recent requests, changed files, todos) as a fallback.
  SessionStart (compact) — puts .handoff.md and the snapshot back into context after compaction.
  SessionStart (startup/clear/resume) — mentions an unfinished handoff.md if it is fresh.
  PreToolUse (Read) — stops the first whole-file read of a big text file once and suggests reading
      a part, searching or delegating; repeating the same Read goes through.

Usage in hooks.json: python ctx_guard.py <data_dir>. Never fails the session: any error -> silent exit 0.
"""
import json, os, sys, time

STEP = 50_000            # report chat size every +50k tokens
FIRST = 50_000           # first report at 50k
WARN_SHARE = 0.7         # handoff reminder from 70% of the auto-compact point
WARN_STEP = 15_000       # repeat the handoff reminder every +15k
HANDOFF_MAX = 9_000      # chars injected after compaction (handoff.md + auto snapshot)
SNAP_MAX = 3_000         # chars of the automatic snapshot
OPUS_CACHE_READ = 0.5e-6  # $ per token
OPUS_CACHE_WRITE = 6.25e-6
BIG_READ_TOKENS = 8_000   # whole-file Read above this is stopped once (env TRG_BIG_READ_TOKENS, 0 = off)
BINARY_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".pdf", ".ipynb", ".svg")


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
    """Token count at which Claude Code auto-compacts.

    Claude Code compacts at window - 20k (reserved for the reply) - 13k (buffer),
    e.g. ~117k for a 150k window. Measured: compactions at 117k-126k with a 150k window.
    """
    v = os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW", "").lower().replace("_", "")
    try:
        w = int(float(v[:-1]) * 1000) if v.endswith("k") else int(v)
    except ValueError:
        w = 200_000
    pct = os.environ.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE")
    if pct and pct.isdigit():
        return int((w - 20_000) * int(pct) / 100)
    return max(w - 33_000, w // 2)


def handoff_path(cwd):
    """.handoff.md in the project root. Not inside .claude/: Claude Code asks permission to write there,
    which would stop an unattended session. The old .claude/handoff.md is still read if it is the only one."""
    new = os.path.normpath(os.path.join(cwd or ".", ".handoff.md"))
    old = os.path.normpath(os.path.join(cwd or ".", ".claude", "handoff.md"))
    return old if os.path.exists(old) and not os.path.exists(new) else new


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


def est_tokens(path):
    """Rough token count of a text file: ~2 bytes per token for logs/code (Read adds line numbers), ~4.5 for Cyrillic UTF-8."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(8000)
    if 0 in head:
        return 0                        # binary
    wide = sum(1 for b in head if b >= 0x80) / max(1, len(head))
    return int(size / (2 + 2.5 * wide))


def big_read(inp, data_dir):
    i = inp.get("tool_input") or {}
    p = i.get("file_path") or ""
    lim = os.environ.get("TRG_BIG_READ_TOKENS", "")
    lim = int(lim) if lim.isdigit() else BIG_READ_TOKENS
    if not lim or not p or i.get("offset") or i.get("limit") or i.get("pages") or p.lower().endswith(BINARY_EXT):
        return
    try:
        n = est_tokens(p)
    except OSError:
        return
    if n < lim:
        return
    sp = os.path.join(data_dir, f"{inp.get('session_id', 'x')}.reads.json")
    try:
        seen = json.load(open(sp))
    except (OSError, ValueError):
        seen = []
    key = os.path.normcase(os.path.abspath(p))
    if key in seen:                     # second attempt: the model decided it needs the whole file
        return
    os.makedirs(data_dir, exist_ok=True)
    json.dump(seen + [key], open(sp, "w"))
    reason = (f"Файл большой: ~{n // 1000} тыс. токенов. Целиком он останется в чате до сжатия "
              f"(≈ ${n * OPUS_CACHE_WRITE:.2f} один раз и ещё ≈ ${n * OPUS_CACHE_READ:.3f} за каждый следующий шаг). "
              f"Если нужна часть — найди её через Grep или Bash (grep -n, wc, head) и прочитай Read с offset/limit. "
              f"Если нужно разобрать весь файл — отдай это субагенту (task-router-general:worker) и попроси короткий итог. "
              f"Если файл действительно нужен целиком — повтори этот же Read, второй раз он пройдёт.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}, ensure_ascii=True))


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.claude/ctx_guard")
    inp = json.load(sys.stdin)
    if inp.get("agent_id"):           # subagents: their context is small and separate
        return
    ev = inp.get("hook_event_name", "")
    if ev == "PreToolUse":
        if inp.get("tool_name") == "Read":
            big_read(inp, data_dir)
        return
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
    if grow and n + 2 * grow >= w and n < w and n >= st["warn_mark"] + grow:
        st["warn_mark"] = n            # fast growth: compaction may come within 1-2 steps
        msgs.append(f"Чат растёт быстро (+{grow // 1000} тыс. за шаг), автосжатие (~{w // 1000} тыс.) может "
                    f"наступить через 1–2 шага. Обнови {hp} сейчас, до следующего большого вывода: цель, "
                    f"сделано, решения, пути, следующий шаг. Когда вся задача будет готова — удали этот файл.")
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
