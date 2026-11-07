"""Where did this session's money go? Cost report for a Claude Code session, at API list prices.

Usage: python session_report.py [session_id | path/to/session.jsonl]
Without an argument it takes the most recently written session (the current one).
Shows: the main chat (re-reading, new context, replies), subagents, compactions,
the biggest tool outputs that bloated the chat, and what to change.
"""
import glob, json, os, sys

# $ per million tokens: input, cache write, cache read, output
PRICE = {"opus": (5, 6.25, 0.5, 25), "sonnet": (3, 3.75, 0.3, 15), "haiku": (1, 1.25, 0.1, 5)}


def fam(model):
    return next((k for k in PRICE if k in (model or "")), "opus")


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def find_session(arg):
    if arg and os.path.isfile(arg):
        return arg
    files = glob.glob(os.path.join(config_dir(), "projects", "*", "*.jsonl"))
    if arg and not arg.startswith("$"):   # a session id: only that session, never a neighbour
        files = [f for f in files if os.path.basename(f) == arg + ".jsonl"]
    return max(files, key=os.path.getmtime) if files else None


def _short(inp):
    for k in ("file_path", "command", "pattern", "url", "query", "description", "prompt"):
        if inp.get(k):
            return " ".join(str(inp[k]).split())[:70]
    return ""


def _size(content):
    if isinstance(content, str):
        return len(content)
    n = 0
    for b in content or []:
        if isinstance(b, dict):
            n += len(b.get("text") or "") if b.get("type") == "text" else 1500 if b.get("type") == "image" else 0
    return n


def scan(path, main=True):
    seen, tools, results = set(), {}, []
    t = {"inp": 0, "cw": 0, "cr": 0, "out": 0, "cost": 0.0, "steps": 0, "model": None, "compactions": 0, "max_ctx": 0}
    for line in open(path, encoding="utf-8", errors="ignore"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if main and d.get("isSidechain"):
            continue
        if d.get("type") == "system" and d.get("subtype") == "compact_boundary":
            t["compactions"] += 1
        m = d.get("message") or {}
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        if d.get("type") == "assistant":
            for b in c or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tools[b.get("id")] = (b.get("name"), _short(b.get("input") or {}))
            mid = m.get("id")
            if mid in seen or m.get("model") in (None, "<synthetic>"):
                continue
            seen.add(mid)
            u = m.get("usage") or {}
            p = PRICE[fam(m.get("model"))]
            i, w, r, o = (u.get("input_tokens", 0), u.get("cache_creation_input_tokens", 0),
                          u.get("cache_read_input_tokens", 0), u.get("output_tokens", 0))
            t["inp"] += i; t["cw"] += w; t["cr"] += r; t["out"] += o; t["steps"] += 1
            t["max_ctx"] = max(t["max_ctx"], i + w + r)
            t["cost"] += (i * p[0] + w * p[1] + r * p[2] + o * p[3]) / 1e6
            t["model"] = t["model"] or fam(m.get("model"))
            t.setdefault("parts", [0.0, 0.0, 0.0])
            t["parts"][0] += r * p[2] / 1e6               # re-reading the chat
            t["parts"][1] += (i * p[0] + w * p[1]) / 1e6  # new text entering the chat
            t["parts"][2] += o * p[3] / 1e6               # replies + thinking
        elif d.get("type") == "user" and isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    name, what = tools.get(b.get("tool_use_id"), ("?", ""))
                    results.append((_size(b.get("content")), name, what))
    t["results"] = results
    return t


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    path = find_session(sys.argv[1] if len(sys.argv) > 1 else "")
    if not path:
        print("Сессия не найдена: в ней ещё нет записанных шагов.")
        return
    m = scan(path)
    if not m["steps"]:
        print("В этой сессии ещё нет шагов модели — считать пока нечего.")
        return
    sub_dir = os.path.join(os.path.splitext(path)[0], "subagents")
    subs = []
    for f in glob.glob(os.path.join(sub_dir, "agent-*.jsonl")):
        s = scan(f, main=False)
        meta = {}
        try:
            meta = json.load(open(f[:-6] + ".meta.json", encoding="utf-8"))
        except (OSError, ValueError):
            pass
        s["desc"] = (meta.get("description") or meta.get("agentType") or os.path.basename(f))[:45]
        subs.append(s)
    sub_cost = sum(s["cost"] for s in subs)
    total = m["cost"] + sub_cost
    rr, new, outp = m.get("parts", [0, 0, 0])

    def pc(x):
        return f"{x / total:.0%}" if total else "0%"

    print(f"Сессия {os.path.basename(path)[:8]}… — ≈ ${total:.2f} по ценам API\n")
    print(f"Главный чат ({m['model'] or '?'}): ${m['cost']:.2f} ({pc(m['cost'])}), шагов {m['steps']}, "
          f"самый большой контекст {m['max_ctx'] // 1000} тыс., сжатий {m['compactions']}")
    print(f"  перечитывание истории  ${rr:.2f} ({pc(rr)})")
    print(f"  новый текст в чате     ${new:.2f} ({pc(new)})  — выводы команд, файлы, сообщения")
    print(f"  ответы и размышления   ${outp:.2f} ({pc(outp)})")
    if subs:
        print(f"Субагенты: {len(subs)} шт., ${sub_cost:.2f} ({pc(sub_cost)})")
        for s in sorted(subs, key=lambda s: -s["cost"])[:5]:
            print(f"  {s['desc']:45} {s['model'] or '?':6} ${s['cost']:.2f}, шагов {s['steps']}")
    big = sorted(m["results"], key=lambda r: -r[0])[:5]
    big = [b for b in big if b[0] > 8000]
    if big:
        print("Крупнейшие выводы в главном чате (каждый перечитывается всеми следующими шагами):")
        for n, name, what in big:
            print(f"  ~{n // 2500} тыс. ток.  {name}: {what}")

    tips = []
    if total and new / total > 0.35 and big:
        tips.append("Больше всего стоит новый текст: большие выводы читай частями (Grep, Read с offset/limit) "
                    "или отдавай субагенту с коротким итогом.")
    if total and rr / total > 0.35:
        tips.append("Больше всего стоит перечитывание длинной истории: сжимай чат между этапами "
                    "(/compact или .handoff.md + /clear), механику отдавай субагентам.")
    if total and outp / total > 0.3 and m["model"] == "opus":
        tips.append("Много стоят ответы и размышления: для рутины хватит effort medium (/effort medium).")
    if subs and m["cost"] and sub_cost > m["cost"]:
        tips.append("Субагенты дороже главного чата: давай им меньше, но более крупных заданий; "
                    "для простых — haiku (task-router-general:worker).")
    if tips:
        print("\nЧто поменять:")
        for x in tips:
            print("  - " + x)


if __name__ == "__main__":
    main()
