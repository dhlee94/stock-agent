import torch
import matplotlib.pyplot as plt
import seaborn as sns

# def visualize_attention(text, model, tokenizer):
#     inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
#     # attention을 출력하도록 설정
#     outputs = model(**inputs, output_attentions=True)
    
#     # 마지막 레이어의 attention (shape: [batch, heads, seq_len, seq_len])
#     attention = outputs.attentions[-1][0].mean(dim=0).detach().cpu().numpy()
    
#     tokens = tokenizer.convert_ids_to_tokens(inputs['input_ids'][0])
    
#     plt.figure(figsize=(10, 8))
#     sns.heatmap(attention, xticklabels=tokens, yticklabels=tokens, cmap='viridis')
#     plt.title("FinBERT Attention Map")
#     plt.show()
def visualize_attention(attention_weights, tokens):
    """
    (추후 구현) Attention Map 시각화
    지금은 로그만 출력합니다.
    """
    print(f"📊 [XAI] Attention Weights Sample: {attention_weights[0][:5]}...")
    pass