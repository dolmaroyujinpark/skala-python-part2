"""
프로그램명 : preprocess.py — 결측·중복·이상치 처리 및 정체 타깃 생성
작성자     : 판교 10반 박유진
작성일     : 2026-08-07
설명       : 원본 데이터를 분석 가능한 형태로 정제하고 예측 대상을 만든다.
             1) 파생 변수 생성 (소요시간·평균속도·승차 시각/요일)
             2) 결측 진단 — NaN과 '코드값 결측'(RatecodeID=99, 존 264/265)을 구분
             3) 중복행 및 물리적으로 불가능한 값 제거
             4) 절대정체 / 상대정체 두 가지 타깃 생성
변경 이력  : 2026-08-07 최초 작성
실행 방법  : 직접 실행하지 않고 main.py에서 호출한다.
산출 파일  : 없음 (정제된 DataFrame과 처리 이력을 반환)
"""

import pandas as pd

from src.common import format_int, subsection
from src.config import (
    JAM_QUANTILE,
    MAX_DURATION_MIN,
    MAX_SAME_ZONE_DISTANCE,
    MAX_SPEED_MPH,
    MAX_TRIP_DISTANCE,
    MIN_DURATION_MIN,
    MIN_ROUTE_TRIPS,
    MIN_SPEED_MPH,
    OBSERVATION_MONTH,
    OBSERVATION_YEAR,
    REQUIRED_COLUMNS,
    UNKNOWN_RATECODE,
    UNKNOWN_ZONE_IDS,
)


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """승차 시각으로부터 시간 관련 파생 변수를 만든다.

    소요시간은 하차-승차 시각의 차이로 계산한다. 시각·요일은 승차 시점에
    알 수 있는 정보이므로 예측 피처로 사용할 수 있다.

    Args:
        df: 원본 DataFrame. tpep_pickup_datetime, tpep_dropoff_datetime 필요.

    Returns:
        pd.DataFrame: duration_min, hour, dow, is_weekend가 추가된 DataFrame.

    Raises:
        KeyError: 필수 시각 컬럼이 없는 경우.
    """
    required = {"tpep_pickup_datetime", "tpep_dropoff_datetime"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"필수 컬럼이 없습니다: {sorted(missing)}")

    df = df.copy()
    delta = df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]
    df["duration_min"] = delta.dt.total_seconds() / 60
    df["hour"] = df["tpep_pickup_datetime"].dt.hour
    df["dow"] = df["tpep_pickup_datetime"].dt.dayofweek
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    return df


def add_speed_feature(df: pd.DataFrame) -> pd.DataFrame:
    """평균 속도(mph)를 계산한다.

    소요시간이 이미 양수로 걸러진 뒤에 호출해야 0으로 나누는 상황을 피할 수 있다.

    Args:
        df: duration_min과 trip_distance가 있는 DataFrame.

    Returns:
        pd.DataFrame: speed_mph가 추가된 DataFrame.

    Raises:
        ValueError: duration_min에 0 이하 값이 남아 있는 경우.
    """
    if (df["duration_min"] <= 0).any():
        raise ValueError("duration_min에 0 이하 값이 남아 있어 속도를 계산할 수 없습니다.")
    df = df.copy()
    df["speed_mph"] = df["trip_distance"] / (df["duration_min"] / 60)
    return df


def diagnose_missing(df: pd.DataFrame) -> dict:
    """결측 현황을 NaN과 코드값 결측으로 나누어 진단한다.

    NYC TLC 데이터는 '알 수 없음'을 NaN이 아니라 약속된 코드값으로 기록한다.
    isna()만으로는 잡히지 않으므로 별도로 집계한다.

    Args:
        df: 진단할 DataFrame.

    Returns:
        dict: nan_table(컬럼별 NaN 수), code_table(코드값 결측 수), duplicates(중복행 수).
    """
    nan_counts = df.isna().sum()
    nan_table = pd.DataFrame({
        "결측수": nan_counts,
        "비율(%)": (nan_counts / len(df) * 100).round(3),
    })
    nan_table = nan_table[nan_table["결측수"] > 0]

    unknown_zone = (
        df["PULocationID"].isin(UNKNOWN_ZONE_IDS) | df["DOLocationID"].isin(UNKNOWN_ZONE_IDS)
    )
    unknown_rate = df["RatecodeID"] == UNKNOWN_RATECODE
    code_table = pd.DataFrame([
        {
            "항목": f"RatecodeID == {UNKNOWN_RATECODE} (unknown)",
            "행수": int(unknown_rate.sum()),
            "비율(%)": round(unknown_rate.mean() * 100, 3),
            "처리": "유지 — 별도 범주로 학습",
        },
        {
            "항목": f"출발/도착 존이 {UNKNOWN_ZONE_IDS} (Unknown/NA)",
            "행수": int(unknown_zone.sum()),
            "비율(%)": round(unknown_zone.mean() * 100, 3),
            "처리": "제거 — 존이 핵심 피처라 미상은 사용 불가",
        },
    ]).set_index("항목")

    return {
        "nan_table": nan_table,
        "code_table": code_table,
        "duplicates": int(df.duplicated().sum()),
        "total_nan": int(nan_counts.sum()),
    }


