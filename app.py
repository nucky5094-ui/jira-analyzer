import streamlit as st

from charts import build_lead_time_chart, build_throughput_chart
from data_processing import (
    apply_issue_type_filter,
    get_issue_types,
    read_csv_file,
)
from data_quality import (
    prepare_lead_time_data,
    prepare_throughput_data,
    problem_counts_table,
)
from metrics import (
    build_frequency_table,
    build_weekly_throughput,
    calculate_lead_time_percentiles,
)
from tables import build_excluded_table, build_task_table


st.set_page_config(
    page_title="Jira Flow Analyzer",
    page_icon="📊",
    layout="wide",
)


st.title("Jira Flow Analyzer")
st.write(
    "Загрузите CSV-выгрузку из Jira. Приложение проверит качество данных, "
    "рассчитает **Lead Time**, его перцентили и **Throughput по неделям**."
)

uploaded_file = st.file_uploader("Загрузить CSV из Jira", type=["csv"])

if uploaded_file is None:
    st.info("Выберите CSV-файл, чтобы начать анализ.")
    st.stop()

try:
    source_df, detected_separator, detected_encoding = read_csv_file(uploaded_file)
    lead_time_result = prepare_lead_time_data(source_df)
    throughput_result = prepare_throughput_data(source_df)
except Exception as error:
    st.error(f"Не удалось обработать файл: {error}")
    st.stop()


# -----------------------------------------------------------------------------
# Доступность метрик
# -----------------------------------------------------------------------------
st.subheader("Доступность метрик")

availability_cols = st.columns(4)

with availability_cols[0]:
    if lead_time_result["available"]:
        st.success("Lead Time\n\nДоступен")
    else:
        missing = ", ".join(lead_time_result["missing_columns"])
        st.warning(f"Lead Time\n\nНет колонок: {missing}")

with availability_cols[1]:
    if throughput_result["available"]:
        st.success("Throughput\n\nДоступен")
    else:
        missing = ", ".join(throughput_result["missing_columns"])
        st.warning(f"Throughput\n\nНет колонок: {missing}")

with availability_cols[2]:
    st.info("Cycle Time\n\nНедоступен: нужна дата первого перехода в разработку.")

with availability_cols[3]:
    st.info("Time in Status\n\nНедоступен: нужна история переходов Jira.")

st.caption(
    "Недоступность одной метрики не блокирует остальные. "
    "Каждая метрика использует только строки, достаточные для её расчёта."
)


# -----------------------------------------------------------------------------
# Общий фильтр по типам задач
# -----------------------------------------------------------------------------
selected_types = None
issue_types = get_issue_types(source_df)

if issue_types:
    selected_types = st.multiselect(
        "Тип задачи",
        options=issue_types,
        default=issue_types,
        help="Фильтр применяется ко всем доступным метрикам.",
    )
    if not selected_types:
        st.info("Выберите хотя бы один тип задачи.")
        st.stop()
elif "Issue Type" not in source_df.columns:
    st.warning("В файле нет колонки Issue Type. Фильтр по типам задач недоступен.")

lead_data = apply_issue_type_filter(
    lead_time_result["valid_data"],
    selected_types,
)
throughput_data = apply_issue_type_filter(
    throughput_result["valid_data"],
    selected_types,
)


# -----------------------------------------------------------------------------
# Качество данных по метрикам
# -----------------------------------------------------------------------------
st.subheader("Качество данных")

quality_tab1, quality_tab2 = st.tabs(["Lead Time", "Throughput"])

with quality_tab1:
    if not lead_time_result["available"]:
        missing = ", ".join(lead_time_result["missing_columns"])
        st.warning(f"Метрика недоступна. Не хватает колонок: {missing}.")
    else:
        lead_valid_all = len(lead_time_result["valid_data"])
        lead_excluded = len(lead_time_result["excluded_data"])
        total = len(source_df)
        quality = lead_valid_all / total * 100 if total else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Всего строк", total)
        c2.metric("Пригодны", lead_valid_all)
        c3.metric("Исключены", lead_excluded)
        c4.metric("Качество", f"{quality:.1f}%")

        if lead_excluded:
            st.dataframe(
                problem_counts_table(lead_time_result["excluded_data"]),
                use_container_width=True,
                hide_index=True,
            )

with quality_tab2:
    if not throughput_result["available"]:
        missing = ", ".join(throughput_result["missing_columns"])
        st.warning(f"Метрика недоступна. Не хватает колонок: {missing}.")
    else:
        throughput_valid_all = len(throughput_result["valid_data"])
        throughput_excluded = len(throughput_result["excluded_data"])
        total = len(source_df)
        quality = throughput_valid_all / total * 100 if total else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Всего строк", total)
        c2.metric("Пригодны", throughput_valid_all)
        c3.metric("Исключены", throughput_excluded)
        c4.metric("Качество", f"{quality:.1f}%")

        if throughput_excluded:
            st.dataframe(
                problem_counts_table(throughput_result["excluded_data"]),
                use_container_width=True,
                hide_index=True,
            )


# -----------------------------------------------------------------------------
# Lead Time + P50/P85/P95
# -----------------------------------------------------------------------------
st.divider()
st.header("Lead Time")

if not lead_time_result["available"]:
    missing = ", ".join(lead_time_result["missing_columns"])
    st.warning(f"Lead Time не рассчитан. Не хватает колонок: {missing}.")
elif lead_data.empty:
    st.warning("После проверки качества и применения фильтров нет задач для Lead Time.")
