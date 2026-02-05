import torch
import torch.nn as nn
import torch.nn.functional as F

class MultimodalFusion(nn.Module):
    def __init__(self, text_dim=768, price_dim=50, hidden_dim=128):
        super(MultimodalFusion, self).__init__()
        
        # 1. Feature Projection (차원 통일)
        self.text_proj = nn.Linear(text_dim, hidden_dim)
        self.price_proj = nn.Linear(price_dim, hidden_dim)
        
        # 2. Cross-Attention Mechanism
        # Query: Price (시장 상황), Key/Value: Text (뉴스)
        # 시장 상황에 맞는 뉴스를 집중해서 보겠다는 의도
        self.attention = nn.MultiheadAttention(embed_dim=hidden_dim, num_heads=4, batch_first=True)
        
        # 3. Fusion Gate
        self.gate = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.Sigmoid()
        )
        
        # 4. Final Processing
        self.layer_norm = nn.LayerNorm(hidden_dim)
        self.dropout = nn.Dropout(0.2)

    def forward(self, text_features, price_features):
        # text_features: (batch, text_dim) -> (batch, 1, hidden_dim)
        # price_features: (batch, price_dim) -> (batch, 1, hidden_dim)
        
        text_emb = self.text_proj(text_features).unsqueeze(1)
        price_emb = self.price_proj(price_features).unsqueeze(1)
        
        # Cross Attention: Price가 Query가 되어 Text 정보를 탐색
        attn_output, attn_weights = self.attention(query=price_emb, key=text_emb, value=text_emb)
        
        # Residual Connection & Normalization
        combined = torch.cat([price_emb, attn_output], dim=-1) # (batch, 1, hidden*2)
        gate_val = self.gate(combined)
        
        # Gated Fusion
        fused = gate_val * price_emb + (1 - gate_val) * attn_output
        fused = self.layer_norm(fused)
        
        return fused.squeeze(1) # (batch, hidden_dim)