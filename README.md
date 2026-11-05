# Manager mode for Claude Code / Режим менеджера для Claude Code

[English](#english) · [Русский](#русский)

---

## English

A Claude Code skill. The chat model (usually Opus) **thinks**: it plans, writes prompts, and checks results. Cheap **Haiku/Sonnet** subagents do the **hands-on work** — browser clicks, uploads, waiting for generations, repetitive steps — in parallel.

The skill also tells the model **when not to delegate**. In our tests, blind delegation often cost *more* than doing the work directly.

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

Takeaways:
- **Fresh chat + scriptable work** (curl, ffmpeg, grep): Opus doing it itself is just as cheap. The skill now recognises this and doesn't delegate.
- **Long chat**: every Opus step re-reads the whole history (~$0.05–0.10 per step). Handing the mechanics to a subagent cut the cost by 43%.
- Each subagent costs 15–32k tokens just to start. One Haiku card with two tasks was 3× cheaper than two separate agents.
- Hidden cost: every subagent launch and every completion notice is a full manager turn. Fewer, bigger cards are better.

### Contents

- `skills/task-router-general/SKILL.md` — the skill (in Russian; models follow it fine in any language).
- `skills/task-router-general/agent_stats.py` — per-subagent cost/time report for a session: `python agent_stats.py ~/.claude/projects/<project>/<session-id>/subagents`
- `evals/` — the 3 test cases. Run them with `claude plugin eval . --scaffold --allow-tools Write,Edit,Bash,Agent` (these are real, billed model runs).

---

## Русский

Скилл для Claude Code. Модель чата (обычно Opus) **думает**: планирует, пишет промты, проверяет. Дешёвые субагенты **Haiku/Sonnet** работают **руками** — клики в браузере, загрузки, ожидание генераций, однотипные шаги, — параллельно.

Главное отличие — скилл знает, **когда раздавать не надо**. В тестах слепое делегирование часто выходило дороже, чем сделать самому.

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

Выводы:
- **Свежий чат и работа скриптами** (curl, ffmpeg, grep): Opus сам справляется так же дёшево. Скилл это распознаёт и не раздаёт.
- **Длинный чат**: каждый шаг Opus перечитывает всю историю (~$0.05–0.10 за шаг). Механика, отданная исполнителю, снизила цену на 43%.
- Старт любого субагента стоит 15–32 тыс. токенов. Одна карточка Haiku с двумя задачами вышла в 3 раза дешевле двух отдельных агентов.
- Скрытая цена: каждый запуск и каждое уведомление о завершении — полный ход менеджера. Лучше меньше карточек, но крупнее.

### Состав

- `skills/task-router-general/SKILL.md` — сам скилл.
- `skills/task-router-general/agent_stats.py` — отчёт по расходу субагентов сессии: `python agent_stats.py ~/.claude/projects/<проект>/<id-сессии>/subagents`
- `evals/` — 3 теста. Запуск: `claude plugin eval . --scaffold --allow-tools Write,Edit,Bash,Agent` (это настоящие платные прогоны моделей).

## License

MIT
