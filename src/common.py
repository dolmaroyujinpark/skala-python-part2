"""
프로그램명 : common.py — 공용 유틸리티
작성자     : 판교 10반 박유진
작성일     : 2026-08-07
설명       : 여러 모듈에서 반복되는 로직을 한곳에 모아 중복을 제거한다.
             1) 콘솔 구분선 출력 (section)
             2) p-value 해석 문구 생성 (interpret_p)
             3) 실행 시간 측정 (timed)
             4) 표 형태 데이터를 마크다운으로 변환 (to_markdown_table)
변경 이력  : 2026-08-07 최초 작성
실행 방법  : 직접 실행하지 않고 다른 모듈에서 import 하여 사용한다.
산출 파일  : 없음
"""

import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

import pandas as pd

from src.config import ALPHA

# 콘솔 출력 폭 — 구분선 길이를 통일하기 위해 사용
LINE_WIDTH = 78


def section(title: str) -> None:
    """콘솔에 단계 제목을 구분선과 함께 출력한다.

    실행 로그의 가독성을 위해 모든 단계에서 동일한 형식을 사용한다.

    Args:
        title: 출력할 단계 제목.
    """
    print("\n" + "=" * LINE_WIDTH)
    print(f" {title}")
    print("=" * LINE_WIDTH)


def subsection(title: str) -> None:
    """콘솔에 하위 항목 제목을 출력한다.

    Args:
        title: 출력할 하위 항목 제목.
    """
    print(f"\n[{title}]")
    print("-" * LINE_WIDTH)


def interpret_p(p_value: float, alpha: float = ALPHA) -> str:
    """p-value를 유의수준과 비교해 해석 문구를 만든다.

    t-test 등 여러 검정에서 동일한 해석 규칙을 쓰기 위해 공용 함수로 분리했다.

    Args:
        p_value: 검정 결과 p-value.
        alpha: 유의수준. 기본값은 config.ALPHA(0.05).

    Returns:
        str: 귀무가설 기각 여부를 담은 한국어 해석 문구.
    """
    if p_value < alpha:
        return (
            f"p = {p_value:.4e} < α = {alpha} 이므로 귀무가설을 기각한다. "
            "두 집단의 평균 차이는 통계적으로 유의하다."
        )
    return (
        f"p = {p_value:.4e} >= α = {alpha} 이므로 귀무가설을 기각하지 못한다. "
        "두 집단의 평균 차이는 통계적으로 유의하지 않다."
    )


@contextmanager
def timed(label: str) -> Any:
    """with 블록의 실행 시간을 측정해 출력한다.

    Args:
        label: 측정 대상을 설명하는 라벨.

    Yields:
        dict: 종료 후 'elapsed' 키에 경과 시간(초)이 담기는 딕셔너리.
    """
    holder: dict[str, float] = {"elapsed": 0.0}
    start = time.perf_counter()
    try:
        yield holder
    finally:
        holder["elapsed"] = time.perf_counter() - start
        print(f"  · {label}: {holder['elapsed']:.3f}초")


def measure(func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, float]:
    """함수를 실행하고 결과와 경과 시간을 함께 돌려준다.

    Pandas와 Polars의 로딩 속도를 동일한 방식으로 재기 위해 사용한다.

    Args:
        func: 실행할 함수.
        *args: func에 전달할 위치 인자.
        **kwargs: func에 전달할 키워드 인자.

    Returns:
        tuple: (함수 반환값, 경과 시간(초)).
    """
    start = time.perf_counter()
    result = func(*args, **kwargs)
    return result, time.perf_counter() - start


def to_markdown_table(df: pd.DataFrame, floatfmt: str = "{:.4f}") -> str:
    """DataFrame을 마크다운 표 문자열로 변환한다.

    report.md 자동 생성 시 외부 의존성(tabulate) 없이 표를 만들기 위해
    직접 구현했다. 인덱스는 첫 번째 열로 포함한다.

    Args:
        df: 변환할 DataFrame.
        floatfmt: 실수 값 포맷 문자열.

    Returns:
        str: 마크다운 표 문자열.
    """

    def fmt(value: Any) -> str:
        """셀 하나를 문자열로 변환한다."""
        if isinstance(value, float):
            return floatfmt.format(value)
        return str(value)

    index_name = df.index.name or ""
    headers = [index_name] + [str(c) for c in df.columns]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for idx, row in df.iterrows():
        cells = [str(idx)] + [fmt(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def with_particle(word: str) -> str:
    """한국어 단어 뒤에 '와/과' 조사를 받침 유무에 맞춰 붙인다.

    t-test 귀무가설 문구를 집단 이름에 따라 자동 생성할 때 사용한다.
    한글 음절은 유니코드상 (코드 - 0xAC00) % 28 == 0 이면 받침이 없다.

    Args:
        word: 조사를 붙일 단어.

    Returns:
        str: 조사가 붙은 문자열. 예) '정체 트립' -> '정체 트립과'
    """
    if not word:
        return word
    last = word[-1]
    if "가" <= last <= "힣":
        has_final = (ord(last) - 0xAC00) % 28 != 0
        return word + ("과" if has_final else "와")
    # 한글이 아닌 문자로 끝나면 기본형을 사용한다
    return word + "와"


def format_int(value: float) -> str:
    """정수를 천 단위 구분 기호가 있는 문자열로 변환한다.

    Args:
        value: 변환할 수치.

    Returns:
        str: 예) 3021962 -> '3,021,962'
    """
    return f"{int(value):,}"
