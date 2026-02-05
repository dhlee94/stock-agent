import math
import random
from scipy import stats

def get_wald_interval(success, n, z=1.96):
    """가장 기본적인 정규 근사 방식 (Wald)"""
    p_hat = success / n
    se = math.sqrt((p_hat * (1 - p_hat)) / n)
    return p_hat - z * se, p_hat + z * se

def get_wilson_interval(success, n, z=1.96):
    """샘플이 적을 때 유용한 Wilson Score 방식 (추천 시스템용)"""
    p_hat = success / n
    denom = 1 + (z**2 / n)
    center = (p_hat + (z**2 / (2 * n))) / denom
    spread = (z * math.sqrt((p_hat * (1 - p_hat) / n) + (z**2 / (4 * n**2)))) / denom
    return center - spread, center + spread

def get_agresti_coull_interval(success, n, z=1.96):
    """성공 2회, 실패 2회를 더해 보정하는 방식"""
    n_tilde = n + z**2
    p_tilde = (success + (z**2 / 2)) / n_tilde
    se = math.sqrt((p_tilde * (1 - p_tilde)) / n_tilde)
    return p_tilde - z * se, p_tilde + z * se

def get_clopper_pearson_interval(success, n, alpha=0.05):
    """
    이항분포를 직접 사용하는 엄격한 방식 (Exact Method)
    Beta 분포의 역함수를 풀기 위해 scipy를 사용합니다.
    """
    lower = stats.beta.ppf(alpha / 2, success, n - success + 1) if success > 0 else 0
    upper = stats.beta.ppf(1 - alpha / 2, success + 1, n - success) if success < n else 1
    return lower, upper

def get_fisher_exact(table):
    """
    두 집단 간의 비율 차이가 유의미한지 검정
    팩토리얼 계산 오버플로우를 막기 위해 scipy를 사용합니다.
    """
    odds_ratio, p_value = stats.fisher_exact(table)
    return odds_ratio, p_value

def get_bootstrap_interval(success, n, iterations=10000):
    """수치적 재추출을 통한 비모수적 방식"""
    data = [1] * success + [0] * (n - success)
    resampled_means = []
    for _ in range(iterations):
        sample = [random.choice(data) for _ in range(n)]
        resampled_means.append(sum(sample) / n)
    resampled_means.sort()

    return resampled_means[int(iterations * 0.025)], resampled_means[int(iterations * 0.975)]

def main():
    # 1. 예시 데이터 설정
    # 상황: 지난 50일 동안 주가가 상승한 날이 10일이라고 가정 (상승 확률 20%)
    n_days = 50
    up_days = 10
    alpha = 0.05  # 95% 신뢰구간
    
    print(f"📊 분석 대상: {n_days}일 중 {up_days}일 상승 (비율: {up_days/n_days:.2%})")
    print("-" * 50)

    # 2. 각 방법별 신뢰구간 계산 및 출력
    # (1) Wald (Normal Approximation)
    low_w, high_w = get_wald_interval(up_days, n_days)
    print(f"1. Normal (Wald)    : [{low_w:.4f}, {high_w:.4f}]")

    # (2) Wilson Score
    low_ws, high_ws = get_wilson_interval(up_days, n_days)
    print(f"2. Wilson Score     : [{low_ws:.4f}, {high_ws:.4f}] (추천!)")

    # (3) Agresti-Coull
    low_ac, high_ac = get_agresti_coull_interval(up_days, n_days)
    print(f"3. Agresti-Coull    : [{low_ac:.4f}, {high_ac:.4f}]")

    # (4) Clopper-Pearson (Exact)
    low_cp, high_cp = get_clopper_pearson_interval(up_days, n_days)
    print(f"4. Clopper-Pearson  : [{low_cp:.4f}, {high_cp:.4f}] (보수적)")

    # (5) Bootstrap (수치적 추정)
    low_bs, high_bs = get_bootstrap_interval(up_days, n_days)
    print(f"5. Bootstrap        : [{low_bs:.4f}, {high_bs:.4f}]")

    print("-" * 50)

    # 3. Fisher's Exact Test 예시
    # 상황: A 전략(10번 중 8번 성공) vs B 전략(10번 중 2번 성공) 비교
    print("🧪 전략 비교 (Fisher's Exact Test):")
    table = [[8, 2], [2, 8]]  # [[A성공, A실패], [B성공, B실패]]
    odds, p_val = get_fisher_exact(table)
    print(f"- 오즈비(Odds Ratio): {odds:.2f}")
    print(f"- p-value: {p_val:.4f} ({'유의미한 차이 있음' if p_val < 0.05 else '차이 없음'})")

if __name__ == "__main__":
    main()
