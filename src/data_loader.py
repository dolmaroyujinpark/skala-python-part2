"""
프로그램명 : data_loader.py — Pandas / Polars 이중 로딩 및 결과 비교
작성자     : 판교 10반 박유진
작성일     : 2026-08-07
설명       : 동일한 parquet 파일을 두 라이브러리로 읽어 결과가 일치하는지 검증한다.
             1) Pandas로 로딩 (read_parquet)
             2) Polars Eager 로딩 (read_parquet)
             3) Polars Lazy 로딩 (scan_parquet + collect) — 실행계획 기반
             4) 행수·열수·결측수·기술통계를 대조하여 차이점 도출
변경 이력  : 2026-08-07 최초 작성
실행 방법  : 직접 실행하지 않고 main.py에서 호출한다.
산출 파일  : 없음 (비교 결과를 dict로 반환)
"""

from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl

from src.common import measure, subsection
from src.config import LAZY_SCAN_COLUMNS


def load_with_pandas(path: Path) -> tuple[pd.DataFrame, float]:
    """Pandas로 parquet 파일을 읽는다.

    Args:
        path: 읽을 parquet 파일 경로.

    Returns:
        tuple: (DataFrame, 소요 시간(초)).

    Raises:
        RuntimeError: 파일을 읽지 못한 경우.
    """
    try:
        return measure(pd.read_parquet, path)
    except Exception as exc:
        raise RuntimeError(f"Pandas 로딩 실패: {path}") from exc


def load_with_polars(path: Path) -> tuple[pl.DataFrame, float]:
    """Polars Eager 방식(read_parquet)으로 parquet 파일을 읽는다.

    Args:
        path: 읽을 parquet 파일 경로.

    Returns:
        tuple: (Polars DataFrame, 소요 시간(초)).

    Raises:
        RuntimeError: 파일을 읽지 못한 경우.
    """
    try:
        return measure(pl.read_parquet, path)
    except Exception as exc:
        raise RuntimeError(f"Polars 로딩 실패: {path}") from exc


def aggregate_with_polars_lazy(path: Path) -> tuple[pl.DataFrame, float]:
    """Polars Lazy 방식(scan_parquet)으로 승객 수별 평균 속도를 집계한다.

    scan_parquet은 즉시 읽지 않고 실행 계획만 세우며, collect() 시점에
    projection pushdown(필요한 컬럼만 읽기)과 predicate pushdown(조건을 스캔
    단계로 내리기)이 적용된다. 여기서는 집계 결과까지 Lazy로 만들어,
    같은 집계를 수행한 Pandas 결과와 대조할 수 있게 한다.

    Args:
        path: 읽을 parquet 파일 경로.

    Returns:
        tuple: (승객 수별 평균 속도 DataFrame, 소요 시간(초)).

    Raises:
        RuntimeError: 파일을 읽거나 집계하지 못한 경우.
    """

    def _scan_and_aggregate() -> pl.DataFrame:
        """실행 계획을 세운 뒤 collect()로 스캔과 집계를 한 번에 수행한다."""
        duration = (
            pl.col("tpep_dropoff_datetime") - pl.col("tpep_pickup_datetime")
        ).dt.total_seconds() / 60
        return (
            pl.scan_parquet(path)
            .select(LAZY_SCAN_COLUMNS)
            .with_columns(duration.alias("duration_min"))
            # 속도를 계산할 수 있는 행만 남긴다 (predicate pushdown 대상)
            .filter((pl.col("duration_min") > 0) & (pl.col("trip_distance") > 0))
            .with_columns(
                (pl.col("trip_distance") / (pl.col("duration_min") / 60)).alias(
                    "speed_mph"
                )
            )
            .group_by("passenger_count")
            .agg(
                pl.len().alias("트립수"),
                pl.col("speed_mph").mean().alias("평균속도"),
                # 이상치 제거 전이라 평균이 왜곡될 수 있으므로 중앙값을 함께 본다
                pl.col("speed_mph").median().alias("중앙속도"),
            )
            .sort("passenger_count")
            .collect()
        )

    try:
        return measure(_scan_and_aggregate)
    except Exception as exc:
        raise RuntimeError(f"Polars Lazy 집계 실패: {path}") from exc


