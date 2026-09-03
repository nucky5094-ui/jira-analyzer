import csv
import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# -----------------------------
# Настройки страницы
# -----------------------------
st.set_page_config(
    page_title="Jira Cycle Time Analyzer",
    page_icon="📊",import csv
import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="Jira Cycle Time Analyzer",
    page_icon="📊",
    layout="wide",
)


REQUIRED_COLUMNS = {"Issue Type", "Created", "Resolved"}


def read_csv_file(uploaded_file):
    """Читает CSV-файл Jira и пытается определить кодировку и разделитель."""
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
    result = pd.to_datetime(
        series,
        format="%d/%m/%y %H:%M",
        errors="coerce",
    )

    missing_mask = result.isna() & series.notna()

    if missing_mask.any():
        fallback = pd.to_datetime(
            series.loc[missing_mask],
            dayfirst=True,
            errors="coerce",
        )
        result.loc[missing_mask] = fallback

    return result


def prepare_data(dataframe):
    """Проверяет данные и рассчитывает количество дней до закрытия."""
    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"В CSV отсутствуют обязательные колонки: {missing_text}"
        )

    data = dataframe.copy()

    data["Issue Type"] = (
        data["Issue Type"]
        .fillna("Без типа")
        .astype(str)
        .str.strip()
    )

    data["_Created"] = parse_jira_dates(data["Created"])
    data["_Resolved"] = parse_jira_dates(data["Resolved"])

    invalid_date_mask = data["_Created"].isna() | data["_Resolved"].isna()
    invalid_date_count = int(invalid_date_mask.sum())

    delta_seconds = (
        data["_Resolved"] - data["_Created"]
    ).dt.total_seconds()

    negative_mask = delta_seconds < 0
    negative_count = int(negative_mask.fillna(False).sum())

    valid_mask = (~invalid_date_mask) & (~negative_mask.fillna(False))
    data = data.loc[valid_mask].copy()

    delta_seconds = (
        data["_Resolved"] - data["_Created"]
    ).dt.total_seconds()

    data["Days to Resolve"] = np.floor(
        delta_seconds / 86400
    ).astype(int)

    return data, invalid_date_count, negative_count


def build_frequency_table(filtered_data, day_limit=None):
    """Строит частотную таблицу и формирует текущую выборку."""
    total_tasks = len(filtered_data)

    if day_limit is None:
        visible_data = filtered_data.copy()
    else:
        visible_data = filtered_data[
            filtered_data["Days to Resolve"] <= day_limit
        ].copy()

    frequency = (
        visible_data
        .groupby("Days to Resolve")
        .size()
        .reset_index(name="Количество задач")
        .sort_values("Days to Resolve")
    )

    if total_tasks > 0 and not frequency.empty:
        frequency["Доля"] = (
            frequency["Количество задач"] / total_tasks * 100
        )
    else:
        frequency["Доля"] = pd.Series(dtype=float)

    return frequency, visible_data


def build_chart(frequency):
    """Создаёт интерактивную частотную диаграмму."""
    chart_data = frequency.copy()
    chart_data["День"] = chart_data["Days to Resolve"].astype(str)

    custom_data = np.column_stack(
        (
            chart_data["Days to Resolve"],
            chart_data["Доля"],
        )
    )

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=chart_data["День"],
            y=chart_data["Количество задач"],
            customdata=custom_data,
            hovertemplate=(
                "Дней до закрытия: %{customdata[0]:.0f}"
                "<br>Количество задач: %{y}"
                "<br>Доля среди выбранных задач: %{customdata[1]:.1f}%"
                "<extra></extra>"
            ),
            name="Количество задач",
        )
    )

    fig.update_layout(
        title={
            "text": "Распределение задач по времени закрытия",
            "x": 0.01,
            "xanchor": "left",
        },
        xaxis_title="Количество дней до закрытия",
        yaxis_title="Количество задач",
        hovermode="closest",
        bargap=0.12,
        height=620,
        margin=dict(l=40, r=30, t=80, b=80),
    )

    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=chart_data["День"].tolist(),
    )

    fig.update_yaxes(
        rangemode="tozero",
        dtick=1,
    )

    return fig


