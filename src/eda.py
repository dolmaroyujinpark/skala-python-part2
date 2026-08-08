"""
프로그램명 : eda.py — 기술통계 및 상관관계 분석
작성자     : 판교 10반 박유진
작성일     : 2026-08-07
설명       : 정제된 데이터의 분포와 변수 간 관계를 수치로 파악한다.
             1) 기술통계 산출 (평균·표준편차·분위수·최솟값·최댓값)
             2) 수치형 변수 간 피어슨 상관계수 행렬 계산
             3) 타깃과 상관이 높은 변수 추출
             4) 시간대·요일별 평균속도 집계 (시각화 및 t-test의 근거)
변경 이력  : 2026-08-07 최초 작성
실행 방법  : 직접 실행하지 않고 main.py에서 호출한다.
산출 파일  : outputs/tables/*.csv (기술통계·상관계수 표)
"""

from typing import Any

import pandas as pd

from src.common import subsection
from src.config import STAT_COLUMNS, TABLE_DIR


def describe_numeric(
    df: pd.DataFrame, columns: list[str] | None = None
) -> pd.DataFrame:
    """수치형 변수의 기술통계를 산출한다.

    채점 기준이 요구하는 평균·표준편차·분위수를 모두 포함한다.

    Args:
        df: 대상 DataFrame.
        columns: 통계를 낼 컬럼 목록. None이면 config.STAT_COLUMNS를 사용한다.

    Returns:
        pd.DataFrame: 컬럼별 기술통계 표.
    """
    columns = columns or STAT_COLUMNS
    available = [c for c in columns if c in df.columns]
    stats = df[available].agg(["count", "mean", "std", "min", "median", "max"]).T
    # 분위수는 agg로 한 번에 뽑기 어려우므로 별도 계산해 결합한다
    quantiles = df[available].quantile([0.25, 0.75]).T
    quantiles.columns = ["25%", "75%"]
    result = stats.join(quantiles)
    result = result[["count", "mean", "std", "min", "25%", "median", "75%", "max"]]
    result.columns = [
        "건수",
        "평균",
        "표준편차",
        "최솟값",
        "25%",
        "중앙값",
        "75%",
        "최댓값",
    ]
    result.index.name = "변수"
    return result


def correlation_matrix(
    df: pd.DataFrame, columns: list[str] | None = None
) -> pd.DataFrame:
    """수치형 변수 간 피어슨 상관계수 행렬을 계산한다.

    Args:
        df: 대상 DataFrame.
        columns: 상관계수를 낼 컬럼 목록. None이면 config.STAT_COLUMNS를 사용한다.

    Returns:
        pd.DataFrame: 상관계수 행렬.
    """
    columns = columns or STAT_COLUMNS
    available = [c for c in columns if c in df.columns]
    matrix = df[available].corr(method="pearson")
    matrix.index.name = "변수"
    return matrix


def top_correlations(matrix: pd.DataFrame, target: str, top_n: int = 5) -> pd.DataFrame:
    """특정 변수와 상관이 큰 변수를 절댓값 기준으로 뽑는다.

    Args:
        matrix: correlation_matrix가 만든 상관계수 행렬.
        target: 기준이 될 변수명.
        top_n: 반환할 변수 개수.

    Returns:
        pd.DataFrame: 상관계수와 그 절댓값을 담은 표.

    Raises:
        KeyError: 기준 변수가 행렬에 없는 경우.
    """
    if target not in matrix.columns:
        raise KeyError(f"상관계수 행렬에 '{target}' 변수가 없습니다.")
    series = matrix[target].drop(labels=[target])
    result = pd.DataFrame({"상관계수": series, "절댓값": series.abs()})
    result = result.sort_values("절댓값", ascending=False).head(top_n)
    result.index.name = "변수"
    return result


