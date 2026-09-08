import numpy as np
import plotly.graph_objects as go


def build_lead_time_chart(frequency):
    """Строит распределение Lead Time."""
    chart_data = frequency.copy()
    chart_data["День"] = chart_data["Lead Time Full Days"].astype(str)

    custom_data = np.column_stack(
        (chart_data["Lead Time Full Days"], chart_data["Доля"])
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
        title={"text": "Распределение Lead Time", "x": 0.01, "xanchor": "left"},
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


def build_throughput_chart(weekly):
    """Строит Throughput по неделям."""
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=weekly["Неделя"],
            y=weekly["Закрыто задач"],
            hovertemplate=(
                "Неделя с %{x}"
                "<br>Закрыто задач: %{y}"
                "<extra></extra>"
            ),
            name="Throughput",
        )
    )

    fig.update_layout(
        title={"text": "Throughput по неделям", "x": 0.01, "xanchor": "left"},
        xaxis_title="Начало недели",
        yaxis_title="Количество закрытых задач",
        hovermode="closest",
        bargap=0.18,
        height=500,
        margin=dict(l=40, r=30, t=80, b=80),
    )
    fig.update_yaxes(rangemode="tozero", dtick=1)
    return fig