def diagnose_missing_block(df: pd.DataFrame) -> dict:
    """결측이 무작위인지, 특정 행 블록에 몰려 있는지 판별한다.

    결측이 있는 컬럼들의 결측 위치(불리언 마스크)가 서로 완전히 일치하면,
    값이 개별적으로 빠진 것이 아니라 특정 데이터 소스가 통째로 필드를
    채우지 않았다는 뜻이다. 이 경우 단순 대체(imputation)는 부적절하다.

    Args:
        df: 진단할 원본 DataFrame.

    Returns:
        dict: 블록 존재 여부, 블록 크기, 관련 컬럼, 벤더 분포 비교표.
    """
    nan_columns = [c for c in df.columns if df[c].isna().any()]
    if not nan_columns:
        return {"has_block": False, "columns": [], "block_rows": 0}

    # 첫 번째 결측 컬럼의 마스크를 기준으로, 동일한 마스크를 가진 컬럼을 모은다
    base_mask = df[nan_columns[0]].isna()
    identical = [c for c in nan_columns if df[c].isna().equals(base_mask)]
    has_block = len(identical) > 1

    print(f"  · 결측이 있는 컬럼: {len(nan_columns)}개 -> {nan_columns}")
    if not has_block:
        print("  · 결측 위치가 컬럼마다 달라 무작위 결측으로 판단된다.")
        return {"has_block": False, "columns": nan_columns, "block_rows": 0}

    block_rows = int(base_mask.sum())
    print(f"  · 아래 {len(identical)}개 컬럼의 결측 위치가 완전히 동일하다: {identical}")
    print(f"  · 동일 결측 블록 크기: {block_rows:,}행 ({base_mask.mean() * 100:.1f}%)")
    print("    -> 값이 개별적으로 빠진 것이 아니라, 특정 소스가 필드를 통째로 비운 것이다.")

    # 블록 안팎의 벤더 구성이 다르면 서로 다른 수집 경로임을 뒷받침한다
    vendor_table = pd.DataFrame({
        "결측 블록": df.loc[base_mask, "VendorID"].value_counts(),
        "나머지": df.loc[~base_mask, "VendorID"].value_counts(),
    }).fillna(0).astype(int)
    vendor_table.index.name = "VendorID"
    print("\n  · 블록 안팎의 VendorID 구성")
    print(vendor_table.to_string())

    block_only = [v for v in vendor_table.index if vendor_table.loc[v, "나머지"] == 0]
    rest_only = [v for v in vendor_table.index if vendor_table.loc[v, "결측 블록"] == 0]
    if block_only or rest_only:
        print(f"    -> 블록에만 있는 벤더 {block_only}, 나머지에만 있는 벤더 {rest_only}")
        print("    -> 두 집단은 서로 다른 데이터 파이프라인에서 온 것으로 보인다.")

    return {
        "has_block": True,
        "columns": identical,
        "block_rows": block_rows,
        "block_ratio": float(base_mask.mean()),
        "vendor_table": vendor_table,
        "block_only_vendors": block_only,
        "rest_only_vendors": rest_only,
    }


def _drop_rows(df: pd.DataFrame, mask: pd.Series, label: str, steps: list) -> pd.DataFrame:
    """조건에 해당하는 행을 제거하고 처리 이력을 기록한다.

    제거 단계마다 같은 형식으로 기록하기 위해 공용 헬퍼로 분리했다.

    Args:
        df: 대상 DataFrame.
        mask: 제거할 행이 True인 불리언 Series.
        label: 처리 이력에 남길 설명.
        steps: 이력을 누적할 리스트 (제자리 수정).

    Returns:
        pd.DataFrame: 해당 행이 제거된 DataFrame.
    """
    removed = int(mask.sum())
    result = df[~mask].copy()
    steps.append({"처리 단계": label, "제거 행수": removed, "남은 행수": len(result)})
    print(f"  · {label:<38} -{removed:>7,}  ->  {len(result):,}")
    return result


