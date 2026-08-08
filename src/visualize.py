"""
프로그램명 : visualize.py — Seaborn 정적 차트 / Plotly 인터랙티브 차트 생성
작성자     : 판교 10반 박유진
작성일     : 2026-08-07
설명       : 분석 결과를 시각화하여 이미지·HTML 파일로 저장한다.
             1) Seaborn 히트맵 — 시간대 x 요일별 평균 속도 (그룹 비교)
             2) Seaborn 히트맵 — 변수 간 상관계수 (상관관계)
             3) Plotly 이중축 차트 — 시간대별 평균 속도와 정체 비율 (인터랙티브)
             4) Plotly 박스플롯 — 정체/비정체 트립의 주행거리 분포 (인터랙티브)
             모든 차트에 제목과 축 레이블을 반드시 포함한다.
변경 이력  : 2026-08-07 최초 작성
실행 방법  : 직접 실행하지 않고 main.py에서 호출한다.
산출 파일  : outputs/figures/*.png (정적), outputs/figures/*.html (인터랙티브)
"""

from typing import Any

import matplotlib
import pandas as pd

# 저장 전용 백엔드를 사용한다. 화면 장치가 없는 환경에서도 파일 생성이 가능하다.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import plotly.graph_objects as go
import seaborn as sns
from matplotlib import font_manager
from plotly.subplots import make_subplots

from src.common import subsection
from src.config import FIGURE_DIR

# 한글 축 레이블이 깨지지 않도록 설치된 한글 폰트를 찾아 지정한다.
# 주의: sns.set_theme()이 rcParams의 폰트 설정을 덮어쓰므로 반드시 테마를 먼저 적용한다.
sns.set_theme(style="whitegrid")

KOREAN_FONT_CANDIDATES = [
    "AppleGothic",
    "Apple SD Gothic Neo",
    "NanumGothic",
    "Malgun Gothic",
]


def _apply_korean_font() -> str:
    """설치된 한글 폰트 중 사용 가능한 것을 찾아 matplotlib에 적용한다.

    폰트를 찾지 못하면 축 레이블의 한글이 네모로 깨지므로, 후보를 순회하며
    실제 설치 여부를 확인한 뒤 지정한다.

    Returns:
        str: 적용된 폰트 이름. 후보가 모두 없으면 빈 문자열.
    """
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for candidate in KOREAN_FONT_CANDIDATES:
        if candidate in installed:
            plt.rcParams["font.family"] = candidate
            plt.rcParams["axes.unicode_minus"] = False  # 마이너스 기호 깨짐 방지
            return candidate
    print("  ! 한글 폰트를 찾지 못했습니다. 축 레이블이 깨질 수 있습니다.")
    return ""


ACTIVE_FONT = _apply_korean_font()


def _save_figure(fig: plt.Figure, filename: str) -> str:
    """matplotlib Figure를 PNG로 저장한다.

    Args:
        fig: 저장할 Figure 객체.
        filename: outputs/figures 하위 파일명.

    Returns:
        str: 저장된 파일의 상대 경로. 실패 시 빈 문자열.
    """
    path = FIGURE_DIR / filename
    try:
        fig.savefig(path, dpi=150, bbox_inches="tight")
        print(f"  · 저장: figures/{filename}")
        return f"figures/{filename}"
    except OSError as exc:
        print(f"  ! 그림 저장 실패({filename}): {exc}")
        return ""
    finally:
        plt.close(fig)


def _save_html(fig: go.Figure, filename: str) -> str:
    """Plotly Figure를 인터랙티브 HTML로 저장한다.

    Args:
        fig: 저장할 Plotly Figure 객체.
        filename: outputs/figures 하위 파일명.

    Returns:
        str: 저장된 파일의 상대 경로. 실패 시 빈 문자열.
    """
    path = FIGURE_DIR / filename
    try:
        fig.write_html(path, include_plotlyjs="cdn")
        print(f"  · 저장: figures/{filename}")
        return f"figures/{filename}"
    except (OSError, ValueError) as exc:
        print(f"  ! HTML 저장 실패({filename}): {exc}")
        return ""


