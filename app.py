st.set_page_config(
    page_title="Jira Flow Analyzer",
    page_icon="📊",
    layout="wide",
)


LEAD_TIME_REQUIRED_COLUMNS = {"Created", "Resolved"}


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


def add_problem(problem_lists, mask, text):
    """Добавляет описание проблемы всем строкам, попавшим под mask."""
    for idx in problem_lists.index[mask]:
        problem_lists.at[idx].append(text)


def prepare_lead_time_data(dataframe):
    """
    Готовит данные для Lead Time и отдельно сохраняет строки,
    которые нельзя использовать в этой метрике.
    """
    data = dataframe.copy()

    missing_columns = LEAD_TIME_REQUIRED_COLUMNS - set(data.columns)
    if missing_columns:
        return {
            "available": False,
            "missing_columns": sorted(missing_columns),
            "all_data": data,
            "valid_data": pd.DataFrame(),
            "excluded_data": pd.DataFrame(),
        }

    data["_Created"] = parse_jira_dates(data["Created"])
    data["_Resolved"] = parse_jira_dates(data["Resolved"])

    problem_lists = pd.Series(
        [[] for _ in range(len(data))],
        index=data.index,
        dtype=object,
    )

    created_raw = data["Created"].replace(r"^\s*$", np.nan, regex=True)
    resolved_raw = data["Resolved"].replace(r"^\s*$", np.nan, regex=True)

    created_empty = created_raw.isna()
    resolved_empty = resolved_raw.isna()
    created_invalid = created_raw.notna() & data["_Created"].isna()
    resolved_invalid = resolved_raw.notna() & data["_Resolved"].isna()

    add_problem(problem_lists, created_empty, "Не заполнено поле Created")
    add_problem(problem_lists, resolved_empty, "Не заполнено поле Resolved")
    add_problem(problem_lists, created_invalid, "Некорректная дата Created")
    add_problem(problem_lists, resolved_invalid, "Некорректная дата Resolved")

    negative_mask = (
        data["_Created"].notna()
        & data["_Resolved"].notna()
        & (data["_Resolved"] < data["_Created"])
    )
    add_problem(problem_lists, negative_mask, "Resolved раньше Created")

    if "Issue Type" in data.columns:
        issue_type_raw = data["Issue Type"].replace(r"^\s*$", np.nan, regex=True)
        issue_type_missing = issue_type_raw.isna()
        add_problem(problem_lists, issue_type_missing, "Не заполнено поле Issue Type")

        data["Issue Type"] = issue_type_raw.astype("string").str.strip()

    data["Проблемы данных"] = problem_lists.apply(lambda items: "; ".join(items))

    valid_mask = data["Проблемы данных"].eq("")
    valid_data = data.loc[valid_mask].copy()
    excluded_data = data.loc[~valid_mask].copy()

    if not valid_data.empty:
        delta_seconds = (
            valid_data["_Resolved"] - valid_data["_Created"]
        ).dt.total_seconds()

        valid_data["Lead Time Days"] = np.floor(
            delta_seconds / 86400
        ).astype(int)

    return {
        "available": True,
        "missing_columns": [],
        "all_data": data,
        "valid_data": valid_data,
        "excluded_data": excluded_data,
    }


def build_frequency_table(filtered_data, day_limit=None):
    """Строит частотную таблицу Lead Time и текущую выборку."""
    total_tasks = len(filtered_data)

    if day_limit is None:
        visible_data = filtered_data.copy()
    else:
        visible_data = filtered_data[
            filtered_data["Lead Time Days"] <= day_limit
        ].copy()

    frequency = (
        visible_data
        .groupby("Lead Time Days")
        .size()
        .reset_index(name="Количество задач")
        .sort_values("Lead Time Days")
    )

    if total_tasks > 0 and not frequency.empty:
        frequency["Доля"] = frequency["Количество задач"] / total_tasks * 100
    else:
        frequency["Доля"] = pd.Series(dtype=float)

    return frequency, visible_data


