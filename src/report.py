"""
프로그램명 : report.py — 분석 결과 report.md 자동 생성
작성자     : 판교 10반 박유진
작성일     : 2026-08-07
설명       : 각 분석 단계가 반환한 결과를 모아 마크다운 보고서를 자동 생성한다.
             1) 데이터 로딩 비교 결과 (Pandas vs Polars)
             2) 결측·중복·이상치 처리 이력
             3) 기술통계·상관계수
             4) 시각화 산출물 목록
             5) t-test 결과와 p-value 해석
             6) 모델 성능 비교 및 결론
변경 이력  : 2026-08-07 최초 작성
실행 방법  : 직접 실행하지 않고 main.py에서 호출한다.
산출 파일  : outputs/report.md
"""

from datetime import datetime
from typing import Any

from src.common import format_int, subsection, to_markdown_table
from src.config import (
    ALPHA,
    JAM_QUANTILE,
    LAZY_SCAN_COLUMNS,
    MIN_ROUTE_TRIPS,
    RANDOM_STATE,
    REPORT_PATH,
    SAMPLE_SIZE,
)


def _section_header(context: dict[str, Any]) -> list[str]:
    """보고서 머리말과 분석 개요를 만든다.

    Args:
        context: main.py가 축적한 전체 결과 dict.

    Returns:
        list[str]: 마크다운 문단 리스트.
    """
    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    load = context["load"]
    return [
        "# 뉴욕 옐로우캡 정체 예측 분석 보고서",
        "",
        "> 이 문서는 `main.py` 실행 시 `src/report.py`가 자동 생성합니다.",
        "",
        f"- **생성 일시** : {generated}",
        "- **작성자** : 판교 10반 박유진",
        (
            f"- **데이터** : NYC TLC Yellow Taxi 2026년 5월 "
            f"({format_int(load['shape'][0])}행 × {load['shape'][1]}열)"
        ),
        f"- **난수 시드** : {RANDOM_STATE} (재현 가능)",
        "",
        "## 분석 목표",
        "",
        "승차 시점에 알 수 있는 정보(승차 시각·요일·출발/도착 존·예상 주행거리·승객 수)만으로",
        "해당 트립이 **정체 구간에 걸릴지** 예측한다.",
        "소요시간·요금·팁처럼 하차 후에야 확정되는 값은 타깃 누수를 일으키므로 피처에서 제외했다.",
        "",
        "정체의 정의는 하나로 정하지 않고 **두 가지를 함께 학습해 비교**한다.",
        "",
        f"- **절대정체(jam_abs)** : 전체 트립 평균 속도 분포의 하위 {JAM_QUANTILE * 100:.0f}%",
        (
            f"- **상대정체(jam_rel)** : 동일 경로(출발존→도착존)의 평소 중앙 속도 대비 하위 "
            f"{JAM_QUANTILE * 100:.0f}%"
        ),
        "",
    ]


