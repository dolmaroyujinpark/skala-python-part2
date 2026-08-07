"""
프로그램명 : model.py — sklearn Pipeline 기반 정체 예측 모델
작성자     : 판교 10반 박유진
작성일     : 2026-08-07
설명       : 승차 시점 정보만으로 정체 여부를 예측하는 분류 모델을 학습한다.
             1) ColumnTransformer로 수치형/범주형 전처리를 분리 구성
             2) Pipeline으로 전처리 + 모델을 하나의 객체로 결합
             3) 절대정체·상대정체 두 타깃을 각각 학습해 성능을 비교
             4) 최빈값 기준선(DummyClassifier) 대비 개선폭을 함께 산출
             5) 정확도·F1·정밀도·재현율 출력 후 joblib으로 모델 저장
             누수 방지 : 소요시간·요금·팁 등 하차 후에야 알 수 있는 값은 피처에서 제외.
변경 이력  : 2026-08-07 최초 작성
실행 방법  : 직접 실행하지 않고 main.py에서 호출한다.
산출 파일  : outputs/models/*.pkl, outputs/tables/model_comparison.csv
"""

import time

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.common import subsection
from src.config import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    MODEL_DIR,
    NUMERIC_FEATURES,
    RANDOM_STATE,
    SAMPLE_SIZE,
    TABLE_DIR,
    TARGETS,
    TEST_SIZE,
)

# 존 ID는 카디널리티가 높아, 표본이 적은 범주는 하나로 묶어 차원 폭발을 막는다
MIN_CATEGORY_FREQUENCY = 50
# 랜덤 포레스트 트리 개수
N_ESTIMATORS = 100
# 리프 노드 최소 표본 수.
# 기본값(1)은 트리를 끝까지 쪼개 과적합되고 모델 파일이 636MB까지 커진다.
# 5로 두면 F1이 오히려 0.7606 -> 0.7651로 개선되면서 크기는 55MB로 줄어든다.
MIN_SAMPLES_LEAF = 5


def build_preprocessor() -> ColumnTransformer:
    """수치형/범주형을 나누어 처리하는 전처리기를 만든다.

    수치형은 중앙값 대체 후 표준화하고, 범주형은 최빈값 대체 후 원-핫 인코딩한다.
    존 ID(PULocationID, DOLocationID)는 숫자로 저장돼 있지만 크기에 의미가 없는
    명목형이므로 범주형으로 취급한다.

    Returns:
        ColumnTransformer: 두 갈래 전처리를 묶은 변환기.
    """
    numeric_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("encode", OneHotEncoder(
            handle_unknown="infrequent_if_exist",
            min_frequency=MIN_CATEGORY_FREQUENCY,
        )),
    ])
    return ColumnTransformer([
        ("numeric", numeric_pipeline, NUMERIC_FEATURES),
        ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
    ])


def build_pipeline(model: object) -> Pipeline:
    """전처리기와 분류 모델을 하나의 Pipeline으로 결합한다.

    전처리를 Pipeline 안에 두면 학습 시 fit된 통계값이 예측 시 그대로 적용되어
    테스트 데이터 정보가 학습에 새어드는 것을 막는다.

    Args:
        model: sklearn 분류기 객체.

    Returns:
        Pipeline: 전처리 + 모델 파이프라인.
    """
    return Pipeline([
        ("preprocess", build_preprocessor()),
        ("classifier", model),
    ])


def _evaluate(y_true: pd.Series, y_pred: pd.Series) -> dict:
    """예측 결과로부터 분류 평가 지표를 계산한다.

    기준선 모델과 본 모델에 같은 지표를 적용하기 위해 공용 함수로 분리했다.

    Args:
        y_true: 실제 라벨.
        y_pred: 예측 라벨.

    Returns:
        dict: 정확도·F1(macro)·정밀도·재현율.
    """
    return {
        "정확도": accuracy_score(y_true, y_pred),
        "F1(macro)": f1_score(y_true, y_pred, average="macro"),
        "정밀도(macro)": precision_score(y_true, y_pred, average="macro", zero_division=0),
        "재현율(macro)": recall_score(y_true, y_pred, average="macro", zero_division=0),
    }