def build_task_table(visible_data):
    """
    Формирует список задач, попавших в текущий фильтр и диапазон.
    Необязательные поля показываются только если они есть в CSV.
    """
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

    columns.extend([
        "Created_display",
        "Resolved_display",
        "Days to Resolve",
    ])

    rename_map.update({
        "Created_display": "Создана",
        "Resolved_display": "Закрыта",
        "Days to Resolve": "Дней до закрытия",
    })

    table = table[columns].rename(columns=rename_map)

    # Самые долгие задачи сверху.
    table = table.sort_values(
        by="Дней до закрытия",
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)

    return table


st.title("Jira Cycle Time Analyzer")
st.write(
    "Загрузите CSV-выгрузку из Jira. "
    "Приложение рассчитает время от **Created** до **Resolved** "
    "и покажет частотное распределение по полным календарным суткам."
)

uploaded_file = st.file_uploader(
    "Загрузить CSV из Jira",
    type=["csv"],
)

if uploaded_file is None:
    st.info("Выберите CSV-файл, чтобы начать анализ.")
    st.stop()


try:
    source_df, detected_separator, detected_encoding = read_csv_file(
        uploaded_file
    )
    data, invalid_date_count, negative_count = prepare_data(source_df)

except Exception as error:
    st.error(f"Не удалось обработать файл: {error}")
    st.stop()


if data.empty:
    st.error(
        "После проверки дат не осталось задач, которые можно анализировать."
    )
    st.stop()


if invalid_date_count > 0:
    st.warning(
        f"Не учтено строк с пустыми или некорректными датами: "
        f"{invalid_date_count}."
    )

if negative_count > 0:
    st.warning(
        f"Не учтено строк, где Resolved раньше Created: "
        f"{negative_count}."
    )


issue_types = sorted(data["Issue Type"].unique().tolist())

selected_types = st.multiselect(
    "Тип задачи",
    options=issue_types,
    default=issue_types,
    help="Можно выбрать один, несколько или все типы задач.",
)

if not selected_types:
    st.info("Выберите хотя бы один тип задачи.")
    st.stop()


filtered_data = data[
    data["Issue Type"].isin(selected_types)
].copy()


display_option = st.radio(
    "Диапазон отображения",
    options=[
        "До 30 дней",
        "До 90 дней",
        "Все задачи",
    ],
    index=0,
    horizontal=True,
    help=(
        "Диапазон меняет и диаграмму, и список задач под ней."
    ),
)

day_limit_map = {
    "До 30 дней": 30,
    "До 90 дней": 90,
    "Все задачи": None,
}

day_limit = day_limit_map[display_option]

frequency, visible_data = build_frequency_table(
    filtered_data,
    day_limit=day_limit,
)

if frequency.empty:
    st.warning(
        "Для выбранных типов задач и диапазона нет данных для отображения."
    )
    st.stop()


total_tasks = len(filtered_data)
visible_tasks = len(visible_data)
hidden_tasks = total_tasks - visible_tasks

if hidden_tasks > 0:
    st.caption(
        f"Выбрано задач: {total_tasks}. "
        f"На диаграмме и в списке показано: {visible_tasks}. "
        f"За пределами выбранного диапазона: {hidden_tasks}."
    )
else:
    st.caption(
        f"Выбрано задач: {total_tasks}. "
        f"На диаграмме и в списке показаны все выбранные задачи."
    )


fig = build_chart(frequency)

plotly_config = {
    "displaylogo": False,
    "scrollZoom": True,
    "toImageButtonOptions": {
        "format": "png",
        "filename": "jira_cycle_time_distribution",
        "height": 800,
        "width": 1400,
        "scale": 2,
    },
}

st.plotly_chart(
    fig,
    use_container_width=True,
    config=plotly_config,
)

st.caption(
    "Время рассчитано от Created до Resolved. "
    "1 день = полные 24 часа."
)


