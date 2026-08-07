"""
프로그램명 : stats_test.py — scipy 기반 t-test 및 p-value 해석
작성자     : 판교 10반 박유진
작성일     : 2026-08-07
설명       : 정체 현상에 대한 가설을 통계적으로 검정한다.
             1) 정체 트립과 비정체 트립의 주행거리 평균 차이 검정
             2) 평일과 주말의 평균 속도 차이 검정
             3) 출퇴근 시간대와 그 외 시간대의 속도 차이 검정
             모든 검정은 등분산을 가정하지 않는 Welch's t-test로 수행하고,
             p-value를 유의수준과 비교해 해석 문구를 함께 출력한다.
변경 이력  : 2026-08-07 최초 작성
실행 방법  : 직접 실행하지 않고 main.py에서 호출한다.
산출 파일  : outputs/tables/ttest_results.csv
"""

import pandas as pd
from scipy import stats

from src.common import interpret_p, subsection, with_particle
from src.config import ALPHA, TABLE_DIR

# 출퇴근 혼잡 시간대 정의 (오전 7~10시, 오후 16~19시)
RUSH_HOURS = list(range(7, 10)) + list(range(16, 20))


def run_ttest(
    group_a: pd.Series, group_b: pd.Series, label_a: str, label_b: str, subject: str
) -> dict:
    """두 집단에 대해 Welch's t-test를 수행하고 결과를 정리한다.

    표본 크기가 다르고 분산이 같다고 보장할 수 없으므로 equal_var=False를 쓴다.

    Args:
        group_a: 첫 번째 집단의 값.
        group_b: 두 번째 집단의 값.
        label_a: 첫 번째 집단 이름.
        label_b: 두 번째 집단 이름.
        subject: 검정 대상 변수 설명.

    Returns:
        dict: 검정통계량·p-value·평균·해석 문구를 담은 결과.

    Raises:
        ValueError: 어느 한 집단의 표본이 2개 미만인 경우.
    """
    a = group_a.dropna()
    b = group_b.dropna()
    if len(a) < 2 or len(b) < 2:
        raise ValueError(f"표본이 부족해 t-test를 수행할 수 없습니다: {subject}")

    result = stats.ttest_ind(a, b, equal_var=False)
    interpretation = interpret_p(float(result.pvalue), ALPHA)
    hypothesis = f"{with_particle(label_a)} {label_b}의 평균은 같다"

    print(f"\n  · 검정 대상 : {subject}")
    print(f"    귀무가설  : {hypothesis}")
    print(f"    {label_a:<16} n={len(a):>9,}  평균={a.mean():8.3f}  표준편차={a.std():7.3f}")
    print(f"    {label_b:<16} n={len(b):>9,}  평균={b.mean():8.3f}  표준편차={b.std():7.3f}")
    print(f"    t = {result.statistic:.4f},  p = {result.pvalue:.4e}")
    print(f"    해석      : {interpretation}")

    return {
        "검정 대상": subject,
        "귀무가설": hypothesis,
        "집단 A": label_a,
        "집단 B": label_b,
        "n(A)": len(a),
        "n(B)": len(b),
        "평균(A)": round(float(a.mean()), 4),
        "평균(B)": round(float(b.mean()), 4),
        "평균 차이": round(float(a.mean() - b.mean()), 4),
        "t 통계량": round(float(result.statistic), 4),
        "p-value": float(result.pvalue),
        "유의성": "유의함" if result.pvalue < ALPHA else "유의하지 않음",
        "해석": interpretation,
    }


def run_all_tests(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """정체와 관련된 세 가지 가설을 순서대로 검정한다.

    Args:
        df: 정제 및 타깃 생성이 끝난 DataFrame.

    Returns:
        tuple: (결과 요약 DataFrame, 결과 dict 리스트).
    """
    subsection("5-1. t-test (Welch, equal_var=False)")
    results = []

    # 검정 1 — 정체 트립은 정말 짧은 거리인가
    results.append(run_ttest(
        df.loc[df["jam_abs"] == 1, "trip_distance"],
        df.loc[df["jam_abs"] == 0, "trip_distance"],
        "정체 트립", "비정체 트립",
        "정체 여부에 따른 주행거리(마일) 차이",
    ))

    # 검정 2 — 주말은 평일보다 덜 막히는가
    results.append(run_ttest(
        df.loc[df["is_weekend"] == 1, "speed_mph"],
        df.loc[df["is_weekend"] == 0, "speed_mph"],
        "주말", "평일",
        "주말/평일에 따른 평균 속도(mph) 차이",
    ))

    # 검정 3 — 출퇴근 시간대가 실제로 더 느린가
    is_rush = df["hour"].isin(RUSH_HOURS)
    results.append(run_ttest(
        df.loc[is_rush, "speed_mph"],
        df.loc[~is_rush, "speed_mph"],
        "출퇴근 시간대", "그 외 시간대",
        "출퇴근 시간대 여부에 따른 평균 속도(mph) 차이",
    ))

    summary = pd.DataFrame(results)
    display_columns = [
        "검정 대상", "평균(A)", "평균(B)", "평균 차이", "t 통계량", "p-value", "유의성",
    ]
    summary_view = summary[display_columns].set_index("검정 대상")

    print("\n  · t-test 결과 요약")
    print(summary_view.to_string())

    _save_ttest(summary)
    return summary_view, results


def _save_ttest(summary: pd.DataFrame) -> None:
    """t-test 결과를 CSV로 저장한다.

    Args:
        summary: 검정 결과 DataFrame.
    """
    path = TABLE_DIR / "ttest_results.csv"
    try:
        summary.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"\n  · 표 저장: tables/{path.name}")
    except OSError as exc:
        print(f"  ! t-test 결과 저장 실패: {exc}")
