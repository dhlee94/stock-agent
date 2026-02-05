"""
Image Tool - Image generation and analysis
"""
import json


def process_image(action: str, prompt: str) -> str:
    """
    Generate or analyze images.
    Args:
        action: 'generate' to create an image, 'analyze' to describe an image.
        prompt: Description for generation OR image URL for analysis.
    """
    print(f"🖼️ [Image] Action: {action}, Prompt: {prompt}")
    if action == "generate":
        return json.dumps({
            "status": "success",
            "image_url": "https://storage.example.com/generated_image_123.png",
            "prompt": prompt
        })
    elif action == "analyze":
        return json.dumps({
            "status": "success",
            "description": f"This image shows: {prompt[:50]}... Analysis complete.",
            "objects_detected": ["person", "building", "sky"]
        })
    return "Invalid action. Use 'generate' or 'analyze'."