else:
    percentiles = calculate_lead_time_percentiles(lead_data)
    if percentiles:
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Задач в расчёте", len(lead_data))
        p2.metric("P50", f"{percentiles['P50']:.1f} дн.")
        p3.metric("P85", f"{percentiles['P85']:.1f} дн.")
        p4.metric("P95", f"{percentiles['P95']:.1f} дн.")
        st.caption(
            "P85 означает: 85% задач из текущей выборки были закрыты "
            "не дольше указанного времени от Created до Resolved."
        )

    display_option = st.radio(
        "Диапазон отображения Lead Time",
        options=["До 30 дней", "До 90 дней", "Все задачи"],
        index=0,
        horizontal=True,
        help=(
            "Меняет только распределение и список задач ниже. "
            "P50/P85/P95 считаются по всей текущей выборке, а не по обрезанному диапазону."
        ),
    )

    day_limit_map = {"До 30 дней": 30, "До 90 дней": 90, "Все задачи": None}
    day_limit = day_limit_map[display_option]

    frequency, visible_data = build_frequency_table(lead_data, day_limit)

    if frequency.empty:
        st.warning("В выбранном диапазоне нет задач для отображения.")
    else:
        hidden_tasks = len(lead_data) - len(visible_data)
        st.caption(
            f"В расчёте Lead Time: {len(lead_data)} задач. "
            f"На диаграмме показано: {len(visible_data)}. "
            f"За пределами диапазона: {hidden_tasks}."
        )

        lead_fig = build_lead_time_chart(frequency)
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
        st.plotly_chart(lead_fig, use_container_width=True, config=plotly_config)

        st.caption(
            "Lead Time = время от Created до Resolved. "
            "Для распределения используются полные календарные сутки."
        )

        st.subheader(f"Задачи в Lead Time — {len(visible_data)}")
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
                    width="small", format="%.1f"
                ),
            },
        )


# -----------------------------------------------------------------------------
# Throughput
# -----------------------------------------------------------------------------
st.divider()
st.header("Throughput")
st.caption(
    "Throughput показывает, сколько задач было закрыто за период. "
    "Сейчас группировка выполняется по календарным неделям: понедельник–воскресенье."
)

if not throughput_result["available"]:
    missing = ", ".join(throughput_result["missing_columns"])
    st.warning(f"Throughput не рассчитан. Не хватает колонок: {missing}.")
elif throughput_data.empty:
    st.warning("После проверки качества и применения фильтров нет задач для Throughput.")
else:
    weekly = build_weekly_throughput(throughput_data)

    t1, t2, t3 = st.columns(3)
    t1.metric("Закрыто задач", len(throughput_data))
    t2.metric("Недель в данных", len(weekly))
    t3.metric(
        "Средний Throughput",
        f"{weekly['Закрыто задач'].mean():.1f} задач/нед.",
    )

    throughput_fig = build_throughput_chart(weekly)
    st.plotly_chart(
        throughput_fig,
        use_container_width=True,
        config={"displaylogo": False, "scrollZoom": True},
    )

    st.dataframe(
        weekly[["Неделя", "Закрыто задач"]],
        use_container_width=True,
        hide_index=True,
    )


# -----------------------------------------------------------------------------
# Недоступные метрики — понятные заглушки
# -----------------------------------------------------------------------------
st.divider()
st.header("Пока недоступно")

m1, m2, m3 = st.columns(3)
with m1:
    st.subheader("Cycle Time")
    st.write("Нужна дата первого перехода задачи в разработку.")
    st.caption("Текущая обычная CSV-выгрузка такой истории не содержит.")

with m2:
    st.subheader("Time in Status")
    st.write("Нужны даты входа и выхода из каждого статуса.")
    st.caption("Для этого потребуется история переходов Jira.")

with m3:
    st.subheader("Blocked Time")
    st.write("Нужна история блокировок или переходов в blocked-статусы.")
    st.caption("Пока этих данных в обычной выгрузке нет.")


# -----------------------------------------------------------------------------
# Исключённые задачи — отдельно по каждой метрике
# -----------------------------------------------------------------------------
st.divider()
st.header("Задачи с проблемами данных")
st.caption(
    "Одна и та же задача может быть пригодна для одной метрики и исключена из другой."
)

excluded_tab1, excluded_tab2 = st.tabs(["Не вошли в Lead Time", "Не вошли в Throughput"])

with excluded_tab1:
    excluded = lead_time_result["excluded_data"]
    if lead_time_result["available"] and not excluded.empty:
        st.write(f"Исключено задач: **{len(excluded)}**")
        table = build_excluded_table(excluded)
        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
            height=500,
            column_config={
                "Название": st.column_config.TextColumn(width="large"),
                "Почему исключена": st.column_config.TextColumn(width="large"),
            },
        )
    elif not lead_time_result["available"]:
        st.info("Lead Time целиком недоступен из-за отсутствующих колонок.")
    else:
        st.success("Исключённых задач для Lead Time нет.")

with excluded_tab2:
    excluded = throughput_result["excluded_data"]
    if throughput_result["available"] and not excluded.empty:
        st.write(f"Исключено задач: **{len(excluded)}**")
        table = build_excluded_table(excluded)
        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
            height=500,
            column_config={
                "Название": st.column_config.TextColumn(width="large"),
                "Почему исключена": st.column_config.TextColumn(width="large"),
            },
        )
    elif not throughput_result["available"]:
        st.info("Throughput целиком недоступен из-за отсутствующей колонки Resolved.")
    else:
        st.success("Исключённых задач для Throughput нет.")


with st.expander("Информация о загруженном файле"):
    st.write(f"Строк в исходном файле: {len(source_df)}")
    st.write(f"Определённый разделитель CSV: `{detected_separator}`")
    st.write(f"Определённая кодировка: `{detected_encoding}`")
    st.write("Колонки в файле:")
    st.write(list(source_df.columns))
