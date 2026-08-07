"""
프로그램명 : main.py — NYC 옐로우캡 정체 예측 End2End 분석 파이프라인
작성자     : 판교 10반 박유진
작성일     : 2026-08-07
설명       : 데이터 로딩부터 보고서 생성까지 전 과정을 순서대로 실행한다.
             1단계 데이터 준비   : Pandas / Polars 이중 로딩 및 결과 비교
             2단계 전처리       : 결측 진단(구조적 결측 탐지)·중복·이상치 제거, 타깃 생성
             3단계 EDA         : 기술통계, 상관계수, 시간대별 집계
             4단계 시각화       : Seaborn 정적 차트, Plotly 인터랙티브 차트
             5단계 통계 분석    : scipy ttest_ind로 t-test 수행 및 p-value 해석
             6단계 ML Pipeline : 전처리+모델 파이프라인 학습, 평가, joblib 저장
             7단계 자동화       : 분석 결과를 report.md로 자동 생성
변경 이력  : 2026-08-07 최초 작성
실행 방법  : 프로젝트 루트에서 `python main.py`
             (데이터 파일은 data/ 또는 프로젝트 루트에 두면 자동으로 찾는다)
산출 파일  : outputs/report.md            — 분석 보고서
             outputs/figures/*.png        — Seaborn 정적 차트 3종
             outputs/figures/*.html       — Plotly 인터랙티브 차트 2종
             outputs/models/*.pkl         — 학습된 파이프라인 2종
             outputs/tables/*.csv         — 기술통계·상관계수·t-test·모델 비교표
"""

import sys
import time

from src import eda, model, preprocess, report, stats_test, visualize
from src.common import section
from src.config import ensure_output_dirs, resolve_data_path
from src.data_loader import compare_loaders


def run_pipeline() -> dict:
    """전체 분석 파이프라인을 순서대로 실행한다.

    각 단계의 결과를 context 딕셔너리에 누적해 마지막 보고서 생성에 사용한다.

    Returns:
        dict: 전 단계의 분석 결과를 담은 context.

    Raises:
        FileNotFoundError: 원본 데이터 파일을 찾지 못한 경우.
        RuntimeError: 로딩 또는 보고서 저장에 실패한 경우.
    """
    context: dict = {}
    ensure_output_dirs()

    # ------------------------------------------------------------------
    # 1단계 — 데이터 준비 (Pandas / Polars 이중 로딩 및 비교)
    # ------------------------------------------------------------------
    section("1단계. 데이터 준비 — Pandas / Polars 이중 로딩")
    data_path = resolve_data_path()
    print(f"  · 원본 파일: {data_path.name}")
    load_result = compare_loaders(data_path)
    context["load"] = load_result
    raw_df = load_result.pop("dataframe")

    # ------------------------------------------------------------------
    # 2단계 — 전처리 (결측 진단, 정제, 타깃 생성)
    # ------------------------------------------------------------------
    section("2단계. 전처리 — 결측·중복·이상치 처리 및 타깃 생성")
    print("\n[2-1. 결측 진단]")
    print("-" * 78)
    df = preprocess.add_time_features(raw_df)
    context["missing"] = preprocess.diagnose_missing(df)
    print(f"  · 전체 NaN 셀 수: {context['missing']['total_nan']:,}")
    print(f"  · 완전 중복행: {context['missing']['duplicates']:,}")
    print()
    context["block"] = preprocess.diagnose_missing_block(df)

    print("\n  · NaN이 아닌 코드값 결측")
    print(context["missing"]["code_table"].to_string())

    df, clean_steps = preprocess.clean_dataset(df)
    context["clean_steps"] = clean_steps

    df, target_meta = preprocess.build_targets(df)
    context["target_meta"] = target_meta
    print(f"\n  · {preprocess.summarize_shape(df, '최종 분석 데이터')}")

    # ------------------------------------------------------------------
    # 3단계 — EDA (기술통계, 상관계수)
    # ------------------------------------------------------------------
    section("3단계. EDA — 기술통계 및 상관관계")
    context["eda"] = eda.run_eda(df)

    # ------------------------------------------------------------------
    # 4단계 — 시각화 (Seaborn 정적 + Plotly 인터랙티브)
    # ------------------------------------------------------------------
    section("4단계. 시각화 — Seaborn 정적 / Plotly 인터랙티브")
    context["figures"] = visualize.create_all_figures(df, context["eda"])

    # ------------------------------------------------------------------
    # 5단계 — 통계 분석 (t-test)
    # ------------------------------------------------------------------
    section("5단계. 통계 분석 — t-test 및 p-value 해석")
    _, ttest_results = stats_test.run_all_tests(df)
    context["ttests"] = ttest_results

    # ------------------------------------------------------------------
    # 6단계 — ML Pipeline (학습, 평가, 저장)
    # ------------------------------------------------------------------
    section("6단계. ML Pipeline — 전처리 + 모델 학습 및 저장")
    context["modeling"] = model.run_modeling(df)

    # ------------------------------------------------------------------
    # 7단계 — 보고서 자동 생성
    # ------------------------------------------------------------------
    section("7단계. 자동화 — report.md 생성")
    context["report_path"] = report.write_report(context)

    return context


def main() -> int:
    """진입점. 파이프라인을 실행하고 예외를 처리한다.

    Returns:
        int: 정상 종료 시 0, 오류 발생 시 1.
    """
    started = time.perf_counter()
    section("NYC 옐로우캡 정체 예측 — End2End 분석 시작")

    try:
        context = run_pipeline()
    except FileNotFoundError as exc:
        print(f"\n[오류] 데이터 파일을 찾을 수 없습니다.\n{exc}", file=sys.stderr)
        return 1
    except (KeyError, ValueError) as exc:
        print(f"\n[오류] 데이터 형식이 예상과 다릅니다: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"\n[오류] 실행 중 문제가 발생했습니다: {exc}", file=sys.stderr)
        return 1
    except MemoryError:
        print("\n[오류] 메모리가 부족합니다. config.SAMPLE_SIZE를 줄여 다시 시도하세요.",
              file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - started
    section("분석 완료")
    print(f"  · 총 소요 시간 : {elapsed:.1f}초")
    print(f"  · 보고서       : {context['report_path']}")
    print(f"  · 정적 차트    : {len(context['figures']['seaborn'])}개")
    print(f"  · 인터랙티브   : {len(context['figures']['plotly'])}개")
    print(f"  · 저장된 모델  : {len(context['modeling']['results'])}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