def _section_loading(context: dict[str, Any]) -> list[str]:
    """Pandas / Polars 로딩 비교 절을 만든다.

    Args:
        context: 전체 결과 dict.

    Returns:
        list[str]: 마크다운 문단 리스트.
    """
    load = context["load"]
    lines = [
        "## 1. 데이터 준비 — Pandas / Polars 이중 로딩",
        "",
        "동일한 parquet 파일을 두 라이브러리로 읽어 결과가 일치하는지 검증했다.",
        "",
        "| 방식 | 소요 시간(초) |",
        "|---|---|",
        f"| Pandas `read_parquet` | {load['pandas_sec']:.3f} |",
        f"| Polars `read_parquet` (Eager) | {load['polars_sec']:.3f} |",
        f"| Polars `scan_parquet` (Lazy, 필요 컬럼만) | {load['lazy_sec']:.3f} |",
        "",
        f"Polars가 Pandas 대비 **{load['speedup']:.2f}배** 빠르게 읽었다.",
        "",
        "### 결과 일치 검증",
        "",
        f"- 행/열 개수 일치 : **{load['shape_match']}**",
        (
            f"- 컬럼별 결측 수 일치 : **{load['missing_match']}** "
            f"(전체 결측 {format_int(load['total_missing'])}건)"
        ),
        "",
        "### 분위수 계산 시 주의점",
        "",
        "Polars의 `quantile` 기본 보간법은 `nearest`, Pandas는 `linear`이다.",
        "옵션을 맞추지 않으면 같은 데이터에서도 분위수가 달라진다.",
        "",
        to_markdown_table(load["quantile_table"]),
        "",
    ]
    if load["interpolation_differs"]:
        lines.append(
            "실제로 값 차이가 확인되었으므로, 두 라이브러리 결과를 대조할 때는"
        )
        lines.append('`interpolation="linear"`를 명시해야 한다.')
    else:
        lines.append(
            "이 컬럼에서는 두 보간법의 결과가 일치했으나, 일반적으로는 명시가 필요하다."
        )
    lines.append("")

    agg = load["aggregation"]
    lines += [
        "### 동일 집계 대조 — Polars Lazy vs Pandas",
        "",
        "같은 집계(승객 수별 평균·중앙 속도)를 두 방식으로 수행해 결과를 대조했다.",
        "Polars는 `scan_parquet`으로 실행 계획을 세운 뒤 필터·집계까지 Lazy로 구성하고",
        "`collect()` 시점에 한 번에 실행한다.",
        "",
        f"- Polars `scan_parquet` + `group_by` : {load['lazy_sec']:.3f}초",
        f"- Pandas `groupby` : {load['pandas_agg_sec']:.3f}초",
        (
            f"- Lazy 집계가 **{load['agg_speedup']:.2f}배** 빠르다 "
            f"(필요한 {len(LAZY_SCAN_COLUMNS)}개 컬럼만 읽기 때문)"
        ),
        "",
        to_markdown_table(agg["table"], floatfmt="{:.3f}"),
        "",
    ]
    if agg["polars_groups"] > agg["pandas_groups"]:
        lines += [
            (
                f"**두 결과의 그룹 수가 다르다** — Pandas {agg['pandas_groups']}개, "
                f"Polars {agg['polars_groups']}개."
            ),
            "",
            "Pandas의 `groupby`는 그룹 키가 결측인 행을 **기본적으로 제외**하지만,",
            "Polars의 `group_by`는 null을 **하나의 그룹으로 유지**한다.",
            f"이 데이터에서는 **{format_int(agg['null_group_trips'])}건**이 그 차이에 해당한다.",
            "",
            "즉 Pandas만 썼다면 이 88만 건이 집계에서 조용히 빠진 것을 알아채지 못했을 것이다.",
            "두 결과를 맞추려면 Pandas에 `dropna=False`를 주거나, 집계 전에 그룹 키의 결측을",
            "명시적으로 제거해야 한다.",
            "",
            "이 null 그룹이 곧 2장에서 다루는 **구조적 결측 블록**이다.",
            "표의 평균속도가 중앙속도보다 훨씬 큰 것은 이 집계가 정제 전 원본을 대상으로 해",
            "이상치가 남아 있기 때문이며, 이상치 제거는 2장에서 수행한다.",
            "",
        ]
    return lines


