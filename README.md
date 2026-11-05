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
- Each subagent costs 15–32k tokens just to start. One Haiku card with two tasks was 3× cheaper than two separate agents.
- Hidden cost: every subagent launch and every completion notice is a full manager turn. Fewer, bigger cards are better.

### Contents

- `skills/task-router-general/SKILL.md` — the skill (in Russian; models follow it fine in any language).
- `skills/task-router-general/agent_stats.py` — per-subagent cost/time report for a session: `python agent_stats.py ~/.claude/projects/<project>/<session-id>/subagents`
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
- Старт любого субагента стоит 15–32 тыс. токенов. Одна карточка Haiku с двумя задачами вышла в 3 раза дешевле двух отдельных агентов.
- Скрытая цена: каждый запуск и каждое уведомление о завершении — полный ход менеджера. Лучше меньше карточек, но крупнее.

### Состав

- `skills/task-router-general/SKILL.md` — сам скилл.
- `skills/task-router-general/agent_stats.py` — отчёт по расходу субагентов сессии: `python agent_stats.py ~/.claude/projects/<проект>/<id-сессии>/subagents`
- `evals/` — 3 теста. Запуск: `claude plugin eval . --scaffold --allow-tools Write,Edit,Bash,Agent` (это настоящие платные прогоны моделей).

## License

MIT
