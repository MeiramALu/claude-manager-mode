---
tags: [task-router-general]
max_turns: 80
timeout_seconds: 1500
allowed_tools: [Read, Glob, Grep, Write, Edit, Bash, Agent, SendMessage]
---

У нас всю неделю падал сервис. Логи всех 12 серверов в logs/. Разберись, сколько раз он падал, из-за чего и на каких серверах, и какие ошибки самые частые. Отчёт — в incidents.md.
Input files: logs/