def speed_by_hour_dow(df: pd.DataFrame) -> pd.DataFrame:
    """시간대(0~23) x 요일(월~일)별 평균 속도를 집계한다.

    Seaborn 히트맵과 Plotly 차트가 공통으로 사용하는 집계 결과다.

    Args:
        df: speed_mph, hour, dow가 있는 DataFrame.

    Returns:
        pd.DataFrame: 행=요일, 열=시간대인 평균 속도 피벗 테이블.
    """
    pivot = df.pivot_table(
        index="dow", columns="hour", values="speed_mph", aggfunc="mean"
    )
    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
    pivot.index = [weekday_names[i] for i in pivot.index]
    pivot.index.name = "요일"
    pivot.columns.name = "승차 시각(시)"
    return pivot


def jam_rate_by_hour(df: pd.DataFrame, target: str = "jam_abs") -> pd.DataFrame:
    """시간대별 평균 속도와 정체 비율을 함께 집계한다.

    Args:
        df: 타깃과 speed_mph, hour가 있는 DataFrame.
        target: 정체 비율을 계산할 타깃 컬럼명.

    Returns:
        pd.DataFrame: 시간대별 트립 수·평균 속도·정체 비율.
    """
    grouped = df.groupby("hour").agg(
        트립수=("speed_mph", "size"),
        평균속도=("speed_mph", "mean"),
        정체비율=(target, "mean"),
    )
    grouped["정체비율"] = grouped["정체비율"] * 100
    grouped.index.name = "승차 시각(시)"
    return grouped


def run_eda(df: pd.DataFrame) -> dict[str, Any]:
    """기술통계·상관계수·집계를 한 번에 수행하고 결과를 저장한다.

    Args:
        df: 정제 및 타깃 생성이 끝난 DataFrame.

    Returns:
        dict: 기술통계표, 상관계수 행렬, 상위 상관 변수, 시간대 집계 결과.
    """
    subsection("3-1. 기술통계 (평균·표준편차·분위수)")
    describe_df = describe_numeric(df)
    print(describe_df.round(3).to_string())

    subsection("3-2. 변수 간 상관계수")
    corr_df = correlation_matrix(df)
    print(corr_df.round(3).to_string())

    top_corr = top_correlations(corr_df, "speed_mph")
    print("\n  · speed_mph와 상관이 큰 변수")
    print(top_corr.round(3).to_string())

    subsection("3-3. 시간대·요일별 평균 속도")
    hour_dow = speed_by_hour_dow(df)
    hourly = jam_rate_by_hour(df)
    slowest = hourly["평균속도"].idxmin()
    fastest = hourly["평균속도"].idxmax()
    print(
        f"  · 가장 느린 시간대: {slowest}시 ({hourly.loc[slowest, '평균속도']:.2f} mph)"
    )
    print(
        f"  · 가장 빠른 시간대: {fastest}시 ({hourly.loc[fastest, '평균속도']:.2f} mph)"
    )
    print(f"  · 속도 격차: {hourly['평균속도'].max() / hourly['평균속도'].min():.2f}배")

    _save_table(describe_df, "descriptive_stats.csv")
    _save_table(corr_df, "correlation_matrix.csv")
    _save_table(hourly, "hourly_summary.csv")

    return {
        "describe": describe_df,
        "correlation": corr_df,
        "top_correlation": top_corr,
        "hour_dow_pivot": hour_dow,
        "hourly": hourly,
        "slowest_hour": int(slowest),
        "fastest_hour": int(fastest),
        "slowest_speed": float(hourly["평균속도"].min()),
        "fastest_speed": float(hourly["평균속도"].max()),
    }


def _save_table(df: pd.DataFrame, filename: str) -> None:
    """표를 CSV로 저장한다. 저장 실패가 전체 실행을 막지 않도록 예외를 흡수한다.

    Args:
        df: 저장할 DataFrame.
        filename: outputs/tables 하위에 저장할 파일명.
    """
    path = TABLE_DIR / filename
    try:
        df.to_csv(path, encoding="utf-8-sig")
        print(f"  · 표 저장: {path.relative_to(TABLE_DIR.parent.parent)}")
    except OSError as exc:
        print(f"  ! 표 저장 실패({filename}): {exc}")
