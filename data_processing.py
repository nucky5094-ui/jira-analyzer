import csv
import io

import numpy as np
import pandas as pd


def read_csv_file(uploaded_file):
    """Читает CSV Jira и пытается определить кодировку и разделитель."""
    raw_data = uploaded_file.getvalue()
    encodings = ["utf-8-sig", "utf-8", "cp1251"]
    last_error = None

    for encoding in encodings:
        try:
            text = raw_data.decode(encoding)

            try:
                dialect = csv.Sniffer().sniff(text[:10000], delimiters=";,|\t,")
                separator = dialect.delimiter
            except csv.Error:
                separator = ";"

            dataframe = pd.read_csv(
                io.StringIO(text),
                sep=separator,
                engine="python",
            )
            dataframe.columns = dataframe.columns.astype(str).str.strip()
            return dataframe, separator, encoding

        except (UnicodeDecodeError, pd.errors.ParserError) as error:
            last_error = error

    raise ValueError(
        "Не удалось прочитать CSV-файл. Проверьте кодировку и структуру файла."
    ) from last_error


def parse_jira_dates(series):
    """Преобразует даты Jira в datetime."""
    cleaned = series.replace(r"^\s*$", np.nan, regex=True)

    result = pd.to_datetime(
        cleaned,
        format="%d/%m/%y %H:%M",
        errors="coerce",
    )

    missing_mask = result.isna() & cleaned.notna()
    if missing_mask.any():
        fallback = pd.to_datetime(
            cleaned.loc[missing_mask],
            dayfirst=True,
            errors="coerce",
        )
        result.loc[missing_mask] = fallback

    return result


def normalize_issue_type(data):
    """Возвращает нормализованный Issue Type и маску пустых значений."""
    if "Issue Type" not in data.columns:
        return None, None

    raw = data["Issue Type"].replace(r"^\s*$", np.nan, regex=True)
    normalized = raw.astype("string").str.strip()
    return normalized, raw.isna()


def get_issue_types(dataframe):
    """Возвращает отсортированный список непустых типов задач."""
    if "Issue Type" not in dataframe.columns:
        return []

    issue_types = (
        dataframe["Issue Type"]
        .replace(r"^\s*$", np.nan, regex=True)
        .dropna()
        .astype(str)
        .str.strip()
    )
    return sorted(issue_types.unique().tolist())


def apply_issue_type_filter(data, selected_types):
    """Применяет общий фильтр по Issue Type к подготовленному набору данных."""
    if data.empty or selected_types is None or "Issue Type" not in data.columns:
        return data.copy()

    return data[data["Issue Type"].astype(str).isin(selected_types)].copy()