# -----------------------------
# Список задач
# -----------------------------
st.subheader(f"Задачи в текущей выборке — {visible_tasks}")

st.caption(
    "Здесь показаны те же задачи, которые участвуют в построении диаграммы. "
    "Самые долгие задачи расположены сверху."
)

task_table = build_task_table(visible_data)

st.dataframe(
    task_table,
    use_container_width=True,
    hide_index=True,
    height=500,
    column_config={
        "Название": st.column_config.TextColumn(width="large"),
        "Ключ": st.column_config.TextColumn(width="small"),
        "Тип": st.column_config.TextColumn(width="small"),
        "Статус": st.column_config.TextColumn(width="small"),
        "Исполнитель": st.column_config.TextColumn(width="medium"),
        "Создана": st.column_config.TextColumn(width="medium"),
        "Закрыта": st.column_config.TextColumn(width="medium"),
        "Дней до закрытия": st.column_config.NumberColumn(
            width="small",
            format="%d",
        ),
    },
)


# -----------------------------
# Скачивание PNG
# -----------------------------
try:
    png_bytes = fig.to_image(
        format="png",
        width=1400,
        height=800,
        scale=2,
    )

    st.download_button(
        label="Скачать диаграмму PNG",
        data=png_bytes,
        file_name="jira_cycle_time_distribution.png",
        mime="image/png",
        use_container_width=False,
    )

except Exception:
    st.info(
        "Отдельная кнопка скачивания PNG сейчас недоступна. "
        "Диаграмму всё равно можно скачать: наведите курсор на график "
        "и нажмите значок камеры в панели Plotly."
    )


with st.expander("Информация о загруженном файле"):
    st.write(f"Строк в исходном файле: {len(source_df)}")
    st.write(f"Задач после проверки данных: {len(data)}")
    st.write(f"Определённый разделитель CSV: `{detected_separator}`")
    st.write(f"Определённая кодировка: `{detected_encoding}`")

    layout="wide",
)


REQUIRED_COLUMNS = {"Issue Type", "Created", "Resolved"}


def read_csv_file(uploaded_file):
    """
    Читает CSV-файл Jira.
    Пытается определить кодировку и разделитель автоматически.
    """
    raw_data = uploaded_file.getvalue()

    # Самые вероятные кодировки для выгрузки Jira.
    encodings = ["utf-8-sig", "utf-8", "cp1251"]

    last_error = None

    for encoding in encodings:
        try:
            text = raw_data.decode(encoding)

            # Пытаемся определить разделитель автоматически.
            try:
                dialect = csv.Sniffer().sniff(text[:10000], delimiters=";,|\t,")
                separator = dialect.delimiter
            except csv.Error:
                # Для Jira чаще всего используется ";"
                separator = ";"

            dataframe = pd.read_csv(
                io.StringIO(text),
                sep=separator,
                engine="python",
            )

            # Убираем случайные пробелы из названий колонок.
            dataframe.columns = dataframe.columns.astype(str).str.strip()

            return dataframe, separator, encoding

        except (UnicodeDecodeError, pd.errors.ParserError) as error:
            last_error = error

    raise ValueError(
        "Не удалось прочитать CSV-файл. "
        "Проверьте кодировку и структуру файла."
    ) from last_error


def parse_jira_dates(series):
    """
    Преобразует даты Jira в datetime.
    Основной ожидаемый формат: день/месяц/год часы:минуты.
    """
    result = pd.to_datetime(
        series,
        format="%d/%m/%y %H:%M",
        errors="coerce",
    )

    # Если часть дат имеет другой формат, пытаемся распознать их отдельно.
    missing_mask = result.isna() & series.notna()

    if missing_mask.any():
        fallback = pd.to_datetime(
            series.loc[missing_mask],
            dayfirst=True,
            errors="coerce",
        )
        result.loc[missing_mask] = fallback

    return result