def build_chart(frequency):
    """Создаёт интерактивную частотную диаграмму Lead Time."""
    chart_data = frequency.copy()
    chart_data["День"] = chart_data["Lead Time Days"].astype(str)

    custom_data = np.column_stack(
        (
            chart_data["Lead Time Days"],
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
                "Lead Time: %{customdata[0]:.0f} дн."
                "<br>Количество задач: %{y}"
                "<br>Доля среди выбранных задач: %{customdata[1]:.1f}%"
                "<extra></extra>"
            ),
            name="Количество задач",
        )
    )

    fig.update_layout(
        title={
            "text": "Распределение Lead Time",
            "x": 0.01,
            "xanchor": "left",
        },
        xaxis_title="Lead Time, полных календарных суток",
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

    fig.update_yaxes(rangemode="tozero", dtick=1)

    return fig


def build_task_table(visible_data):
    """Формирует список задач, вошедших в расчёт Lead Time."""
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
        "Lead Time Days",
    ])

    rename_map.update({
        "Created_display": "Создана",
        "Resolved_display": "Закрыта",
        "Lead Time Days": "Lead Time, дней",
    })

    table = table[columns].rename(columns=rename_map)

    table = table.sort_values(
        by="Lead Time, дней",
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)

    return table


def build_excluded_table(excluded_data):
    """Формирует список задач, исключённых из расчёта Lead Time."""
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

    return table[columns].rename(columns=rename_map).reset_index(drop=True)


st.title("Jira Flow Analyzer")
st.write(
    "Загрузите CSV-выгрузку из Jira. На первом этапе приложение проверяет "
    "качество данных и рассчитывает **Lead Time** от Created до Resolved."
)

uploaded_file = st.file_uploader(
    "Загрузить CSV из Jira",
    type=["csv"],
)

if uploaded_file is None:
    st.info("Выберите CSV-файл, чтобы начать анализ.")
    st.stop()


try:
    source_df, detected_separator, detected_encoding = read_csv_file(uploaded_file)
    lead_time_result = prepare_lead_time_data(source_df)

except Exception as error:
    st.error(f"Не удалось обработать файл: {error}")
    st.stop()


# -----------------------------
# Доступность метрик
# -----------------------------
st.subheader("Доступность метрик")

if lead_time_result["available"]:
    st.success("Lead Time: доступен")
else:
    missing_text = ", ".join(lead_time_result["missing_columns"])
    st.warning(
        "Lead Time: недоступен. "
        f"В файле отсутствуют колонки: {missing_text}."
    )

st.info(
    "Cycle Time: пока недоступен. Для корректного расчёта нужна дата первого "
    "перехода задачи в разработку. Обычная выгрузка без истории переходов "
    "этого не содержит."
)

st.info(
    "Time in Status и Blocked Time: пока недоступны. Для них нужна история "
    "переходов Jira."
)

if not lead_time_result["available"]:
    with st.expander("Информация о загруженном файле"):
        st.write(f"Строк в исходном файле: {len(source_df)}")
        st.write(f"Определённый разделитель CSV: `{detected_separator}`")
        st.write(f"Определённая кодировка: `{detected_encoding}`")
        st.write("Колонки в файле:")
        st.write(list(source_df.columns))
    st.stop()


data = lead_time_result["valid_data"]
excluded_data = lead_time_result["excluded_data"]


# -----------------------------
# Качество данных
# -----------------------------
st.subheader("Качество данных для Lead Time")

source_count = len(source_df)
valid_count = len(data)
excluded_count = len(excluded_data)
quality_percent = (valid_count / source_count * 100) if source_count else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Всего строк", source_count)
col2.metric("Участвуют в расчёте", valid_count)
col3.metric("Исключены", excluded_count)
col4.metric("Качество данных", f"{quality_percent:.1f}%")

