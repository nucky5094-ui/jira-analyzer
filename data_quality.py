import pandas as pd

from data_processing import normalize_issue_type, parse_jira_dates


def empty_problem_series(index):
    """Создаёт для каждой строки независимый список проблем."""
    return pd.Series([[] for _ in range(len(index))], index=index, dtype=object)


def add_problem(problem_lists, mask, text):
    """Добавляет описание проблемы всем строкам, попавшим под mask."""
    for idx in problem_lists.index[mask]:
        problem_lists.at[idx].append(text)


def prepare_lead_time_data(dataframe):
    """
    Проверяет контракт Lead Time.

    Для расчёта необходимы Created и Resolved.
    Если Issue Type присутствует, пустые значения исключаются, потому что
    тип задачи участвует в общем фильтре приложения.
    """
    data = dataframe.copy()
    required_columns = {"Created", "Resolved"}
    missing_columns = required_columns - set(data.columns)

    if missing_columns:
        return {
            "available": False,
            "missing_columns": sorted(missing_columns),
            "valid_data": pd.DataFrame(),
            "excluded_data": pd.DataFrame(),
        }

    data["_Created"] = parse_jira_dates(data["Created"])
    data["_Resolved"] = parse_jira_dates(data["Resolved"])

    problem_lists = empty_problem_series(data.index)

    created_raw = data["Created"].replace(r"^\s*$", pd.NA, regex=True)
    resolved_raw = data["Resolved"].replace(r"^\s*$", pd.NA, regex=True)

    add_problem(problem_lists, created_raw.isna(), "Не заполнено поле Created")
    add_problem(problem_lists, resolved_raw.isna(), "Не заполнено поле Resolved")
    add_problem(
        problem_lists,
        created_raw.notna() & data["_Created"].isna(),
        "Некорректная дата Created",
    )
    add_problem(
        problem_lists,
        resolved_raw.notna() & data["_Resolved"].isna(),
        "Некорректная дата Resolved",
    )

    negative_mask = (
        data["_Created"].notna()
        & data["_Resolved"].notna()
        & (data["_Resolved"] < data["_Created"])
    )
    add_problem(problem_lists, negative_mask, "Resolved раньше Created")

    issue_type, issue_type_missing = normalize_issue_type(data)
    if issue_type is not None:
        data["Issue Type"] = issue_type
        add_problem(problem_lists, issue_type_missing, "Не заполнено поле Issue Type")

    data["Проблемы данных"] = problem_lists.apply(lambda items: "; ".join(items))

    valid_mask = data["Проблемы данных"].eq("")
    valid_data = data.loc[valid_mask].copy()
    excluded_data = data.loc[~valid_mask].copy()

    if not valid_data.empty:
        delta_seconds = (
            valid_data["_Resolved"] - valid_data["_Created"]
        ).dt.total_seconds()
        valid_data["Lead Time Days"] = delta_seconds / 86400
        valid_data["Lead Time Full Days"] = (
            valid_data["Lead Time Days"].floordiv(1).astype(int)
        )

    return {
        "available": True,
        "missing_columns": [],
        "valid_data": valid_data,
        "excluded_data": excluded_data,
    }


def prepare_throughput_data(dataframe):
    """
    Проверяет контракт Throughput.

    Для расчёта нужен только Resolved.
    Created не требуется и не влияет на пригодность строки.
    """
    data = dataframe.copy()

    if "Resolved" not in data.columns:
        return {
            "available": False,
            "missing_columns": ["Resolved"],
            "valid_data": pd.DataFrame(),
            "excluded_data": pd.DataFrame(),
        }

    data["_Resolved"] = parse_jira_dates(data["Resolved"])
    problem_lists = empty_problem_series(data.index)

    resolved_raw = data["Resolved"].replace(r"^\s*$", pd.NA, regex=True)
    add_problem(problem_lists, resolved_raw.isna(), "Не заполнено поле Resolved")
    add_problem(
        problem_lists,
        resolved_raw.notna() & data["_Resolved"].isna(),
        "Некорректная дата Resolved",
    )

    issue_type, issue_type_missing = normalize_issue_type(data)
    if issue_type is not None:
        data["Issue Type"] = issue_type
        add_problem(problem_lists, issue_type_missing, "Не заполнено поле Issue Type")

    data["Проблемы данных"] = problem_lists.apply(lambda items: "; ".join(items))

    valid_mask = data["Проблемы данных"].eq("")
    valid_data = data.loc[valid_mask].copy()
    excluded_data = data.loc[~valid_mask].copy()

    return {
        "available": True,
        "missing_columns": [],
        "valid_data": valid_data,
        "excluded_data": excluded_data,
    }


def problem_counts_table(excluded_data):
    """Считает количество каждой причины исключения."""
    if excluded_data.empty or "Проблемы данных" not in excluded_data.columns:
        return pd.DataFrame(columns=["Проблема", "Количество"])

    return (
        excluded_data["Проблемы данных"]
        .str.split("; ")
        .explode()
        .value_counts()
        .rename_axis("Проблема")
        .reset_index(name="Количество")
    )