def _section_cleaning(context: dict[str, Any]) -> list[str]:
    """결측·중복·이상치 처리 절을 만든다.

    Args:
        context: 전체 결과 dict.

    Returns:
        list[str]: 마크다운 문단 리스트.
    """
    diag = context["missing"]
    block = context["block"]
    steps = context["clean_steps"]

    lines = [
        "## 2. 결측치·중복·이상치 처리",
        "",
        "### 2-1. 결측 진단 — 무작위 결측이 아니었다",
        "",
    ]

    if diag["nan_table"].empty:
        lines.append("NaN 형태의 결측은 발견되지 않았다.")
    else:
        lines.append("| 컬럼 | 결측 수 | 비율(%) |")
        lines.append("|---|---|---|")
        for column, row in diag["nan_table"].iterrows():
            lines.append(
                f"| `{column}` | {format_int(row['결측수'])} | {row['비율(%)']:.3f} |"
            )
    lines.append("")

    if block.get("has_block"):
        columns = ", ".join(f"`{c}`" for c in block["columns"])
        lines += [
            (
                f"**핵심 발견** — 위 {len(block['columns'])}개 컬럼({columns})의 결측 위치가 "
                "서로 **완전히 일치**한다."
            ),
            (
                f"해당 블록의 크기는 **{format_int(block['block_rows'])}행"
                f"({block['block_ratio'] * 100:.1f}%)** 이다."
            ),
            "",
            (
                "즉 값이 개별적으로 빠진 것이 아니라, "
                "**특정 데이터 소스가 해당 필드를 통째로 비운 것**이다."
            ),
            "이 경우 평균·최빈값 대체는 존재하지 않는 값을 지어내는 셈이므로 적절하지 않다.",
            "",
            "이를 뒷받침하는 근거로, 블록 안팎의 벤더 구성이 서로 겹치지 않는다.",
            "",
            to_markdown_table(block["vendor_table"], floatfmt="{:.0f}"),
            "",
        ]
        if block["block_only_vendors"] or block["rest_only_vendors"]:
            lines.append(
                f"- 결측 블록에만 존재하는 벤더 : {block['block_only_vendors']}"
            )
            lines.append(
                f"- 나머지 구간에만 존재하는 벤더 : {block['rest_only_vendors']}"
            )
            lines.append("")
        lines.append("따라서 이 블록은 대체하지 않고 **제거**하기로 결정했다.")
        lines.append("")

    lines += [
        "### 2-2. NaN이 아닌 '코드값 결측'",
        "",
        "NYC TLC 데이터는 '알 수 없음'을 NaN이 아니라 약속된 코드값으로 기록한다.",
        "`isna()`만으로는 잡히지 않으므로 별도로 진단했다.",
        "",
        to_markdown_table(diag["code_table"], floatfmt="{:.3f}"),
        "",
        "`RatecodeID = 99`는 제거하지 않았다. '미상'이라는 사실 자체가 정보이며,",
        "보조 피처이므로 별도 범주로 두면 나머지 피처로 예측이 가능하기 때문이다.",
        "",
        "### 2-3. 단계별 처리 이력",
        "",
        "제거 순서는 의존 관계를 따른다. 소요시간을 먼저 걸러야 0으로 나누지 않고",
        "평균 속도를 계산할 수 있으므로, 속도 기반 필터가 뒤에 온다.",
        "",
        "| 처리 단계 | 제거 행수 | 남은 행수 |",
        "|---|---|---|",
    ]
    for label, row in steps.iterrows():
        removed = format_int(row["제거 행수"])
        remaining = format_int(row["남은 행수"])
        lines.append(f"| {label} | {removed} | {remaining} |")
    lines += [
        "",
        f"- 중복행 : {format_int(diag['duplicates'])}건",
        "",
    ]
    return lines


