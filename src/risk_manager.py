"""
리스크 매니저(Risk Manager) - 목표가, 손절가, 손익비(Risk/Reward)를 계산하는 모듈
"""
import json
from typing import Dict, Any, Optional


def calculate_risk_levels(
    current_price: float,
    technical_data: Dict[str, Any],
    ai_prediction: Optional[Dict[str, Any]] = None,
    default_stop_loss_pct: float = 0.07  # 7% default
) -> Dict[str, Any]:
    """
    기술적 분석 결과와 AI 예측을 기반으로 리스크 관리 수준(목표가, 손절가, 손익비)을 계산합니다.
    
    Args:
        current_price: 현재 주가
        technical_data: 기술적 분석 데이터 (`technical_analysis` 도구 결과)
        ai_prediction: AI 예측 데이터 (선택)
        default_stop_loss_pct: 기본 손절 비율 (0.07 = -7%)
        
    Returns:
        target_price, stop_loss, risk_reward_ratio, reasoning 등을 포함한 dict
    """
    if current_price <= 0:
        return {"error": "유효하지 않은 현재가입니다."}
    
    # Extract Bollinger Bands for support/resistance
    bollinger = technical_data.get('indicators', {}).get('bollinger_bands', {})
    upper_band = bollinger.get('upper', current_price * 1.1)  # Default: +10%
    lower_band = bollinger.get('lower', current_price * 0.9)  # Default: -10%
    middle_band = bollinger.get('middle', current_price)
    
    # Extract Moving Averages for additional support/resistance
    ma_data = technical_data.get('indicators', {}).get('moving_averages', {}).get('values', {})
    ma50 = ma_data.get('ma50', current_price)
    ma200 = ma_data.get('ma200', current_price)
    
    # Identify nearest resistance (above current price)
    resistances = [r for r in [upper_band, ma50, ma200] if r > current_price]
    nearest_resistance = min(resistances) if resistances else current_price * 1.1
    
    # Identify nearest support (below current price)
    supports = [s for s in [lower_band, ma50, ma200] if s < current_price]
    nearest_support = max(supports) if supports else current_price * 0.9
    
    # Get AI predicted change if available
    ai_predicted_pct = 0
    if ai_prediction:
        ai_predicted_pct = ai_prediction.get('predicted_change_pct', 0)
    
    ai_target = current_price * (1 + ai_predicted_pct / 100)
    
    # Calculate Target Price: Conservative of AI upside and resistance
    if ai_predicted_pct > 0:
        target_price = min(ai_target, nearest_resistance)
    else:
        # If AI predicts negative or neutral, use middle band as conservative target
        target_price = middle_band if middle_band > current_price else nearest_resistance
    
    # Calculate Stop-loss: More conservative of -7% or below support
    stop_by_percent = current_price * (1 - default_stop_loss_pct)
    stop_by_support = nearest_support * 0.98  # 2% buffer below support
    stop_loss = max(stop_by_percent, stop_by_support)  # Higher = more conservative
    
    # Calculate Risk/Reward Ratio
    upside = target_price - current_price
    downside = current_price - stop_loss
    
    if downside > 0:
        risk_reward_ratio = round(upside / downside, 2)
    else:
        risk_reward_ratio = 0
    
    # Generate recommendation based on risk/reward
    if risk_reward_ratio >= 3:
        entry_rating = "EXCELLENT"
    elif risk_reward_ratio >= 2:
        entry_rating = "GOOD"
    elif risk_reward_ratio >= 1:
        entry_rating = "FAIR"
    else:
        entry_rating = "POOR"
    
    # Calculate percentages
    target_pct = round((target_price / current_price - 1) * 100, 2)
    stop_pct = round((stop_loss / current_price - 1) * 100, 2)
    
    return {
        "current_price": round(current_price, 2),
        "target_price": round(target_price, 2),
        "target_percent": target_pct,
        "stop_loss": round(stop_loss, 2),
        "stop_loss_percent": stop_pct,
        "risk_reward_ratio": risk_reward_ratio,
        "entry_rating": entry_rating,
        "analysis": {
            "nearest_resistance": round(nearest_resistance, 2),
            "nearest_support": round(nearest_support, 2),
            "ai_predicted_change_pct": ai_predicted_pct,
            "bollinger_position": bollinger.get('position', 'N/A')
        },
        "reasoning": _generate_reasoning(
            current_price, target_price, stop_loss, 
            risk_reward_ratio, entry_rating, ai_predicted_pct
        )
    }


def _generate_reasoning(
    current_price: float, 
    target_price: float, 
    stop_loss: float,
    risk_reward: float,
    entry_rating: str,
    ai_predicted_pct: float
) -> str:
    """리스크 수준에 대한 사람 친화적인 설명 문장을 생성합니다."""
    
    target_pct = round((target_price / current_price - 1) * 100, 1)
    stop_pct = round((stop_loss / current_price - 1) * 100, 1)
    
    reasoning = f"목표 수익률 +{target_pct}%, 예상 최대 손실률 {stop_pct}%, 손익비는 {risk_reward}:1 수준입니다. "
    
    if ai_predicted_pct > 5:
        reasoning += f"AI 예측 기준으로는 약 +{ai_predicted_pct:.1f}% 수준의 상승 여력이 있습니다. "
    elif ai_predicted_pct < -5:
        reasoning += f"AI 예측 기준으로는 약 {ai_predicted_pct:.1f}% 수준의 하락 가능성이 있습니다. "
    
    if entry_rating == "EXCELLENT":
        reasoning += "진입 구간이 매우 매력적인 수준으로 평가됩니다."
    elif entry_rating == "GOOD":
        reasoning += "진입 구간이 전반적으로 우호적인 수준입니다."
    elif entry_rating == "FAIR":
        reasoning += "진입 구간이 무난한(보통 수준의) 매력도를 보입니다."
    else:
        reasoning += "진입 매력도가 낮은 구간으로, 더 나은 가격대를 기다리는 것이 바람직할 수 있습니다."
    
    return reasoning


def format_risk_output(risk_data: Dict[str, Any], currency: str = "KRW") -> str:
    """리스크 분석 결과를 사용자에게 보여줄 수 있는 한국어 텍스트로 포맷팅합니다."""
    
    if "error" in risk_data:
        return f"리스크 계산 중 오류가 발생했습니다: {risk_data['error']}"
    
    if currency == "KRW":
        price_fmt = "{:,.0f}"
    else:
        price_fmt = "{:,.2f}"
    
    return f"""
📊 **리스크 관리 분석 결과**
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 목표가(Target Price): {price_fmt.format(risk_data['target_price'])} ({risk_data['target_percent']:+.1f}%)
🛑 손절가(Stop-loss): {price_fmt.format(risk_data['stop_loss'])} ({risk_data['stop_loss_percent']:.1f}%)
⚖️ 손익비(Risk/Reward): {risk_data['risk_reward_ratio']}:1
📈 진입 매력도(Entry Rating): {risk_data['entry_rating']}

💡 {risk_data['reasoning']}
"""


if __name__ == "__main__":
    # Test with sample data
    test_technical = {
        "indicators": {
            "bollinger_bands": {
                "upper": 58000,
                "middle": 55000,
                "lower": 52000,
                "position": 0.45
            },
            "moving_averages": {
                "values": {
                    "ma50": 54000,
                    "ma200": 52000
                }
            }
        }
    }
    
    test_ai = {"predicted_change_pct": 5.5}
    
    result = calculate_risk_levels(55000, test_technical, test_ai)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(format_risk_output(result))