def plot_speed_heatmap(pivot: pd.DataFrame) -> str:
    """[Seaborn 정적] 시간대 x 요일별 평균 속도 히트맵을 그린다.

    언제 뉴욕 도로가 느려지는지를 한눈에 보여주는 그룹 비교 차트다.

    Args:
        pivot: eda.speed_by_hour_dow가 만든 피벗 테이블.

    Returns:
        str: 저장된 파일 경로.
    """
    fig, ax = plt.subplots(figsize=(14, 4.5))
    sns.heatmap(
        pivot,
        cmap="RdYlGn",
        annot=False,
        linewidths=0.4,
        ax=ax,
        cbar_kws={"label": "평균 속도 (mph)"},
    )
    ax.set_title("뉴욕 옐로우캡 시간대·요일별 평균 주행 속도", fontsize=14, pad=12)
    ax.set_xlabel("승차 시각 (시)", fontsize=11)
    ax.set_ylabel("요일", fontsize=11)
    # 한 글자 요일 라벨은 세로로 세우면 읽기 어려우므로 가로로 눕힌다
    plt.setp(ax.get_yticklabels(), rotation=0)
    return _save_figure(fig, "01_speed_heatmap_seaborn.png")


def plot_correlation_heatmap(corr: pd.DataFrame) -> str:
    """[Seaborn 정적] 수치형 변수 간 상관계수 히트맵을 그린다.

    Args:
        corr: eda.correlation_matrix가 만든 상관계수 행렬.

    Returns:
        str: 저장된 파일 경로.
    """
    fig, ax = plt.subplots(figsize=(9, 7))
    sns.heatmap(
        corr,
        cmap="coolwarm",
        center=0,
        annot=True,
        fmt=".2f",
        linewidths=0.4,
        ax=ax,
        cbar_kws={"label": "피어슨 상관계수"},
    )
    ax.set_title("수치형 변수 간 상관계수", fontsize=14, pad=12)
    ax.set_xlabel("변수", fontsize=11)
    ax.set_ylabel("변수", fontsize=11)
    plt.setp(ax.get_xticklabels(), rotation=40, ha="right")
    return _save_figure(fig, "02_correlation_heatmap_seaborn.png")


def plot_distance_distribution(df: pd.DataFrame) -> str:
    """[Seaborn 정적] 정체/비정체 트립의 주행거리 분포를 겹쳐 그린다.

    절대정체 타깃이 '도심 단거리'를 많이 잡는다는 점을 시각적으로 드러낸다.

    Args:
        df: jam_abs와 trip_distance가 있는 DataFrame.

    Returns:
        str: 저장된 파일 경로.
    """
    fig, ax = plt.subplots(figsize=(10, 5))
    subset = df[df["trip_distance"] <= 15]
    sns.histplot(
        data=subset,
        x="trip_distance",
        hue="jam_abs",
        bins=60,
        stat="density",
        common_norm=False,
        element="step",
        ax=ax,
    )
    ax.set_title("정체 여부에 따른 주행거리 분포 (15마일 이하)", fontsize=14, pad=12)
    ax.set_xlabel("주행거리 (마일)", fontsize=11)
    ax.set_ylabel("밀도", fontsize=11)
    legend = ax.get_legend()
    if legend is not None:
        legend.set_title("정체 여부")
        for text, label in zip(legend.get_texts(), ["비정체", "정체"], strict=False):
            text.set_text(label)
    return _save_figure(fig, "03_distance_distribution_seaborn.png")


