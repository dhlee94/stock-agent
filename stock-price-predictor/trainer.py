import torch
import torch.nn as nn
import torch.optim as optim
from src.models.fusion import MultimodalFusion
from src.models.losses import VolatilityLoss

class MultimodalTrainer:
    def __init__(self, price_dim=50, text_dim=768, learning_rate=1e-4):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 모델 초기화
        self.fusion_layer = MultimodalFusion(text_dim=text_dim, price_dim=price_dim).to(self.device)
        # 퓨전된 벡터(128차원)를 받아 가격(1차원) 예측
        self.fc_out = nn.Linear(128, 1).to(self.device)
        
        # Loss & Optimizer
        self.criterion = VolatilityLoss(lambda_v=0.7)
        self.optimizer = optim.Adam(
            list(self.fusion_layer.parameters()) + list(self.fc_out.parameters()), 
            lr=learning_rate
        )

    def train_step(self, price_features, text_features, target_price, volatility):
        """1 Step 학습"""
        self.fusion_layer.train()
        self.fc_out.train()
        self.optimizer.zero_grad()

        # Device 이동
        price_features = price_features.to(self.device) # (B, 50)
        text_features = text_features.to(self.device)   # (B, 768)
        target_price = target_price.to(self.device)
        volatility = volatility.to(self.device)

        # Forward
        fused = self.fusion_layer(text_features, price_features) # (B, 128)
        prediction = self.fc_out(fused) # (B, 1)

        # Loss
        loss = self.criterion(prediction, target_price, volatility)

        # Backward
        loss.backward()
        self.optimizer.step()

        return loss.item()

    def save_model(self, path="models/multimodal_fusion.pt"):
        torch.save({
            'fusion_state_dict': self.fusion_layer.state_dict(),
            'fc_out_state_dict': self.fc_out.state_dict(),
        }, path)
        print(f"💾 모델 저장 완료: {path}")

if __name__ == "__main__":
    print("🚀 트레이닝 모듈 테스트 시작...")
    # 더미 데이터로 테스트
    trainer = MultimodalTrainer()
    
    # Batch Size=4
    dummy_price = torch.randn(4, 50)
    dummy_text = torch.randn(4, 768)
    dummy_target = torch.randn(4, 1)
    dummy_vol = torch.abs(torch.randn(4, 1)) # 변동성은 양수

    loss = trainer.train_step(dummy_price, dummy_text, dummy_target, dummy_vol)
    print(f"✅ 테스트 학습 완료. Loss: {loss:.4f}")