def aggregate_with_pandas(pdf: pd.DataFrame) -> pd.DataFrame:
    """Pandas로 동일한 승객 수별 평균 속도 집계를 수행한다.

    Polars Lazy 결과와 대조하기 위한 것이므로 계산 순서를 똑같이 맞춘다.

    Args:
        pdf: Pandas로 읽은 원본 DataFrame.

    Returns:
        pd.DataFrame: 승객 수별 트립 수와 평균 속도.
    """
    frame = pdf[LAZY_SCAN_COLUMNS].copy()
    delta = frame["tpep_dropoff_datetime"] - frame["tpep_pickup_datetime"]
    frame["duration_min"] = delta.dt.total_seconds() / 60
    frame = frame[(frame["duration_min"] > 0) & (frame["trip_distance"] > 0)]
    frame["speed_mph"] = frame["trip_distance"] / (frame["duration_min"] / 60)
    result = frame.groupby("passenger_count").agg(
        트립수=("speed_mph", "size"),
        평균속도=("speed_mph", "mean"),
        중앙속도=("speed_mph", "median"),
    )
    return result.reset_index()


def compare_aggregations(
    pandas_agg: pd.DataFrame, polars_agg: pl.DataFrame
) -> dict[str, Any]:
    """두 라이브러리의 집계 결과를 병합해 차이를 드러낸다.

    Pandas의 `groupby`는 그룹 키가 결측인 행을 기본적으로 제외하지만,
    Polars의 `group_by`는 null을 하나의 그룹으로 유지한다. 이 데이터의
    passenger_count에는 결측이 있으므로 그 차이가 실제로 나타난다.

    Args:
        pandas_agg: Pandas 집계 결과.
        polars_agg: Polars Lazy 집계 결과.

    Returns:
        dict: 병합 비교표와 그룹 수 차이, null 그룹 트립 수.
    """
    polars_pd = polars_agg.to_pandas()
    merged = pandas_agg.merge(
        polars_pd,
        on="passenger_count",
        how="outer",
        suffixes=("_pandas", "_polars"),
    ).sort_values("passenger_count", na_position="last")

    null_group = polars_pd[polars_pd["passenger_count"].isna()]
    null_trips = int(null_group["트립수"].iloc[0]) if not null_group.empty else 0

    merged = merged.set_index("passenger_count")
    merged.index.name = "승객 수"
    return {
        "table": merged,
        "pandas_groups": len(pandas_agg),
        "polars_groups": len(polars_pd),
        "null_group_trips": null_trips,
    }


def compare_missing(pdf: pd.DataFrame, pldf: pl.DataFrame) -> pd.DataFrame:
    """두 라이브러리가 집계한 컬럼별 결측 수를 대조한다.

    Args:
        pdf: Pandas DataFrame.
        pldf: Polars DataFrame.

    Returns:
        pd.DataFrame: 컬럼별 Pandas/Polars 결측 수와 일치 여부.
    """
    pandas_null = pdf.isna().sum()
    polars_null = pldf.null_count().to_pandas().iloc[0]
    result = pd.DataFrame(
        {
            "pandas_결측": pandas_null,
            "polars_결측": polars_null.reindex(pandas_null.index),
        }
    )
    result["일치"] = result["pandas_결측"] == result["polars_결측"]
    return result


def compare_quantiles(
    pdf: pd.DataFrame, pldf: pl.DataFrame, column: str
) -> pd.DataFrame:
    """동일 컬럼의 분위수를 두 라이브러리로 계산해 비교한다.

    Polars의 quantile 기본 보간법은 'nearest', Pandas는 'linear'이므로
    옵션을 맞추지 않으면 값이 미세하게 달라진다. 이 차이를 드러내기 위해
    Polars를 기본값과 linear 두 가지로 계산한다.

    Args:
        pdf: Pandas DataFrame.
        pldf: Polars DataFrame.
        column: 비교할 수치형 컬럼명.

    Returns:
        pd.DataFrame: 분위수별 세 가지 계산 결과.
    """
    quantiles = [0.25, 0.50, 0.75]
    rows = []
    for q in quantiles:
        rows.append(
            {
                "분위수": f"{int(q * 100)}%",
                "pandas(linear)": pdf[column].quantile(q),
                "polars(기본=nearest)": pldf[column].quantile(q),
                "polars(linear 명시)": pldf[column].quantile(q, interpolation="linear"),
            }
        )
    return pd.DataFrame(rows).set_index("분위수")