def prepare_data(dataframe):
    """
    Проверяет обязательные колонки и рассчитывает время закрытия задачи.
    Возвращает:
    - очищенные данные;
    - количество строк с некорректными датами;
    - количество строк с отрицательным временем закрытия.
    """
    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"В CSV отсутствуют обязательные колонки: {missing_text}"
        )

    data = dataframe.copy()

    # Нормализуем тип задачи.
    data["Issue Type"] = (
        data["Issue Type"]
        .fillna("Без типа")
        .astype(str)
        .str.strip()
    )

    data["_Created"] = parse_jira_dates(data["Created"])
    data["_Resolved"] = parse_jira_dates(data["Resolved"])

    invalid_date_mask = data["_Created"].isna() | data["_Resolved"].isna()
    invalid_date_count = int(invalid_date_mask.sum())

    # Считаем фактически прошедшее время в секундах.
    delta_seconds = (
        data["_Resolved"] - data["_Created"]
    ).dt.total_seconds()

    negative_mask = delta_seconds < 0
    negative_count = int(negative_mask.fillna(False).sum())

    # Оставляем только строки, которые можно корректно анализировать.
    valid_mask = (~invalid_date_mask) & (~negative_mask.fillna(False))
    data = data.loc[valid_mask].copy()

    delta_seconds = (
        data["_Resolved"] - data["_Created"]
    ).dt.total_seconds()

    # Количество ПОЛНЫХ 24-часовых суток до закрытия.
    # 23 часа -> 0 дней
    # 1 день 5 часов -> 1 день
    data["Days to Resolve"] = np.floor(
        delta_seconds / 86400
    ).astype(int)

    return data, invalid_date_count, negative_count


def build_frequency_table(filtered_data, day_limit=None):
    """
    Строит таблицу частот для диаграммы.
    day_limit влияет только на то, какие дни показываются на графике.
    """
    total_tasks = len(filtered_data)

    if day_limit is None:
        visible_data = filtered_data.copy()
    else:
        visible_data = filtered_data[
            filtered_data["Days to Resolve"] <= day_limit
        ].copy()

    frequency = (
        visible_data
        .groupby("Days to Resolve")
        .size()
        .reset_index(name="Количество задач")
        .sort_values("Days to Resolve")
    )

    if total_tasks > 0 and not frequency.empty:
        frequency["Доля"] = (
            frequency["Количество задач"] / total_tasks * 100
        )
    else:
        frequency["Доля"] = pd.Series(dtype=float)

    return frequency, visible_data


def build_chart(frequency):
    """
    Создаёт интерактивную частотную диаграмму Plotly.
    """
    chart_data = frequency.copy()

    # Используем категориальную ось X:
    # пустые значения дней не создают пустые столбцы на диаграмме.
    chart_data["День"] = chart_data["Days to Resolve"].astype(str)

    custom_data = np.column_stack(
        (
            chart_data["Days to Resolve"],
            chart_data["Доля"],
        )
    )

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=chart_data["День"],
            y=chart_data["Количество задач"],
            customdata=custom_data,
            hovertemplate=(
                "Дней до закрытия: %{customdata[0]:.0f}"
                "<br>Количество задач: %{y}"
                "<br>Доля среди выбранных задач: %{customdata[1]:.1f}%"
                "<extra></extra>"
            ),
            name="Количество задач",
        )
    )

    fig.update_layout(
        title={
            "text": "Распределение задач по времени закрытия",
            "x": 0.01,
            "xanchor": "left",
        },
        xaxis_title="Количество дней до закрытия",
        yaxis_title="Количество задач",
        hovermode="closest",
        bargap=0.12,
        height=620,
        margin=dict(l=40, r=30, t=80, b=80),
    )

    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=chart_data["День"].tolist(),
    )

    fig.update_yaxes(
        rangemode="tozero",
        dtick=1,
    )

    return fig


# -----------------------------
# Интерфейс приложения
# -----------------------------
st.title("Jira Cycle Time Analyzer")
st.write(
    "Загрузите CSV-выгрузку из Jira. "
    "Приложение рассчитает время от **Created** до **Resolved** "
    "и покажет частотное распределение по полным календарным суткам."
)