def _section_targets(context: dict[str, Any]) -> list[str]:
    """타깃 정의 절을 만든다.

    Args:
        context: 전체 결과 dict.

    Returns:
        list[str]: 마크다운 문단 리스트.
    """
    meta = context["target_meta"]
    return [
        "## 3. 정체 타깃 정의",
        "",
        "| 항목 | 절대정체 (`jam_abs`) | 상대정체 (`jam_rel`) |",
        "|---|---|---|",
        (
            f"| 기준 | 전체 평균속도 하위 {JAM_QUANTILE * 100:.0f}% | "
            f"동일 경로 평소 속도 대비 하위 {JAM_QUANTILE * 100:.0f}% |"
        ),
        (
            f"| 임계값 | {meta['abs_threshold']:.2f} mph | "
            f"평소 속도의 {meta['rel_threshold'] * 100:.1f}% |"
        ),
        f"| 정체 비율 | {meta['abs_ratio'] * 100:.1f}% | {meta['rel_ratio'] * 100:.1f}% |",
        "",
        (
            f"- 상대정체는 표본 {MIN_ROUTE_TRIPS}건 이상인 경로 "
            f"**{format_int(meta['reliable_routes'])}개**를 기준으로 계산했다."
        ),
        f"- 두 정의가 같은 판정을 내린 비율 : **{meta['agreement'] * 100:.1f}%**",
        "",
        "### 두 타깃이 실제로 잡아내는 트립",
        "",
        to_markdown_table(meta["profile"], floatfmt="{:.2f}"),
        "",
        "절대정체는 **1마일 미만 단거리 비중이 뚜렷하게 높다**. 맨해튼 도심의 짧은 트립은",
        "교통 상황과 무관하게 원래 느리기 때문이다. 즉 절대정체는 '교통 정체'뿐 아니라",
        "'도심 단거리라는 트립 성격'을 함께 잡는다.",
        "상대정체는 경로별 평소 속도를 기준으로 삼아 이 성격을 통제하므로,",
        "'같은 길인데 오늘 유독 느렸다'는 의미에 더 가깝다.",
        "",
    ]


def _section_stats(context: dict[str, Any]) -> list[str]:
    """기술통계·상관계수·t-test 절을 만든다.

    Args:
        context: 전체 결과 dict.

    Returns:
        list[str]: 마크다운 문단 리스트.
    """
    eda = context["eda"]
    lines = [
        "## 4. 통계 분석",
        "",
        "### 4-1. 기술통계 (평균·표준편차·분위수)",
        "",
        to_markdown_table(eda["describe"], floatfmt="{:.3f}"),
        "",
        "### 4-2. 변수 간 상관계수 (피어슨)",
        "",
        to_markdown_table(eda["correlation"], floatfmt="{:.3f}"),
        "",
        "평균 속도와 상관이 큰 변수는 다음과 같다.",
        "",
        to_markdown_table(eda["top_correlation"], floatfmt="{:.3f}"),
        "",
        "주행거리와 평균 속도의 상관이 높은 것은, 장거리 트립이 고속도로를 이용해",
        "빠르고 단거리 트립은 도심 신호에 걸려 느리기 때문이다.",
        "",
        "### 4-3. 시간대별 속도",
        "",
        f"- 가장 느린 시간대 : **{eda['slowest_hour']}시 ({eda['slowest_speed']:.2f} mph)**",
        f"- 가장 빠른 시간대 : **{eda['fastest_hour']}시 ({eda['fastest_speed']:.2f} mph)**",
        f"- 속도 격차 : **{eda['fastest_speed'] / eda['slowest_speed']:.2f}배**",
        "",
        "### 4-4. t-test 및 p-value 해석",
        "",
        "표본 크기가 다르고 등분산을 가정할 수 없으므로 Welch's t-test",
        f"(`scipy.stats.ttest_ind(equal_var=False)`)를 사용했다. 유의수준은 α = {ALPHA}이다.",
        "",
    ]
    for result in context["ttests"]:
        lines += [
            f"#### {result['검정 대상']}",
            "",
            f"- 귀무가설 : {result['귀무가설']}",
            (
                f"- {result['집단 A']} : n = {format_int(result['n(A)'])}, "
                f"평균 = {result['평균(A)']:.3f}"
            ),
            (
                f"- {result['집단 B']} : n = {format_int(result['n(B)'])}, "
                f"평균 = {result['평균(B)']:.3f}"
            ),
            f"- t = {result['t 통계량']:.4f}, p = {result['p-value']:.4e}",
            f"- **해석** : {result['해석']}",
            "",
        ]
    return lines