def compare_loaders(path: Path) -> dict[str, Any]:
    """Pandas와 Polars 로딩 결과를 종합 비교한다.

    Args:
        path: 비교에 사용할 parquet 파일 경로.

    Returns:
        dict: 로딩 시간, 형태 일치 여부, 결측 비교표, 분위수 비교표,
              그리고 이후 단계에서 사용할 Pandas DataFrame.
    """
    subsection("1-1. Pandas / Polars 이중 로딩")
    pdf, pandas_sec = load_with_pandas(path)
    print(
        f"  · Pandas  read_parquet  : {pandas_sec:.3f}초  -> "
        f"{pdf.shape[0]:,}행 x {pdf.shape[1]}열"
    )

    pldf, polars_sec = load_with_polars(path)
    print(
        f"  · Polars  read_parquet  : {polars_sec:.3f}초  -> "
        f"{pldf.shape[0]:,}행 x {pldf.shape[1]}열"
    )

    speedup = pandas_sec / polars_sec if polars_sec > 0 else float("nan")
    print(f"  · Polars가 Pandas 대비 {speedup:.2f}배 빠름")

    subsection("1-2. 두 라이브러리의 로딩 결과 일치 검증")
    shape_match = pdf.shape == (pldf.shape[0], pldf.shape[1])
    print(f"  · 행/열 개수 일치       : {shape_match}")

    missing_df = compare_missing(pdf, pldf)
    all_missing_match = bool(missing_df["일치"].all())
    total_missing = int(missing_df["pandas_결측"].sum())
    print(
        f"  · 컬럼별 결측 수 일치   : {all_missing_match} (전체 결측 {total_missing:,}건)"
    )

    quantile_df = compare_quantiles(pdf, pldf, "trip_distance")
    print("  · trip_distance 분위수 비교 (보간법 차이 확인)")
    print(quantile_df.round(4).to_string())

    nearest = quantile_df["polars(기본=nearest)"]
    linear = quantile_df["polars(linear 명시)"]
    interp_diff = bool((nearest - linear).abs().max() > 0)
    if interp_diff:
        print("    -> 보간법을 명시하지 않으면 Polars와 Pandas의 분위수가 달라진다.")
    else:
        print("    -> 이 컬럼에서는 보간법 차이가 드러나지 않았다.")

    subsection("1-3. 동일 집계 대조 — Polars Lazy vs Pandas")
    polars_agg, lazy_sec = aggregate_with_polars_lazy(path)
    pandas_agg, pandas_agg_sec = measure(aggregate_with_pandas, pdf)
    print(f"  · Polars scan_parquet + group_by : {lazy_sec:.3f}초")
    print(f"  · Pandas  groupby                : {pandas_agg_sec:.3f}초")
    agg_speedup = pandas_agg_sec / lazy_sec if lazy_sec > 0 else float("nan")
    print(
        f"  · Lazy 집계가 {agg_speedup:.2f}배 빠름 "
        f"(필요한 {len(LAZY_SCAN_COLUMNS)}개 컬럼만 읽기 때문)"
    )

    agg = compare_aggregations(pandas_agg, polars_agg)
    print("\n  · 승객 수별 속도 집계 결과 대조 (정제 전 원본이므로 이상치 포함)")
    print(agg["table"].round(3).to_string())
    print(
        f"\n  · 그룹 수 — Pandas {agg['pandas_groups']}개 / Polars {agg['polars_groups']}개"
    )
    if agg["polars_groups"] > agg["pandas_groups"]:
        print("    -> Pandas groupby는 그룹 키가 결측인 행을 기본적으로 제외하지만,")
        print("       Polars group_by는 null을 하나의 그룹으로 유지한다.")
        print(
            f"       이 데이터에서는 {agg['null_group_trips']:,}건이 그 차이에 해당한다."
        )
        print("    -> 두 결과를 맞추려면 pandas는 dropna=False를 주거나,")
        print("       집계 전에 그룹 키의 결측을 명시적으로 제거해야 한다.")
        print("    -> 이 null 그룹이 2단계에서 확인할 '구조적 결측 블록'이다.")
        print("       평균속도가 중앙속도보다 훨씬 큰 것은 정제 전이라")
        print("       이상치가 남아 있기 때문이다.")

    return {
        "pandas_sec": pandas_sec,
        "polars_sec": polars_sec,
        "lazy_sec": lazy_sec,
        "pandas_agg_sec": pandas_agg_sec,
        "agg_speedup": agg_speedup,
        "speedup": speedup,
        "shape": pdf.shape,
        "shape_match": shape_match,
        "missing_table": missing_df,
        "missing_match": all_missing_match,
        "total_missing": total_missing,
        "quantile_table": quantile_df,
        "interpolation_differs": interp_diff,
        "aggregation": agg,
        "dataframe": pdf,
    }
