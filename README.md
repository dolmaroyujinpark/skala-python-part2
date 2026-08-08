# NYC 옐로우캡 정체 예측 — End2End 데이터 분석 프로젝트

SKALA 교육과정 판교 10반 5조 / Day 2 종합 실습

승차 시점에 알 수 있는 정보만으로 **해당 트립이 정체 구간에 걸릴지** 예측한다.

## 팀

**5조** — 박유진, 강용현, 김인성, 이승석, 이중헌, 최윤영

데이터셋(NYC Yellow Taxi 2026-05)만 팀에서 통일하고, **가설은 각자 세워 따로 돌린 뒤 결과를
모아 비교**했다. 이 저장소는 그중 '정체 예측' 가설의 파이프라인이다.

---

## 분석 가설

> 승차 시각·요일·출발/도착 존·예상 주행거리·승객 수만으로 트립의 정체 여부를 예측할 수 있다.

소요시간·요금·팁처럼 **하차 후에야 확정되는 값은 타깃 누수**를 일으키므로 피처에서 제외했다.

정체의 정의는 하나로 정하지 않고 **두 가지를 함께 학습해 비교**한다.

| 타깃 | 정의 | 의미 |
|---|---|---|
| `jam_abs` | 전체 트립 평균속도 하위 33% | 절대적으로 느린 트립 |
| `jam_rel` | 동일 경로(출발존→도착존) 평소 속도 대비 하위 33% | 평소보다 막힌 트립 |

두 정의를 비교하는 이유는 **점수가 높은 가설이 곧 좋은 가설은 아니라는 점**을 확인하기 위해서다.

---

## 실행 방법

```bash
# 1. 의존성 설치
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 데이터 준비 — data/ 또는 프로젝트 루트에 아래 파일을 둔다
#    https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2026-05.parquet

# 3. 전체 파이프라인 실행
python main.py
```

실행 시간은 약 15초이며, 완료 후 `outputs/` 하위에 모든 산출물이 생성된다.

정적 검사는 `ruff check main.py src/` 로 수행한다(설정은 `pyproject.toml`).

---

## 폴더 구조

```
skala-python-part2/
├── main.py                  # 전체 파이프라인 실행 (1~7단계)
├── requirements.txt
├── pyproject.toml           # ruff 정적 검사 설정
├── README.md
├── data/
│   └── yellow_tripdata_2026-05.parquet   # 원본 (git 추적 제외)
├── src/
│   ├── config.py            # 경로·상수·피처 정의
│   ├── common.py            # 공용 유틸 (구분선, p-value 해석, 마크다운 표)
│   ├── data_loader.py       # 1단계 Pandas / Polars 이중 로딩 및 비교
│   ├── preprocess.py        # 2단계 결측 진단·정제·타깃 생성
│   ├── eda.py               # 3단계 기술통계·상관계수
│   ├── visualize.py         # 4단계 Seaborn 정적 / Plotly 인터랙티브
│   ├── stats_test.py        # 5단계 t-test 및 p-value 해석
│   ├── model.py             # 6단계 sklearn Pipeline 학습·평가·저장
│   └── report.py            # 7단계 report.md 자동 생성
├── docs/
│   ├── 컬럼_모델_정리.md      # 조원 공유용 컬럼·모델 정리
│   ├── captures/            # 실행결과 캡처
│   └── tools/               # 제출용 보고서(docx) 생성 스크립트
└── outputs/
    ├── report.md            # 자동 생성 분석 보고서
    ├── figures/             # 정적 차트 3종(PNG) + 인터랙티브 2종(HTML)
    ├── models/              # 학습된 파이프라인 2종(joblib)
    └── tables/              # 기술통계·상관계수·t-test·모델 비교표(CSV)
```

---

## 파이프라인 단계

| 단계 | 모듈 | 내용 |
|---|---|---|
| 1 | `data_loader.py` | Pandas / Polars Eager / Polars Lazy 3방식 로딩, 결과 일치 검증 |
| 2 | `preprocess.py` | 구조적 결측 블록 탐지, 코드값 결측 진단, 이상치 제거, 타깃 생성 |
| 3 | `eda.py` | 기술통계(평균·표준편차·분위수), 피어슨 상관계수, 시간대별 집계 |
| 4 | `visualize.py` | Seaborn 히트맵·분포도, Plotly 이중축 차트·존별 막대 |
| 5 | `stats_test.py` | Welch's t-test 3종 및 p-value 해석 |
| 6 | `model.py` | ColumnTransformer + RandomForest Pipeline, 두 타깃 비교, joblib 저장 |
| 7 | `report.py` | 전 단계 결과를 `report.md`로 자동 생성 |

---

## 주요 결과

### 결측은 무작위가 아니었다

`passenger_count`, `RatecodeID`, `store_and_fwd_flag`, `congestion_surcharge`, `Airport_fee`
**5개 컬럼의 결측 위치가 완전히 일치**했다. 크기는 **955,371행(23.4%)**이다.

블록 안팎의 벤더 구성도 겹치지 않는다 — **VendorID 6은 결측 블록에만, 7은 나머지에만** 존재한다.
즉 값이 개별적으로 빠진 것이 아니라 **서로 다른 데이터 파이프라인이 섞여 있었다**.
평균·최빈값 대체는 존재하지 않는 값을 지어내는 셈이므로 이 블록은 제거했다.

### NaN이 아닌 결측이 따로 있다

`RatecodeID = 99`(unknown, 3.44%)와 존 ID `264/265`(Unknown/N-A, 0.62%)는
약속된 코드값이라 `isna()`로 잡히지 않는다. 존 미상은 핵심 피처가 비는 것이라 제거했고,
`RatecodeID = 99`는 '미상'이라는 사실 자체가 정보이므로 별도 범주로 남겼다.

### 모델 성능

| 타깃 | 정확도 | F1(macro) | 기준선 F1 | 개선 |
|---|---|---|---|---|
| `jam_abs` 절대정체 | 0.7964 | 0.7651 | 0.3966 | +0.3685 |
| `jam_rel` 상대정체 | 0.7339 | 0.6575 | 0.4002 | +0.2573 |

절대정체가 점수는 높지만, 그 차이의 상당 부분은 **'도심 단거리인지'를 맞히는 데서 온다**
(절대정체로 분류된 트립의 39.2%가 1마일 미만, 상대정체는 29.5%).
상대정체는 경로 성격을 통제하므로 점수는 낮아도 '평소보다 막혔다'는 의미에 더 충실하다.

---

## 참고

- 데이터 출처 : [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
- 원본 데이터(약 70MB)와 학습된 모델 파일은 용량 문제로 git에 포함하지 않는다(`.gitignore` 참고).