def train_and_evaluate(df: pd.DataFrame, target: str) -> dict:
    """지정한 타깃에 대해 모델을 학습하고 평가한다.

    Args:
        df: 피처와 타깃이 모두 있는 DataFrame.
        target: 학습할 타깃 컬럼명 (jam_abs 또는 jam_rel).

    Returns:
        dict: 평가 지표, 기준선 대비 개선폭, 학습된 파이프라인 등.

    Raises:
        KeyError: 타깃 또는 피처 컬럼이 없는 경우.
    """
    missing = [c for c in FEATURE_COLUMNS + [target] if c not in df.columns]
    if missing:
        raise KeyError(f"모델 학습에 필요한 컬럼이 없습니다: {missing}")

    # 전체 300만 행은 학습 시간이 과도하므로 표본을 추출한다
    sample_size = min(SAMPLE_SIZE, len(df))
    sample = df.sample(sample_size, random_state=RANDOM_STATE)
    features = sample[FEATURE_COLUMNS]
    labels = sample[target]

    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=labels
    )
    print(f"\n  · 타깃 '{target}' — {TARGETS[target]}")
    print(f"    표본 {sample_size:,}행 (학습 {len(x_train):,} / 테스트 {len(x_test):,})")
    print(f"    클래스 분포: {labels.value_counts(normalize=True).round(3).to_dict()}")

    # (1) 기준선 — 항상 최빈 클래스만 예측하는 모델
    baseline = build_pipeline(DummyClassifier(strategy="most_frequent"))
    baseline.fit(x_train, y_train)
    baseline_scores = _evaluate(y_test, baseline.predict(x_test))

    # (2) 본 모델 — 랜덤 포레스트
    pipeline = build_pipeline(RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        min_samples_leaf=MIN_SAMPLES_LEAF,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    ))
    start = time.perf_counter()
    pipeline.fit(x_train, y_train)
    fit_seconds = time.perf_counter() - start

    y_pred = pipeline.predict(x_test)
    scores = _evaluate(y_test, y_pred)

    n_features = pipeline.named_steps["preprocess"].transform(x_test.head(5)).shape[1]
    print(f"    전처리 후 피처 수: {n_features}개  |  학습 시간: {fit_seconds:.1f}초")
    print(f"    {'지표':<14}{'기준선':>10}{'모델':>10}{'개선':>10}")
    for key in scores:
        gain = scores[key] - baseline_scores[key]
        print(f"    {key:<14}{baseline_scores[key]:>10.4f}{scores[key]:>10.4f}{gain:>+10.4f}")

    print("\n    분류 리포트")
    report = classification_report(
        y_test, y_pred, target_names=["비정체", "정체"], digits=4, zero_division=0
    )
    print("      " + report.replace("\n", "\n      "))

    matrix = pd.DataFrame(
        confusion_matrix(y_test, y_pred),
        index=["실제 비정체", "실제 정체"],
        columns=["예측 비정체", "예측 정체"],
    )
    print("    혼동 행렬")
    print("      " + matrix.to_string().replace("\n", "\n      "))

    return {
        "target": target,
        "description": TARGETS[target],
        "pipeline": pipeline,
        "scores": scores,
        "baseline_scores": baseline_scores,
        "fit_seconds": fit_seconds,
        "n_features": int(n_features),
        "n_samples": sample_size,
        "class_ratio": float(labels.mean()),
        "report_text": report,
        "confusion_matrix": matrix,
    }


def save_model(pipeline: Pipeline, target: str) -> str:
    """학습된 파이프라인을 joblib으로 저장한다.

    전처리기가 Pipeline 안에 포함돼 있으므로, 저장된 파일 하나만 불러오면
    원본 형태의 입력을 그대로 예측에 사용할 수 있다.

    Args:
        pipeline: 저장할 학습 완료 파이프라인.
        target: 타깃 이름. 파일명에 사용한다.

    Returns:
        str: 저장된 파일의 상대 경로. 실패 시 빈 문자열.
    """
    path = MODEL_DIR / f"jam_model_{target}.pkl"
    try:
        joblib.dump(pipeline, path)
        size_mb = path.stat().st_size / 1024 / 1024
        print(f"  · 모델 저장: models/{path.name} ({size_mb:.1f} MB)")
        return f"models/{path.name}"
    except (OSError, ValueError) as exc:
        print(f"  ! 모델 저장 실패({target}): {exc}")
        return ""


def run_modeling(df: pd.DataFrame) -> dict:
    """두 타깃에 대해 학습·평가·저장을 수행하고 결과를 비교한다.

    Args:
        df: 정제 및 타깃 생성이 끝난 DataFrame.

    Returns:
        dict: 타깃별 결과와 비교표.
    """
    subsection("6-1. Pipeline 구성 및 학습")
    results = {}
    for target in TARGETS:
        results[target] = train_and_evaluate(df, target)

    subsection("6-2. 모델 저장 (joblib)")
    for target, result in results.items():
        result["model_path"] = save_model(result["pipeline"], target)

    subsection("6-3. 두 타깃 정의 비교")
    rows = []
    for target, result in results.items():
        rows.append({
            "타깃": target,
            "정의": result["description"],
            "정확도": round(result["scores"]["정확도"], 4),
            "F1(macro)": round(result["scores"]["F1(macro)"], 4),
            "기준선 F1": round(result["baseline_scores"]["F1(macro)"], 4),
            "F1 개선": round(
                result["scores"]["F1(macro)"] - result["baseline_scores"]["F1(macro)"], 4
            ),
            "학습(초)": round(result["fit_seconds"], 1),
        })
    comparison = pd.DataFrame(rows).set_index("타깃")
    print(comparison.to_string())

    try:
        comparison.to_csv(TABLE_DIR / "model_comparison.csv", encoding="utf-8-sig")
        print("\n  · 표 저장: tables/model_comparison.csv")
    except OSError as exc:
        print(f"  ! 비교표 저장 실패: {exc}")

    return {"results": results, "comparison": comparison}
