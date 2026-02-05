import numpy as np

class SignalGatekeeper:
    def __init__(self, window_size=10, threshold=0.3):
        self.history = [] # 최근 예측 성공 여부 (1: 성공, 0: 실패)
        self.window_size = window_size
        self.threshold = threshold

    def update(self, is_correct):
        self.history.append(1 if is_correct else 0)
        if len(self.history) > self.window_size:
            self.history.pop(0)

    def can_trade(self):
        """
        Wilson Score Interval 하한값이 threshold보다 높아야 매매 승인
        즉, 최근 승률이 통계적으로 유의미하게 높아야 함.
        """
        if not self.history:
            return True # 초기에는 관대하게

        n = len(self.history)
        p_hat = sum(self.history) / n
        z = 1.96 # 95% 신뢰수준
        
        # Wilson Score Formula
        denominator = 1 + z**2/n
        center_adjusted_probability = p_hat + z**2 / (2*n)
        adjusted_standard_deviation = z * np.sqrt((p_hat*(1 - p_hat) + z**2 / (4*n)) / n)
        
        lower_bound = (center_adjusted_probability - adjusted_standard_deviation) / denominator
        
        return lower_bound > self.threshold