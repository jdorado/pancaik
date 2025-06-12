import asyncio
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel

from pancaik.utils import compose_prompt, get_completion
from pancaik.utils.ai_router import Provider
from pancaik.utils.json_parser import extract_json_content

# Load environment variables from .env file
load_dotenv()


async def main():
    """Demonstrate AI router with structured output"""

    # OpenAI (default is o3-mini)
    openai_response = await get_completion("What is AI?", use_openrouter=False)
    print(f"OpenAI default ({Provider.OPENAI.name}): {openai_response[:50]}...\n")

    # OpenRouter
    openrouter_response = await get_completion("What is AI?")
    print(f"OpenRouter ({Provider.OPENROUTER.name}): {openrouter_response[:50]}...\n")

    # System prompt
    messages = compose_prompt("Explain quantum computing briefly.", system_content="Be concise and simple.")
    response = await get_completion(messages)
    print(f"System prompt: {response[:50]}...\n")

    # Pydantic model example
    math_messages = compose_prompt(
        "How can I solve 8x + 7 = -23?", system_content="You are a helpful math tutor. Guide the user through the solution step by step."
    )

    # Define a simple Pydantic model for structured output
    class Step(BaseModel):
        explanation: str
        output: str

    class MathReasoning(BaseModel):
        steps: List[Step]
        final_answer: str

    math_result = await get_completion(math_messages, model_id="o3-mini", use_openrouter=False, response_model=MathReasoning)

    # Check if the model refused to respond
    if hasattr(math_result, "refusal") and math_result.refusal:
        print(f"Model refused: {math_result.refusal}")
    else:
        print("Math problem solution:")
        for i, step in enumerate(math_result.steps, 1):
            print(f"  Step {i}: {step.explanation}")
            print(f"    {step.output}")
        print(f"  Final answer: {math_result.final_answer}")

    # Simple JSON extraction example
    json_response = await get_completion("List 3 fruits in JSON format")
    fruits = extract_json_content(json_response)
    print(f"\nExtracted fruits: {fruits}")


if __name__ == "__main__":
    asyncio.run(main())
