import pandas as pd


def build_task_table(visible_data):
    """Формирует таблицу задач, участвующих в Lead Time."""
    table = visible_data.copy()
    table["Created_display"] = table["_Created"].dt.strftime("%d.%m.%Y %H:%M")
    table["Resolved_display"] = table["_Resolved"].dt.strftime("%d.%m.%Y %H:%M")

    columns = []
    rename_map = {}
    optional_columns = [
        ("Issue key", "Ключ"),
        ("Summary", "Название"),
        ("Issue Type", "Тип"),
        ("Status", "Статус"),
        ("Assignee", "Исполнитель"),
    ]

    for source_name, display_name in optional_columns:
        if source_name in table.columns:
            columns.append(source_name)
            rename_map[source_name] = display_name

    columns.extend(["Created_display", "Resolved_display", "Lead Time Days"])
    rename_map.update(
        {
            "Created_display": "Создана",
            "Resolved_display": "Закрыта",
            "Lead Time Days": "Lead Time, дней",
        }
    )

    table = table[columns].rename(columns=rename_map)
    table["Lead Time, дней"] = table["Lead Time, дней"].round(1)
    table = table.sort_values(
        by="Lead Time, дней",
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)
    return table


def build_excluded_table(excluded_data):
    """Формирует таблицу исключённых задач с причиной."""
    table = excluded_data.copy()
    columns = []
    rename_map = {}

    optional_columns = [
        ("Issue key", "Ключ"),
        ("Summary", "Название"),
        ("Issue Type", "Тип"),
        ("Status", "Статус"),
        ("Assignee", "Исполнитель"),
        ("Created", "Created"),
        ("Resolved", "Resolved"),
        ("Проблемы данных", "Почему исключена"),
    ]

    for source_name, display_name in optional_columns:
        if source_name in table.columns:
            columns.append(source_name)
            rename_map[source_name] = display_name

    if not columns:
        return pd.DataFrame()

    return table[columns].rename(columns=rename_map).reset_index(drop=True)
