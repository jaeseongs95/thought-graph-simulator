"""TTS v1.0의 범주형 참조 선택기.

이 모듈은 산술·입력 검사·선택만 구현하며 LLM 또는 CTA 실행 커널이 아니다.
권한(admissible)과 적용 가능성(trusted)은 외부의 신뢰된 실행기가 판정한다.
operator_id는 역할명이 아니라 버전·인수 결합이 끝난 실행 선택의 고유 키이다.
Python 3.10 이상, 표준 라이브러리만 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Mapping, Sequence

__version__ = "1.0"
SUM_TOLERANCE = 1e-10
TRANSITION_ALPHABET = tuple(
    f"pass_A{a}_D{d}_M{m}"
    for a in range(5) for d in ("0", "1", "2", "3", "4", "5+") for m in range(3)
) + ("reject", "unknown", "stop")


def _finite_real(value: Real, name: str) -> float:
    """문자열·불리언을 수치로 자동 해석하지 않는다."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name}: 불리언이 아닌 실수가 필요합니다.")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{name}: 표현 가능한 유한 실수가 필요합니다.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name}: 유한 실수가 필요합니다.")
    return number


def distribution(values: Sequence[float]) -> tuple[float, ...]:
    """유한 비음수 분포를 검사한다. 합 허용오차는 1e-10, 재정규화하지 않는다."""
    if values is None or isinstance(values, (str, bytes)):
        raise ValueError("분포는 숫자의 비어 있지 않은 열이어야 합니다.")
    try:
        p = tuple(_finite_real(x, "확률") for x in values)
    except TypeError as exc:
        raise ValueError("분포는 숫자의 열이어야 합니다.") from exc
    if not p or any(x < 0 for x in p):
        raise ValueError("분포는 비어 있지 않은 비음수 값이어야 합니다.")
    try:
        total = math.fsum(p)
    except OverflowError as exc:
        raise ValueError("분포의 합이 수치 표현 범위를 벗어났습니다.") from exc
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=SUM_TOLERANCE):
        raise ValueError("분포의 합은 1이어야 합니다.")
    return p


def js_bits(p: Sequence[float], q: Sequence[float]) -> float:
    """밑이 2인 JS 발산. 같은 범주 순서를 사용하는 분포를 받는다.

    log2(p / ((p+q)/2))를 1+log2(p)-log2(p+q)로 계산하여
    극소 확률에서 중간 평균값의 언더플로를 피한다.
    """
    p, q = distribution(p), distribution(q)
    if len(p) != len(q):
        raise ValueError("두 분포는 같은 범주 집합을 사용해야 합니다.")
    terms = []
    for a, b in zip(p, q):
        total = a + b
        if a > 0:
            terms.append(a * (1.0 + math.log2(a) - math.log2(total)))
        if b > 0:
            terms.append(b * (1.0 + math.log2(b) - math.log2(total)))
    value = 0.5 * math.fsum(terms)
    if not math.isfinite(value) or not -SUM_TOLERANCE <= value <= 1.0 + SUM_TOLERANCE:
        raise ValueError("발산 계산이 허용 수치 범위를 벗어났습니다.")
    # 검사한 입력의 반올림 오차만 제한하며, 입력을 재정규화하지 않는다.
    return min(1.0, max(0.0, value))


@dataclass(frozen=True)
class Option:
    operator_id: str
    base_utility: float
    admissible: bool = True
    predicted_transition: tuple[float, ...] | None = None


@dataclass(frozen=True)
class Decision:
    operator_id: str | None
    scores: Mapping[str, float]
    reason: str


def select(options: Sequence[Option], prior: Sequence[float] | None,
           strength: float, trusted: bool) -> Decision:
    """U(o)-strength*JS(P_o,Q)를 최대화하며 동점은 고유 키 사전순이다.

    trusted=False 또는 strength=0이면 분포를 읽지 않고 같은 U로 복귀한다.
    형식 오류는 ValueError, 빈 허용 집합은 operator_id=None으로 반환한다.
    실제 복구·종료·권한 검사는 호출 실행기의 책임이다.
    """
    strength = _finite_real(strength, "가중치")
    if strength < 0:
        raise ValueError("가중치는 비음수여야 합니다.")
    if type(trusted) is not bool:
        raise ValueError("trusted는 bool이어야 합니다.")
    options = tuple(options)
    if any(not isinstance(o, Option) for o in options):
        raise ValueError("선택 후보는 Option이어야 합니다.")
    ids = [o.operator_id for o in options]
    if any(not isinstance(x, str) or not x.strip() for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("실행 선택 ID는 비어 있지 않은 고유 문자열이어야 합니다.")
    if any(type(o.admissible) is not bool for o in options):
        raise ValueError("admissible은 bool이어야 합니다.")
    allowed = sorted((o for o in options if o.admissible), key=lambda o: o.operator_id)
    if not allowed:
        return Decision(None, {}, "NO_ADMISSIBLE_OPERATOR")
    utilities = {o.operator_id: _finite_real(o.base_utility, "효용") for o in allowed}
    active = trusted and strength > 0
    checked_prior = distribution(prior) if active else None
    scores: dict[str, float] = {}
    for o in allowed:
        penalty = 0.0
        if active:
            if o.predicted_transition is None:
                raise ValueError("활성 선택에는 모든 허용 연산의 분포가 필요합니다.")
            penalty = strength * js_bits(o.predicted_transition, checked_prior)
        score = utilities[o.operator_id] - penalty
        if not math.isfinite(score):
            raise ValueError("점수가 유한 수치 범위를 벗어났습니다.")
        scores[o.operator_id] = score
    chosen = max(allowed, key=lambda o: scores[o.operator_id])
    return Decision(chosen.operator_id, scores, "TTS_ACTIVE" if active else "BASELINE")


def demonstration() -> dict:
    """논문의 구성 사례. 실제 관측·학습·LLM 과제 성능이 아니다."""
    opts = [Option("derive", .60, True, (.80, .10, .10)),
            Option("review", .56, True, (.10, .80, .10)),
            Option("forbidden_commit", 10., False, (.10, .80, .10))]
    prior = (.10, .80, .10)
    decisions = {
        "baseline": select(opts, prior, .20, False),
        "tts_active": select(opts, prior, .20, True),
        "opposite_prior": select(opts, (.80, .10, .10), .20, True),
    }
    return {
        "release_version": __version__,
        "scope": "constructed arithmetic example; not LLM results",
        "alphabet": ["pass_A1_D2_M0", "pass_A1_D1_M1", "reject"],
        "omitted_zero_mass_categories": 90,
        "strength": .20,
        "js_derive_vs_review_prior": js_bits(opts[0].predicted_transition, prior),
        **{k: {"selected": v.operator_id, "scores": dict(v.scores)} for k, v in decisions.items()},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(demonstration(), ensure_ascii=False, indent=2))