uploaded_file = st.file_uploader(
    "Загрузить CSV из Jira",
    type=["csv"],
)

if uploaded_file is None:
    st.info("Выберите CSV-файл, чтобы начать анализ.")
    st.stop()


try:
    source_df, detected_separator, detected_encoding = read_csv_file(
        uploaded_file
    )
    data, invalid_date_count, negative_count = prepare_data(source_df)

except Exception as error:
    st.error(f"Не удалось обработать файл: {error}")
    st.stop()


if data.empty:
    st.error(
        "После проверки дат не осталось задач, которые можно анализировать."
    )
    st.stop()


if invalid_date_count > 0:
    st.warning(
        f"Не учтено строк с пустыми или некорректными датами: "
        f"{invalid_date_count}."
    )

if negative_count > 0:
    st.warning(
        f"Не учтено строк, где Resolved раньше Created: "
        f"{negative_count}."
    )


issue_types = sorted(data["Issue Type"].unique().tolist())

selected_types = st.multiselect(
    "Тип задачи",
    options=issue_types,
    default=issue_types,
    help="Можно выбрать один, несколько или все типы задач.",
)

if not selected_types:
    st.info("Выберите хотя бы один тип задачи.")
    st.stop()


filtered_data = data[
    data["Issue Type"].isin(selected_types)
].copy()


display_option = st.radio(
    "Диапазон отображения",
    options=[
        "До 30 дней",
        "До 90 дней",
        "Все задачи",
    ],
    index=0,
    horizontal=True,
    help=(
        "Диапазон меняет только масштаб диаграммы. "
        "Фильтр по типу задачи применяется ко всему набору данных."
    ),
)

day_limit_map = {
    "До 30 дней": 30,
    "До 90 дней": 90,
    "Все задачи": None,
}

day_limit = day_limit_map[display_option]

frequency, visible_data = build_frequency_table(
    filtered_data,
    day_limit=day_limit,
)

if frequency.empty:
    st.warning(
        "Для выбранных типов задач и диапазона нет данных для отображения."
    )
    st.stop()


total_tasks = len(filtered_data)
visible_tasks = len(visible_data)
hidden_tasks = total_tasks - visible_tasks

if hidden_tasks > 0:
    st.caption(
        f"Выбрано задач: {total_tasks}. "
        f"На диаграмме показано: {visible_tasks}. "
        f"За пределами выбранного диапазона: {hidden_tasks}."
    )
else:
    st.caption(
        f"Выбрано задач: {total_tasks}. "
        f"На диаграмме показаны все выбранные задачи."
    )


fig = build_chart(frequency)

plotly_config = {
    "displaylogo": False,
    "scrollZoom": True,
    "toImageButtonOptions": {
        "format": "png",
        "filename": "jira_cycle_time_distribution",
        "height": 800,
        "width": 1400,
        "scale": 2,
    },
}

st.plotly_chart(
    fig,
    use_container_width=True,
    config=plotly_config,
)

st.caption(
    "Время рассчитано от Created до Resolved. "
    "1 день = полные 24 часа."
)


# -----------------------------
# Скачивание PNG
# -----------------------------
try:
    png_bytes = fig.to_image(
        format="png",
        width=1400,
        height=800,
        scale=2,
    )

    st.download_button(
        label="Скачать диаграмму PNG",
        data=png_bytes,
        file_name="jira_cycle_time_distribution.png",
        mime="image/png",
        use_container_width=False,
    )

except Exception:
    st.info(
        "Отдельная кнопка скачивания PNG сейчас недоступна. "
        "Диаграмму всё равно можно скачать: наведите курсор на график "
        "и нажмите значок камеры в панели Plotly."
    )


with st.expander("Информация о загруженном файле"):
    st.write(f"Строк в исходном файле: {len(source_df)}")
    st.write(f"Задач после проверки данных: {len(data)}")
    st.write(f"Определённый разделитель CSV: `{detected_separator}`")
    st.write(f"Определённая кодировка: `{detected_encoding}`")

