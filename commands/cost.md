---
description: Where this session's money went — main chat, subagents, compactions, the biggest outputs, and what to change
allowed-tools: Bash(python:*)
---
Отчёт о расходах этой сессии (цены API):

!`python "${CLAUDE_PLUGIN_ROOT}/scripts/session_report.py" "${CLAUDE_SESSION_ID}"`

Покажи пользователю этот отчёт как есть, без вызова инструментов. Если пользователь спросит, что делать дальше, объясни советы из раздела «Что поменять» простыми словами.