def plot_hourly_interactive(hourly: pd.DataFrame) -> str:
    """[Plotly 인터랙티브] 시간대별 평균 속도와 정체 비율을 이중축으로 그린다.

    마우스를 올리면 각 시간대의 트립 수·속도·정체 비율을 확인할 수 있다.

    Args:
        hourly: eda.jam_rate_by_hour가 만든 시간대별 집계표.

    Returns:
        str: 저장된 파일 경로.
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=hourly.index,
            y=hourly["평균속도"],
            name="평균 속도 (mph)",
            mode="lines+markers",
            line={"width": 3},
            hovertemplate="%{x}시<br>평균 속도 %{y:.2f} mph<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            x=hourly.index,
            y=hourly["정체비율"],
            name="정체 비율 (%)",
            opacity=0.45,
            hovertemplate="%{x}시<br>정체 비율 %{y:.1f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_layout(
        title={"text": "시간대별 평균 주행 속도와 정체 트립 비율", "x": 0.5},
        xaxis_title="승차 시각 (시)",
        hovermode="x unified",
        template="plotly_white",
        legend={"orientation": "h", "y": -0.2},
    )
    fig.update_yaxes(title_text="평균 속도 (mph)", secondary_y=False)
    fig.update_yaxes(title_text="정체 비율 (%)", secondary_y=True)
    return _save_html(fig, "04_hourly_speed_plotly.html")


def plot_zone_interactive(df: pd.DataFrame, top_n: int = 20) -> str:
    """[Plotly 인터랙티브] 정체율이 높은 출발 존 상위 N개를 막대로 그린다.

    Args:
        df: jam_abs와 PULocationID가 있는 DataFrame.
        top_n: 표시할 존 개수.

    Returns:
        str: 저장된 파일 경로.
    """
    zone = df.groupby("PULocationID").agg(
        트립수=("jam_abs", "size"),
        정체율=("jam_abs", "mean"),
        평균속도=("speed_mph", "mean"),
    )
    # 표본이 적은 존은 비율이 불안정하므로 제외한다
    zone = zone[zone["트립수"] >= 500].copy()
    zone["정체율"] = zone["정체율"] * 100
    zone = zone.sort_values("정체율", ascending=False).head(top_n)

    fig = go.Figure(
        go.Bar(
            x=zone.index.astype(str),
            y=zone["정체율"],
            marker={
                "color": zone["평균속도"],
                "colorscale": "RdYlGn",
                "colorbar": {"title": "평균 속도<br>(mph)"},
            },
            customdata=zone[["트립수", "평균속도"]].values,
            hovertemplate=(
                "존 %{x}<br>정체율 %{y:.1f}%<br>"
                "트립수 %{customdata[0]:,}<br>"
                "평균 속도 %{customdata[1]:.2f} mph<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title={
            "text": f"정체율이 높은 출발 존 상위 {top_n}개 (트립 500건 이상)",
            "x": 0.5,
        },
        xaxis_title="출발 존 ID (PULocationID)",
        yaxis_title="정체 트립 비율 (%)",
        template="plotly_white",
    )
    return _save_html(fig, "05_zone_jam_rate_plotly.html")


def create_all_figures(df: pd.DataFrame, eda_result: dict[str, Any]) -> dict[str, Any]:
    """모든 차트를 생성하고 저장 경로를 모아 반환한다.

    Args:
        df: 정제 및 타깃 생성이 끝난 DataFrame.
        eda_result: eda.run_eda가 반환한 결과 dict.

    Returns:
        dict: 차트 종류별 저장 경로.
    """
    subsection("4-1. Seaborn 정적 차트")
    seaborn_paths = [
        plot_speed_heatmap(eda_result["hour_dow_pivot"]),
        plot_correlation_heatmap(eda_result["correlation"]),
        plot_distance_distribution(df),
    ]

    subsection("4-2. Plotly 인터랙티브 차트")
    plotly_paths = [
        plot_hourly_interactive(eda_result["hourly"]),
        plot_zone_interactive(df),
    ]

    return {
        "seaborn": [p for p in seaborn_paths if p],
        "plotly": [p for p in plotly_paths if p],
    }