def _section_visuals(context: dict[str, Any]) -> list[str]:
    """시각화 산출물 절을 만든다.

    Args:
        context: 전체 결과 dict.

    Returns:
        list[str]: 마크다운 문단 리스트.
    """
    figures = context["figures"]
    lines = [
        "## 5. 시각화 산출물",
        "",
        "모든 차트에 제목과 축 레이블을 포함했다.",
        "",
        "### Seaborn 정적 차트",
        "",
    ]
    for path in figures["seaborn"]:
        lines.append(f"![{path}]({path})")
        lines.append("")
    lines += ["### Plotly 인터랙티브 차트", ""]
    for path in figures["plotly"]:
        lines.append(f"- [{path}]({path}) — 브라우저에서 열면 확대·툴팁 확인 가능")
    lines.append("")
    return lines


def _section_model(context: dict[str, Any]) -> list[str]:
    """ML 모델 결과 절을 만든다.

    Args:
        context: 전체 결과 dict.

    Returns:
        list[str]: 마크다운 문단 리스트.
    """
    modeling = context["modeling"]
    lines = [
        "## 6. ML Pipeline",
        "",
        "### 6-1. 파이프라인 구성",
        "",
        "```",
        "Pipeline",
        " ├─ preprocess : ColumnTransformer",
        " │   ├─ numeric     : SimpleImputer(median) → StandardScaler",
        " │   └─ categorical : SimpleImputer(most_frequent) → OneHotEncoder",
        " └─ classifier : RandomForestClassifier",
        "```",
        "",
        "전처리를 Pipeline 안에 넣었기 때문에, 학습 데이터에서 구한 통계값(중앙값·평균·분산)이",
        "테스트 데이터에 그대로 적용된다. 전처리를 Pipeline 밖에서 미리 수행하면 테스트 데이터의",
        "정보가 학습에 새어드는 **데이터 누수**가 발생한다.",
        "",
        "존 ID(`PULocationID`, `DOLocationID`)는 정수로 저장돼 있지만 숫자의 크기에 의미가 없는",
        "명목형이므로 범주형으로 취급해 원-핫 인코딩했다.",
        "",
        f"학습 표본은 {format_int(SAMPLE_SIZE)}행이며, 층화 추출로 8:2 분할했다.",
        "",
        "### 6-2. 성능 비교",
        "",
        to_markdown_table(modeling["comparison"], floatfmt="{:.4f}"),
        "",
        "기준선은 항상 최빈 클래스만 예측하는 `DummyClassifier`이다.",
        "정확도만 보면 불균형 데이터에서 기준선이 높게 나오므로, **F1(macro) 개선폭**을 함께 봐야",
        "모델이 실제로 학습했는지 판단할 수 있다.",
        "",
    ]
    for target, result in modeling["results"].items():
        lines += [
            f"### 6-3. `{target}` 상세 — {result['description']}",
            "",
            f"- 전처리 후 피처 수 : {result['n_features']}개",
            f"- 학습 시간 : {result['fit_seconds']:.1f}초",
            (
                f"- 정확도 : {result['scores']['정확도']:.4f} / "
                f"F1(macro) : {result['scores']['F1(macro)']:.4f}"
            ),
            "",
            "```",
            result["report_text"].rstrip(),
            "```",
            "",
            "혼동 행렬",
            "",
            to_markdown_table(result["confusion_matrix"], floatfmt="{:.0f}"),
            "",
            f"- 저장된 모델 : `outputs/{result['model_path']}`",
            "",
        ]
    return lines


