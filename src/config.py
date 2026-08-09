"""
프로그램명 : config.py — NYC 택시 정체 예측 프로젝트 설정
작성자     : 판교 10반 박유진
작성일     : 2026-08-07
설명       : 프로젝트 전역에서 사용하는 경로·상수를 한곳에 모은다.
             1) 입출력 경로 정의 및 자동 생성
             2) 원본 데이터 파일 탐색(프로젝트 루트 / data 디렉터리)
             3) 분석·모델링 하이퍼파라미터 상수 정의
변경 이력  : 2026-08-07 최초 작성
실행 방법  : 직접 실행하지 않고 다른 모듈에서 import 하여 사용한다.
산출 파일  : 없음 (outputs/ 하위 디렉터리를 생성함)
"""

from pathlib import Path

# ----------------------------------------------------------------------------
# 1. 경로 설정
# ----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"
FIGURE_DIR = OUTPUT_DIR / "figures"
MODEL_DIR = OUTPUT_DIR / "models"
TABLE_DIR = OUTPUT_DIR / "tables"
REPORT_PATH = OUTPUT_DIR / "report.md"

# 원본 데이터 파일명 — 정제 전 raw 파일을 사용한다.
# 결측치 처리 과정 자체가 분석의 일부이므로 정제본이 아닌 원본에서 시작한다.
DATA_FILENAME = "yellow_tripdata_2026-05.parquet"

# 관측 대상 기간 — 이 범위를 벗어난 승차 시각은 기록 오류로 간주한다
OBSERVATION_YEAR = 2026
OBSERVATION_MONTH = 5

# ----------------------------------------------------------------------------
# 2. 분석 상수
# ----------------------------------------------------------------------------
RANDOM_STATE = 42  # 재현성을 위한 난수 시드
SAMPLE_SIZE = 200_000  # 모델 학습에 사용할 표본 크기 (전체 300만 행은 학습 시간 과다)
TEST_SIZE = 0.2  # 홀드아웃 테스트 비율
CV_FOLDS = 5  # 교차검증 폴드 수
ALPHA = 0.05  # 유의수준 (p-value 해석 기준)

# 정체 판정 기준 — 하위 33%를 정체로 본다
JAM_QUANTILE = 1 / 3
# 상대정체 계산 시 경로(출발존→도착존)별 최소 표본 수
MIN_ROUTE_TRIPS = 30

# ----------------------------------------------------------------------------
# 3. 데이터 정제 경계값
#    NYC TLC 데이터에 남아 있는 물리적으로 불가능한 값을 걸러내기 위한 임계치
# ----------------------------------------------------------------------------
MIN_DURATION_MIN = 1.0  # 1분 미만 주행은 오기록으로 간주
MAX_DURATION_MIN = 180.0  # 3시간 초과 주행은 미터기 미종료로 간주
MIN_SPEED_MPH = 1.0  # 1mph 미만은 사실상 정지 상태
MAX_SPEED_MPH = 70.0  # 70mph 초과는 시내 주행으로 불가능
MAX_TRIP_DISTANCE = 50.0  # 50마일 초과는 관외 이동으로 분석 대상 외
MAX_SAME_ZONE_DISTANCE = 10.0  # 출발=도착인데 10마일 초과면 좌표 오류
UNKNOWN_ZONE_IDS = (264, 265)  # TLC 정의상 264=Unknown, 265=N/A
UNKNOWN_RATECODE = 99  # RatecodeID 99 = 'unknown' (NaN 아닌 코드값 결측)

# ----------------------------------------------------------------------------
# 4. 컬럼 정의
#    목적마다 필요한 컬럼이 다르므로 네 가지 목록으로 나누어 한곳에서 관리한다.
#    (1) 원본 필수 컬럼  (2) 모델 피처  (3) 통계 대상  (4) Polars 스캔 대상
# ----------------------------------------------------------------------------

# (1) 원본에 반드시 값이 있어야 하는 컬럼.
#     아래 (2)(3)을 만들기 위한 원본이므로, 하나라도 결측이면 그 행은 쓸 수 없다.
#     - 시각 2종      : duration_min, hour, dow, is_weekend, speed_mph의 원본
#     - 존/벤더/요율   : 모델 범주형 피처
#     - 거리/승객수    : 모델 수치형 피처이자 통계 대상
#     - 요금 3종      : 통계·상관계수 대상 (모델 피처로는 쓰지 않는다)
REQUIRED_COLUMNS = [
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "PULocationID",
    "DOLocationID",
    "VendorID",
    "RatecodeID",
    "trip_distance",
    "passenger_count",
    "fare_amount",
    "tip_amount",
    "total_amount",
]

# (2) 모델 학습 피처 — 승차 시점에 알 수 있는 정보만 쓴다.
#     duration_min·speed_mph·fare_amount·tip_amount는 하차 후에야 확정되므로
#     여기에 넣으면 타깃 누수가 된다. 의도적으로 제외한 것이다.
NUMERIC_FEATURES = ["hour", "dow", "is_weekend", "trip_distance", "passenger_count"]
CATEGORICAL_FEATURES = ["PULocationID", "DOLocationID", "VendorID", "RatecodeID"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# (3) 기술통계·상관계수 산출 대상.
#     현상을 설명하는 것이 목적이므로 (2)와 달리 사후 정보를 포함해도 된다.
STAT_COLUMNS = [
    "trip_distance",
    "duration_min",
    "speed_mph",
    "fare_amount",
    "tip_amount",
    "total_amount",
    "passenger_count",
]

# (4) Polars Lazy 스캔으로 읽을 컬럼.
#     scan_parquet의 projection pushdown 효과를 확인하기 위해 필요한 컬럼만 읽는다.
LAZY_SCAN_COLUMNS = [
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "trip_distance",
    "PULocationID",
    "DOLocationID",
    "passenger_count",
]

# 학습할 타깃 2종 — 정의가 다르면 성능과 해석이 어떻게 맞바뀌는지 비교한다
TARGETS = {
    "jam_abs": "절대정체 (전체 트립 평균속도 하위 33%)",
    "jam_rel": "상대정체 (동일 경로 평소 속도 대비 하위 33%)",
}


def resolve_data_path() -> Path:
    """원본 parquet 파일의 실제 위치를 찾아 반환한다.

    data/ 디렉터리와 프로젝트 루트를 순서대로 탐색한다. 두 곳 모두 사용할 수
    있도록 하여, 데이터 파일을 옮기지 않아도 실행되게 한다.

    Returns:
        Path: 찾은 parquet 파일 경로.

    Raises:
        FileNotFoundError: 어느 위치에서도 파일을 찾지 못한 경우.
    """
    candidates = [DATA_DIR / DATA_FILENAME, BASE_DIR / DATA_FILENAME]
    for path in candidates:
        if path.exists():
            return path
    searched = "\n  - ".join(str(p) for p in candidates)
    raise FileNotFoundError(
        f"원본 데이터 파일을 찾을 수 없습니다. 아래 경로를 확인하세요:\n  - {searched}"
    )


def ensure_output_dirs() -> None:
    """산출물 디렉터리를 생성한다. 이미 있으면 아무 일도 하지 않는다."""
    for directory in (OUTPUT_DIR, FIGURE_DIR, MODEL_DIR, TABLE_DIR):
        directory.mkdir(parents=True, exist_ok=True)
