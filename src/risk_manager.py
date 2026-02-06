"""
Risk Manager - Calculate Target Price, Stop-loss, and Risk/Reward Ratio
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
    Calculate risk management levels based on technical analysis and AI prediction.
    
    Args:
        current_price: Current stock price
        technical_data: Technical analysis data (from technical_analysis tool)
        ai_prediction: AI prediction data (optional)
        default_stop_loss_pct: Default stop-loss percentage (0.07 = 7%)
        
    Returns:
        dict with target_price, stop_loss, risk_reward_ratio, and reasoning
    """
    if current_price <= 0:
        return {"error": "Invalid current price"}
    
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
    """Generate human-readable reasoning for risk levels."""
    
    target_pct = round((target_price / current_price - 1) * 100, 1)
    stop_pct = round((stop_loss / current_price - 1) * 100, 1)
    
    reasoning = f"Target +{target_pct}%, Stop-loss {stop_pct}%, Risk/Reward {risk_reward}:1. "
    
    if ai_predicted_pct > 5:
        reasoning += f"AI predicts strong upside of +{ai_predicted_pct:.1f}%. "
    elif ai_predicted_pct < -5:
        reasoning += f"AI predicts downside of {ai_predicted_pct:.1f}%. "
    
    if entry_rating == "EXCELLENT":
        reasoning += "Entry point is highly favorable."
    elif entry_rating == "GOOD":
        reasoning += "Entry point is favorable."
    elif entry_rating == "FAIR":
        reasoning += "Entry point is neutral."
    else:
        reasoning += "Entry point is not favorable. Consider waiting for better levels."
    
    return reasoning


def format_risk_output(risk_data: Dict[str, Any], currency: str = "KRW") -> str:
    """Format risk data for display."""
    
    if "error" in risk_data:
        return f"Risk calculation error: {risk_data['error']}"
    
    if currency == "KRW":
        price_fmt = "{:,.0f}"
    else:
        price_fmt = "{:,.2f}"
    
    return f"""
📊 **Risk Management Analysis**
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Target Price: {price_fmt.format(risk_data['target_price'])} ({risk_data['target_percent']:+.1f}%)
🛑 Stop-loss: {price_fmt.format(risk_data['stop_loss'])} ({risk_data['stop_loss_percent']:.1f}%)
⚖️ Risk/Reward: {risk_data['risk_reward_ratio']}:1
📈 Entry Rating: {risk_data['entry_rating']}

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
