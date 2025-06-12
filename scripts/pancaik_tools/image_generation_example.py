import asyncio

from dotenv import load_dotenv

from pancaik.utils import generate_image

# Load environment variables from .env file
load_dotenv()


async def main():
    """
    Examples demonstrating image generation capabilities
    """
    # Example 1: Basic image generation with DALL-E
    image_url = await generate_image(prompt="A beautiful mountain landscape at sunset")
    print(f"Image URL: {image_url}")


if __name__ == "__main__":
    asyncio.run(main())