def clean_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """결측·중복·이상치를 제거해 분석용 데이터셋을 만든다.

    제거 순서는 의존 관계를 따른다. 소요시간을 먼저 거른 뒤에야 속도를
    안전하게 계산할 수 있으므로 속도 기반 필터가 뒤에 온다.

    Args:
        df: 파생 시간 변수가 추가된 DataFrame.

    Returns:
        tuple: (정제된 DataFrame, 단계별 처리 이력 DataFrame).
    """
    subsection("2-2. 결측·중복·이상치 제거")
    steps: list[dict] = []
    start_rows = len(df)
    print(f"  · 시작 행수: {start_rows:,}")

    # (1) 결측치 — 분석에 사용하는 컬럼(config.REQUIRED_COLUMNS)에 NaN이 있으면 제거한다
    missing_mask = df[REQUIRED_COLUMNS].isna().any(axis=1)
    df = _drop_rows(df, missing_mask, "분석 대상 컬럼의 결측치", steps)

    # (2) 중복행
    df = _drop_rows(df, df.duplicated(), "완전 중복행", steps)

    # (3) 관측 기간을 벗어난 승차 시각 — 원본에는 2008/2009년 레코드가 섞여 있다
    pickup = df["tpep_pickup_datetime"]
    out_of_period = (pickup.dt.year != OBSERVATION_YEAR) | (pickup.dt.month != OBSERVATION_MONTH)
    period_label = f"관측 기간({OBSERVATION_YEAR}-{OBSERVATION_MONTH:02d}) 밖 승차 시각"
    df = _drop_rows(df, out_of_period, period_label, steps)

    # (4) 소요시간 이상치 — 속도 계산 전에 반드시 처리한다
    duration_bad = ~df["duration_min"].between(MIN_DURATION_MIN, MAX_DURATION_MIN)
    duration_label = f"소요시간 {MIN_DURATION_MIN:g}분 미만 / {MAX_DURATION_MIN:g}분 초과"
    df = _drop_rows(df, duration_bad, duration_label, steps)

    # (5) 속도 파생 후 속도 이상치
    df = add_speed_feature(df)
    speed_bad = ~df["speed_mph"].between(MIN_SPEED_MPH, MAX_SPEED_MPH)
    df = _drop_rows(
        df, speed_bad, f"평균속도 {MIN_SPEED_MPH:g}mph 미만 / {MAX_SPEED_MPH:g}mph 초과", steps
    )

    # (6) 요금·거리 이상치
    df = _drop_rows(df, df["fare_amount"] <= 0, "요금 0 이하", steps)
    df = _drop_rows(df, df["trip_distance"] > MAX_TRIP_DISTANCE,
                    f"주행거리 {MAX_TRIP_DISTANCE:g}마일 초과", steps)

    # (7) 코드값 결측 — 존 미상은 핵심 피처가 비는 것이므로 제거
    unknown_zone = (
        df["PULocationID"].isin(UNKNOWN_ZONE_IDS) | df["DOLocationID"].isin(UNKNOWN_ZONE_IDS)
    )
    df = _drop_rows(df, unknown_zone, f"출발/도착 존 미상 {UNKNOWN_ZONE_IDS}", steps)

    # (8) 논리적 모순 — 같은 존인데 장거리로 기록된 행
    same_zone_far = (
        (df["PULocationID"] == df["DOLocationID"]) & (df["trip_distance"] > MAX_SAME_ZONE_DISTANCE)
    )
    df = _drop_rows(df, same_zone_far,
                    f"출발=도착인데 {MAX_SAME_ZONE_DISTANCE:g}마일 초과", steps)

    removed = start_rows - len(df)
    print(f"  · 최종 행수: {len(df):,}  (총 제거 {removed:,}행, {removed / start_rows * 100:.2f}%)")
    return df, pd.DataFrame(steps).set_index("처리 단계")


