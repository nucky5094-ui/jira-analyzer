import pandas as pd


def calculate_lead_time_percentiles(data):
    """Возвращает P50/P85/P95 Lead Time в календарных днях."""
    if data.empty:
        return None

    values = data["Lead Time Days"].dropna()
    if values.empty:
        return None

    return {
        "P50": float(values.quantile(0.50)),
        "P85": float(values.quantile(0.85)),
        "P95": float(values.quantile(0.95)),
    }


def build_frequency_table(filtered_data, day_limit=None):
    """Готовит распределение Lead Time и текущую видимую выборку."""
    total_tasks = len(filtered_data)

    if day_limit is None:
        visible_data = filtered_data.copy()
    else:
        visible_data = filtered_data[
            filtered_data["Lead Time Full Days"] <= day_limit
        ].copy()

    frequency = (
        visible_data.groupby("Lead Time Full Days")
        .size()
        .reset_index(name="Количество задач")
        .sort_values("Lead Time Full Days")
    )

    if total_tasks > 0 and not frequency.empty:
        frequency["Доля"] = frequency["Количество задач"] / total_tasks * 100
    else:
        frequency["Доля"] = pd.Series(dtype=float)

    return frequency, visible_data


def build_weekly_throughput(data):
    """Считает Throughput по календарным неделям (пн–вс)."""
    if data.empty:
        return pd.DataFrame(columns=["Неделя", "Закрыто задач"])

    result = data.copy()
    result["_Week"] = result["_Resolved"].dt.to_period("W-SUN").apply(
        lambda period: period.start_time
    )

    weekly = (
        result.groupby("_Week")
        .size()
        .reset_index(name="Закрыто задач")
        .sort_values("_Week")
    )
    weekly["Неделя"] = weekly["_Week"].dt.strftime("%d.%m.%Y")
    return weekly