def _section_conclusion(context: dict[str, Any]) -> list[str]:
    """결론 및 한계 절을 만든다.

    Args:
        context: 전체 결과 dict.

    Returns:
        list[str]: 마크다운 문단 리스트.
    """
    modeling = context["modeling"]
    abs_result = modeling["results"]["jam_abs"]
    rel_result = modeling["results"]["jam_rel"]
    abs_f1 = abs_result["scores"]["F1(macro)"]
    rel_f1 = rel_result["scores"]["F1(macro)"]

    return [
        "## 7. 결론",
        "",
        "1. **승차 시점 정보만으로 정체 예측이 가능하다.** 소요시간·요금 등 사후 정보를 모두",
        f"   제외했음에도 절대정체 F1(macro) {abs_f1:.4f}, 상대정체 {rel_f1:.4f}로",
        "   기준선을 크게 상회했다.",
        "",
        "2. **타깃 정의를 바꾸면 성능과 해석이 맞바뀐다.** 절대정체가 상대정체보다 점수가 높지만,",
        "   그 차이의 상당 부분은 '도심 단거리인지'를 맞히는 데서 온다. 상대정체는 경로 성격을",
        "   통제하므로 점수는 낮아도 '평소보다 막혔다'는 의미에 더 충실하다.",
        "   **높은 점수가 곧 좋은 가설은 아니다.**",
        "",
        "3. **결측은 세어보는 것이 아니라 구조를 봐야 한다.** 이 데이터의 결측은 무작위가 아니라",
        "   특정 벤더 블록에 몰려 있었다. `dropna()`나 평균 대체로 처리했다면 서로 다른 두 개의",
        "   데이터 소스가 섞인 채로 분석이 진행됐을 것이다.",
        "",
        "## 8. 한계와 개선 방향",
        "",
        "- **날씨·사고·공사 정보가 없다.** 실제 정체의 주요 원인이 데이터에 없으므로, 모델은",
        "  '이 시간 이 경로는 통상 느리다'는 평균적 경향만 학습한다. 외부 데이터를 결합하면",
        "  같은 경로 내 변동을 더 설명할 수 있다.",
        "- **정체 기준을 하위 33%로 임의 설정했다.** 분위수 대신 절대 속도(예: 5mph 미만)나",
        "  경로별 하위 10% 등으로 바꾸면 결과가 달라진다. 기준의 민감도 분석이 필요하다.",
        "- **단일 월(2026년 5월) 데이터만 사용했다.** 계절성과 연간 추세를 반영하지 못한다.",
        "- **하이퍼파라미터를 튜닝하지 않았다.** 시간 제약으로 기본값을 사용했으며,",
        "  `GridSearchCV`를 Pipeline에 결합하면 추가 개선 여지가 있다.",
        "",
    ]


def build_report(context: dict[str, Any]) -> str:
    """전체 보고서 마크다운 문자열을 만든다.

    Args:
        context: main.py가 축적한 전체 결과 dict.

    Returns:
        str: 완성된 마크다운 문서.
    """
    lines: list[str] = []
    for builder in (
        _section_header,
        _section_loading,
        _section_cleaning,
        _section_targets,
        _section_stats,
        _section_visuals,
        _section_model,
        _section_conclusion,
    ):
        lines.extend(builder(context))
    lines.append("---")
    lines.append("")
    lines.append("*본 보고서는 `python main.py` 실행 시 자동 생성됩니다.*")
    return "\n".join(lines)


def write_report(context: dict[str, Any]) -> str:
    """보고서를 생성해 outputs/report.md로 저장한다.

    Args:
        context: 전체 결과 dict.

    Returns:
        str: 저장된 파일 경로. 실패 시 빈 문자열.

    Raises:
        RuntimeError: 보고서 저장에 실패한 경우.
    """
    subsection("7-1. report.md 자동 생성")
    content = build_report(context)
    try:
        REPORT_PATH.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"보고서 저장 실패: {REPORT_PATH}") from exc

    size_kb = REPORT_PATH.stat().st_size / 1024
    line_count = content.count("\n") + 1
    print(f"  · 저장: outputs/{REPORT_PATH.name} ({line_count:,}줄, {size_kb:.1f} KB)")
    return str(REPORT_PATH)
