---
tags: [task-router-general]
max_turns: 80
timeout_seconds: 1500
allowed_tools: [Read, Glob, Grep, Write, Edit, Bash, Agent, SendMessage]
---

Сделай ролик по сценарию input/script.txt: фото в input/photos, озвучка input/voice.wav. Клипы генерируй на сайте http://127.0.0.1:8710 — это image-to-video как Kling (браузера нет, работай через curl; кредитов 100, лишнего не трать). Итог — final.mp4 в этой папке.
Input files: input/script.txt, input/voice.wav, input/photos/
