import torch
import torch.nn as nn

class VolatilityLoss(nn.Module):
    def __init__(self, lambda_v=0.5):
        super(VolatilityLoss, self).__init__()
        self.mse = nn.MSELoss(reduction='none') # 개별 loss 계산
        self.lambda_v = lambda_v

    def forward(self, prediction, target, volatility):
        """
        loss = MSE + lambda * (MSE * Volatility)
        변동성(Volatility)이 높은 구간에서 틀리면 가중치 증가
        """
        base_loss = self.mse(prediction, target)
        
        # 변동성이 높을수록 Loss를 증폭시켜 모델이 해당 구간을 더 집중 학습하게 함
        weighted_loss = base_loss * (1 + self.lambda_v * volatility)
        
        return weighted_loss.mean()