if excluded_count > 0:
    st.warning(
        f"Из расчёта Lead Time исключено задач: {excluded_count}. "
        "Они не участвуют в графике и показаны отдельно ниже."
    )

    problem_counts = (
        excluded_data["Проблемы данных"]
        .str.split("; ")
        .explode()
        .value_counts()
        .rename_axis("Проблема")
        .reset_index(name="Количество")
    )

    st.dataframe(
        problem_counts,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.success("Для расчёта Lead Time проблем с обязательными данными не найдено.")


if data.empty:
    st.error(
        "В файле нет задач с достаточными и корректными данными для расчёта Lead Time."
    )
else:
    # -----------------------------
    # Фильтр по типу задачи
    # -----------------------------
    if "Issue Type" in data.columns:
        issue_types = sorted(data["Issue Type"].dropna().astype(str).unique().tolist())

        selected_types = st.multiselect(
            "Тип задачи",
            options=issue_types,
            default=issue_types,
            help="Можно выбрать один, несколько или все типы задач.",
        )

        if not selected_types:
            st.info("Выберите хотя бы один тип задачи.")
            st.stop()

        filtered_data = data[data["Issue Type"].astype(str).isin(selected_types)].copy()
    else:
        st.warning(
            "В файле нет колонки Issue Type. Lead Time будет рассчитан, "
            "но фильтр по типу задачи недоступен."
        )
        filtered_data = data.copy()

    display_option = st.radio(
        "Диапазон отображения",
        options=["До 30 дней", "До 90 дней", "Все задачи"],
        index=0,
        horizontal=True,
        help="Диапазон меняет и диаграмму, и список задач под ней.",
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
    else:
        total_tasks = len(filtered_data)
        visible_tasks = len(visible_data)
        hidden_tasks = total_tasks - visible_tasks

        if hidden_tasks > 0:
            st.caption(
                f"После проверки качества выбрано задач: {total_tasks}. "
                f"На диаграмме и в списке показано: {visible_tasks}. "
                f"За пределами выбранного диапазона: {hidden_tasks}."
            )
        else:
            st.caption(
                f"После проверки качества выбрано задач: {total_tasks}. "
                "На диаграмме и в списке показаны все выбранные задачи."
            )

        fig = build_chart(frequency)

        plotly_config = {
            "displaylogo": False,
            "scrollZoom": True,
            "toImageButtonOptions": {
                "format": "png",
                "filename": "jira_lead_time_distribution",
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
            "Lead Time рассчитан от Created до Resolved. "
            "1 день = полные 24 часа. Строки с недостаточными или "
            "некорректными данными в расчёт не включаются."
        )

        # -----------------------------
        # Список задач в расчёте
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
                "Lead Time, дней": st.column_config.NumberColumn(
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
                file_name="jira_lead_time_distribution.png",
                mime="image/png",
                use_container_width=False,
            )

        except Exception:
            st.info(
                "Отдельная кнопка скачивания PNG сейчас недоступна. "
                "Диаграмму всё равно можно скачать: наведите курсор на график "
                "и нажмите значок камеры в панели Plotly."
            )


# -----------------------------
# Исключённые задачи
# -----------------------------
if excluded_count > 0:
    st.subheader(f"Исключённые из Lead Time задачи — {excluded_count}")
    st.caption(
        "Эти задачи не участвуют в расчёте Lead Time. "
        "В последнем столбце указано, какие данные нужно исправить или заполнить."
    )

    excluded_table = build_excluded_table(excluded_data)

    st.dataframe(
        excluded_table,
        use_container_width=True,
        hide_index=True,
        height=500,
        column_config={
            "Название": st.column_config.TextColumn(width="large"),
            "Почему исключена": st.column_config.TextColumn(width="large"),
        },
    )


with st.expander("Информация о загруженном файле"):
    st.write(f"Строк в исходном файле: {len(source_df)}")
    st.write(f"Задач для Lead Time после проверки данных: {len(data)}")
    st.write(f"Исключено из Lead Time: {len(excluded_data)}")
    st.write(f"Определённый разделитель CSV: `{detected_separator}`")
    st.write(f"Определённая кодировка: `{detected_encoding}`")
    st.write("Колонки в файле:")
    st.write(list(source_df.columns))
