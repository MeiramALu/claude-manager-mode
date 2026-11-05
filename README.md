# Manager mode for Claude Code — save tokens in long chats / Режим менеджера — экономия токенов в длинных чатах

[English](#english) · [Русский](#русский)

---

## English

A token-saving Claude Code skill for **any big task**: code, bugs and logs, research, data, documents, browser work, files, video.

In a long chat, every model step re-reads the whole history: ~$0.05 per step at 100k tokens, ~$0.10 at 200k. Most of the spend is re-reading, not work. The skill pulls three levers:
1. **Fewer manager turns**: batched tool calls, scripts instead of command series, short outputs.
2. **Execution in someone else's context**: cheap **Haiku/Sonnet** subagents do the hands-on work in parallel, and the chat model (usually Opus) only plans, decides and checks.
3. **A shorter chat**: it suggests `/compact` or a `handoff.md` + `/clear` between stages.

It also tells the model **when not to delegate**. In a fresh chat, blind delegation often costs *more* than doing the work directly.

### Install

```
/plugin marketplace add MeiramALu/claude-manager-mode
/plugin install task-router-general@claude-manager-mode
```

Use it: `/task-router-general <your task>`, or say "work as a manager" / "delegate to subagents".

### What we measured (Opus 5.5 manager, Nov 2026)

Each run is a separate headless `claude -p` session. Cost = manager + all subagents, at API prices. All runs passed all checks.

| Test | Without skill | Old skill version | **This version** |
|---|---|---|---|
| Video from 3 photos + voice via a Kling-like site (curl), fresh chat | $0.71 · 134 s | $0.80 · 179 s | $0.85 · 190 s |
| Investigate crashes in 48k log lines, fresh chat | $0.35 · 83 s | $0.30 · 57 s | $0.30 · 61 s |
| Small sales report (should NOT delegate) | $0.22 · 49 s | $0.19 · 33 s | $0.23 · 43 s |
| **Same video task in a long chat (~200k tokens of history)** | **$4.18 · 146 s** | — | **$2.36 · 137 s (−43%)** |
| Same log investigation in a long chat (~170k) | $2.14 · 52 s | — | $1.97 · 53 s (−8%) |

Takeaways:
- **Fresh chat + scriptable work** (curl, ffmpeg, grep): Opus doing it itself is just as cheap. The skill now recognises this and doesn't delegate.
- **Long chat**: every Opus step re-reads the whole history (~$0.05–0.10 per step). On a long job, handing the mechanics to a subagent cut the cost by 43%. On a short one (6 steps) the gain was small (−8%): most of the cost is reading the history once, which only compacting the chat removes.
- Each general-purpose subagent costs 15–32k tokens just to start. The plugin ships lean executors (`worker` for shell and files, `web-worker` for web lookups) that start at ~11k instead of ~20k. One Haiku card with two tasks was 3× cheaper than two separate agents.
- Hidden cost: every subagent launch and every completion notice is a full manager turn. Fewer, bigger cards are better.

### Automatic mode: the chat compacts itself, nothing is lost

The plugin ships hooks (`hooks/hooks.json` + `scripts/ctx_guard.py`, needs Python):
- **Real chat size for the model.** Every +50k tokens it tells the model how big the chat is and what one step costs. Without this, models misjudge it, which was the main weakness in our tests.
- **Handoff before compaction.** From 70% of the auto-compact point it asks the model to keep `.handoff.md` in the project root up to date (goal, done, decisions, paths, next step).
- **Fast growth.** If the chat grows so fast that compaction may come within 1–2 steps, it asks for the handoff right away.
- **Auto snapshot.** Right before compaction the hook saves, with no model involved, the first request (the goal), the last requests, the changed files and the todo list. This is a fallback in case the model never wrote `handoff.md`.
- **Restore after compaction.** After every auto or manual compaction, the hook puts `.handoff.md` and the snapshot back into context. Tested: after 3 automatic compactions in a row, the model still had the exact details from the file.

To make Claude Code compact earlier (cheaper steps), add to `~/.claude/settings.json`:
```json
{ "env": { "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "150000", "CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS": "100000" } }
```
The chat then compacts itself at ~117k tokens (Claude Code compacts ~33k below the window: 20k reserved for the reply plus a 13k buffer), or at 100k when you come back after a pause. Combined with the handoff file, that works like an automatic "move to a new chat".

**Status line** (optional): chat size against the compaction threshold, the cost of one step, and the session cost, e.g. `ctx 87k/117k 74% · step ~$0.04 · session $1.23` (117k = the point where the chat compacts). The plugin copies the script to its data folder on every session start, so the path stays the same across updates:
```json
{ "statusLine": { "type": "command", "command": "python ~/.claude/plugins/data/task-router-general-claude-manager-mode/statusline.py" } }
```

### Contents

- `skills/task-router-general/SKILL.md` — the skill (in Russian; models follow it fine in any language).
- `skills/task-router-general/agent_stats.py` — per-subagent cost/time report for a session: `python agent_stats.py ~/.claude/projects/<project>/<session-id>/subagents`
- `agents/` — lean executors `worker` and `web-worker` (Haiku by default).
- `hooks/`, `scripts/ctx_guard.py` — the context guard described above. `scripts/statusline.py` — the status line.
- `evals/` — the 3 test cases. Run them with `claude plugin eval . --scaffold --allow-tools Write,Edit,Bash,Agent` (these are real, billed model runs).

---

## Русский

Скилл экономии токенов для Claude Code — для **любых больших задач**: код, баги и логи, исследования, данные, документы, браузер, файлы, видео.

В длинном чате каждый шаг модели перечитывает всю историю: ~$0.05 за шаг при 100 тыс. токенов, ~$0.10 при 200 тыс. Основные траты — перечитывание, а не работа. Скилл тянет за три рычага:
1. **Меньше ходов менеджера**: вызовы пачкой, скрипты вместо серии команд, короткий вывод.
2. **Исполнение в чужом контексте**: дешёвые субагенты **Haiku/Sonnet** работают руками параллельно, а модель чата (обычно Opus) только планирует, решает и проверяет.
3. **Короче сам чат**: между этапами предлагает `/compact` или перенос через `handoff.md` + `/clear`.

Скилл также знает, **когда раздавать не надо**. В свежем чате слепое делегирование часто выходит дороже, чем сделать самому.

### Установка

```
/plugin marketplace add MeiramALu/claude-manager-mode
/plugin install task-router-general@claude-manager-mode
```

Вызов: `/task-router-general <задача>`, или «работай как менеджер», «раздай субагентам».

### Замеры (менеджер — Opus 5.5, ноябрь 2026)

Каждый прогон — отдельная сессия `claude -p`. Цена — менеджер плюс все субагенты, по ценам API. Все прогоны прошли все проверки.

| Тест | Без скилла | Старая версия | **Эта версия** |
|---|---|---|---|
| Ролик из 3 фото + голос через сайт типа Kling (curl), свежий чат | $0.71 · 134 с | $0.80 · 179 с | $0.85 · 190 с |
| Разбор падений по 48 тыс. строк логов, свежий чат | $0.35 · 83 с | $0.30 · 57 с | $0.30 · 61 с |
| Маленький отчёт по продажам (раздавать не надо) | $0.22 · 49 с | $0.19 · 33 с | $0.23 · 43 с |
| **Тот же ролик в длинном чате (~200 тыс. токенов истории)** | **$4.18 · 146 с** | — | **$2.36 · 137 с (−43%)** |
| Тот же разбор логов в длинном чате (~170 тыс.) | $2.14 · 52 с | — | $1.97 · 53 с (−8%) |

Выводы:
- **Свежий чат и работа скриптами** (curl, ffmpeg, grep): Opus сам справляется так же дёшево. Скилл это распознаёт и не раздаёт.
- **Длинный чат**: каждый шаг Opus перечитывает всю историю (~$0.05–0.10 за шаг). На долгой работе механика, отданная исполнителю, снизила цену на 43%. На короткой (6 шагов) выигрыш небольшой (−8%): основная цена — разовое чтение истории, и убрать её может только сжатие чата.
- Старт обычного субагента стоит 15–32 тыс. токенов. В плагине есть лёгкие исполнители (`worker` — команды и файлы, `web-worker` — поиск в сети): старт ~11 тыс. вместо ~20 тыс. Одна карточка Haiku с двумя задачами вышла в 3 раза дешевле двух отдельных агентов.
- Скрытая цена: каждый запуск и каждое уведомление о завершении — полный ход менеджера. Лучше меньше карточек, но крупнее.

### Автоматический режим: чат сжимается сам, ничего не теряется

В плагине есть хуки (`hooks/hooks.json` + `scripts/ctx_guard.py`, нужен Python):
- **Модель знает реальный размер чата.** Каждые +50 тыс. токенов хук сообщает размер чата и цену одного шага. Без этого модель ошибается — это была главная слабость в тестах.
- **Сохранение перед сжатием.** С 70% порога автосжатия хук просит модель обновлять `.handoff.md` в корне проекта: цель, что сделано, решения, пути, следующий шаг.
- **Быстрый рост.** Если чат растёт так быстро, что сжатие может наступить через 1–2 шага, хук просит обновить handoff сразу.
- **Автоснимок.** Перед сжатием хук сам, без участия модели, сохраняет первый запрос (цель), последние запросы, изменённые файлы и список задач. Это запасной вариант на случай, если модель не записала `handoff.md`.
- **Возврат после сжатия.** После каждого авто- или ручного сжатия хук возвращает `.handoff.md` и автоснимок в контекст. Проверено: после 3 автосжатий подряд модель помнила точные детали из файла.

Чтобы Claude Code сжимал чат раньше (каждый шаг дешевле), добавь в `~/.claude/settings.json`:
```json
{ "env": { "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "150000", "CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS": "100000" } }
```
Тогда чат сам сожмётся при ~117 тыс. токенов (Claude Code сжимает на ~33 тыс. раньше окна: 20 тыс. под ответ и 13 тыс. запаса), а после перерыва — при 100 тыс. Вместе с handoff-файлом это работает как автоматический «перенос в новый чат».

**Строка состояния** (по желанию): размер чата относительно порога сжатия, цена одного шага и цена сессии, например `ctx 87k/117k 74% · step ~$0.04 · session $1.23` (117k — точка, где чат сожмётся). Плагин при каждом старте сессии копирует скрипт в свою папку данных, поэтому путь не меняется при обновлениях:
```json
{ "statusLine": { "type": "command", "command": "python ~/.claude/plugins/data/task-router-general-claude-manager-mode/statusline.py" } }
```

### Состав

- `skills/task-router-general/SKILL.md` — сам скилл.
- `skills/task-router-general/agent_stats.py` — отчёт по расходу субагентов сессии: `python agent_stats.py ~/.claude/projects/<проект>/<id-сессии>/subagents`
- `agents/` — лёгкие исполнители `worker` и `web-worker` (по умолчанию Haiku).
- `hooks/`, `scripts/ctx_guard.py` — контролёр контекста, описанный выше. `scripts/statusline.py` — строка состояния.
- `evals/` — 3 теста. Запуск: `claude plugin eval . --scaffold --allow-tools Write,Edit,Bash,Agent` (это настоящие платные прогоны моделей).

## License

MIT
