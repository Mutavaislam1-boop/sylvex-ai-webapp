# SYLVEX — реестр готовности к запуску

- `REGISTER.json` — единый реестр, 79 требований.
- `fixes/*/RESULT.md` — отчёты, на которые ссылается `evidence_catalog`.
- `apply_b09_s705.py`, `apply_b13_b16_s808_sx010.py`, `apply_b15_sx010_close.py`, `apply_s110_restore.py`, `apply_b10_s106_s107.py`, `apply_s106_deployed.py`, `apply_b10_security_close.py`, `apply_b10_mfa_production.py`, `apply_s709_finance.py`, `apply_s709_close.py`, `apply_s106_close_mfa_manual.py`, `apply_b11_inventory.py`, `apply_b11_implementation.py`, `apply_b11_close.py`, `apply_b08_backups.py`, затем `apply_b08_schedule_b09_scope.py` — те же правки, применённые к исходному файлу из библиотеки.
  Порядок запуска:
  ```
  python3 apply_b09_s705.py REGISTER.json step1.json
  python3 apply_b13_b16_s808_sx010.py step1.json step2.json
  python3 apply_b15_sx010_close.py step2.json step3.json
  python3 apply_s110_restore.py step3.json step4.json
  python3 apply_b10_s106_s107.py step4.json step5.json
  python3 apply_s106_deployed.py step5.json step6.json
  python3 apply_b10_security_close.py step6.json step7.json
  python3 apply_b10_mfa_production.py step7.json step8.json
  python3 apply_s709_finance.py step8.json step9.json
  python3 apply_s709_close.py step9.json step10.json
  python3 apply_s106_close_mfa_manual.py step10.json step11.json
  python3 apply_b11_inventory.py step11.json step12.json
  python3 apply_b11_implementation.py step12.json step13.json
  python3 apply_b11_close.py step13.json step14.json
  python3 apply_b08_backups.py step14.json step15.json
  python3 apply_b08_schedule_b09_scope.py step15.json REGISTER.json
  ```
- Пути `evidence_catalog`, которые не начинаются с `fixes/…-production`, указывают на файлы библиотеки владельца. В этот репозиторий они не входят.
