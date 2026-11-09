# SYLVEX — реестр готовности к запуску

- `REGISTER.json` — единый реестр, 79 требований.
- `fixes/*/RESULT.md` — отчёты, на которые ссылается `evidence_catalog`.
- `apply_b09_s705.py`, затем `apply_b13_b16_s808_sx010.py` — те же правки, применённые к исходному файлу из библиотеки.
  Порядок запуска:
  ```
  python3 apply_b09_s705.py REGISTER.json step1.json
  python3 apply_b13_b16_s808_sx010.py step1.json REGISTER.json
  ```
- Пути `evidence_catalog`, которые не начинаются с `fixes/…-production`, указывают на файлы библиотеки владельца. В этот репозиторий они не входят.
