Jira Flow Analyzer — структура после рефакторинга

Файлы:
- app.py — только интерфейс Streamlit и связывание модулей.
- data_processing.py — загрузка CSV, разбор дат, общие фильтры.
- data_quality.py — правила качества данных для каждой метрики.
- metrics.py — расчёты Lead Time, перцентилей и Throughput.
- charts.py — Plotly-графики.
- tables.py — подготовка таблиц для интерфейса.

Как установить:
1. Поместите все .py файлы в одну папку проекта.
2. Старый app.py предварительно сохраните как app_backup.py.
3. Запускайте как раньше:
   streamlit run app.py