def build_targets(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """정체 여부를 나타내는 두 가지 타깃을 만든다.

    두 정의는 잡아내는 현상이 다르다.
      - jam_abs: 전체 트립 대비 절대적으로 느린 트립. 도심 단거리가 많이 섞인다.
      - jam_rel: 같은 경로의 평소 속도 대비 느린 트립. 경로 성격을 통제하므로
                 '평소보다 막혔다'는 의미에 더 가깝다.

    Args:
        df: speed_mph가 계산된 DataFrame.

    Returns:
        tuple: (타깃이 추가된 DataFrame, 임계값·분포 등 메타 정보 dict).
    """
    subsection("2-3. 정체 타깃 생성")
    df = df.copy()

    # (1) 절대정체 — 전체 평균속도 분포의 하위 33%
    abs_threshold = df["speed_mph"].quantile(JAM_QUANTILE)
    df["jam_abs"] = (df["speed_mph"] < abs_threshold).astype(int)
    print(f"  · 절대정체 임계값: {abs_threshold:.2f} mph "
          f"(정체 비율 {df['jam_abs'].mean() * 100:.1f}%)")

    # (2) 상대정체 — 동일 경로(출발존→도착존)의 중앙 속도 대비 비율
    #     표본이 적은 경로는 중앙값이 불안정하므로 최소 건수 기준을 둔다
    route_stats = df.groupby(["PULocationID", "DOLocationID"])["speed_mph"].agg(["median", "size"])
    reliable = route_stats[route_stats["size"] >= MIN_ROUTE_TRIPS]
    print(f"  · 표본 {MIN_ROUTE_TRIPS}건 이상인 경로: {len(reliable):,}개 "
          f"(전체 경로쌍 {len(route_stats):,}개 중)")

    before = len(df)
    df = df.join(reliable["median"].rename("route_median_mph"),
                 on=["PULocationID", "DOLocationID"], how="inner")
    print(f"  · 경로 기준 매칭 후: {before:,} -> {len(df):,}행 "
          f"(표본 부족 경로 {before - len(df):,}행 제외)")

    df["speed_ratio"] = df["speed_mph"] / df["route_median_mph"]
    rel_threshold = df["speed_ratio"].quantile(JAM_QUANTILE)
    df["jam_rel"] = (df["speed_ratio"] < rel_threshold).astype(int)
    print(f"  · 상대정체 임계값: 평소 속도의 {rel_threshold * 100:.1f}% 미만 "
          f"(정체 비율 {df['jam_rel'].mean() * 100:.1f}%)")

    agreement = float((df["jam_abs"] == df["jam_rel"]).mean())
    print(f"  · 두 정의가 같은 판정을 내린 비율: {agreement * 100:.1f}%")

    # 두 타깃이 실제로 어떤 트립을 잡는지 대조한다
    profile = pd.DataFrame({
        "절대정체": _target_profile(df, "jam_abs"),
        "상대정체": _target_profile(df, "jam_rel"),
    }).T
    print("\n  · 각 타깃이 '정체'로 분류한 트립의 성격")
    print(profile.round(2).to_string())

    meta = {
        "abs_threshold": float(abs_threshold),
        "rel_threshold": float(rel_threshold),
        "abs_ratio": float(df["jam_abs"].mean()),
        "rel_ratio": float(df["jam_rel"].mean()),
        "agreement": agreement,
        "reliable_routes": int(len(reliable)),
        "rows_after_route_join": int(len(df)),
        "profile": profile,
    }
    return df, meta


def _target_profile(df: pd.DataFrame, target: str) -> pd.Series:
    """특정 타깃이 정체로 분류한 트립의 특성을 요약한다.

    두 타깃 정의를 같은 잣대로 비교하기 위해 공용 함수로 분리했다.

    Args:
        df: 타깃이 포함된 DataFrame.
        target: 요약할 타깃 컬럼명.

    Returns:
        pd.Series: 중앙 거리·소요시간·속도와 단거리 비중.
    """
    jam = df[df[target] == 1]
    return pd.Series({
        "중앙 거리(mi)": jam["trip_distance"].median(),
        "중앙 소요(분)": jam["duration_min"].median(),
        "중앙 속도(mph)": jam["speed_mph"].median(),
        "1마일 미만 비중(%)": (jam["trip_distance"] < 1).mean() * 100,
    })


def summarize_shape(df: pd.DataFrame, label: str) -> str:
    """DataFrame 크기를 사람이 읽기 쉬운 문자열로 만든다.

    Args:
        df: 대상 DataFrame.
        label: 앞에 붙일 설명.

    Returns:
        str: 예) '정제 후: 2,829,808행 x 25열'
    """
    return f"{label}: {format_int(len(df))}행 x {df.shape[1]}열"
