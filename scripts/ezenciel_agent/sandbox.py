"""
To run this code you need to install the following dependencies:
pip install google-genai pillow
"""

import asyncio
import os

from google import genai
from google.genai import types

MODEL = "veo-2.0-generate-001"

client = genai.Client(
    http_options={"api_version": "v1beta"},
    api_key=os.environ.get("GEMINI_API_KEY"),
)

video_config = types.GenerateVideosConfig(
    person_generation="allow_all",  # supported values: "dont_allow" or "allow_adult" or "allow_all"
    aspect_ratio="16:9",  # supported values: "16:9" or "16:10"
    number_of_videos=1,  # supported values: 1 - 4
    duration_seconds=5,  # supported values: 5 - 8
)


async def generate():
    operation = client.models.generate_videos(
        model=MODEL,
        prompt="""baby in diapers""",
        config=video_config,
    )

    # Waiting for the video(s) to be generated
    while not operation.done:
        print("Video has not been generated yet. Check again in 10 seconds...")
        await asyncio.sleep(10)  # Non-blocking sleep
        operation = client.operations.get(operation)

    result = operation.result
    if not result:
        print("Error occurred while generating video.")
        return

    generated_videos = result.generated_videos
    if not generated_videos:
        print("No videos were generated.")
        return

    print(f"Generated {len(generated_videos)} video(s).")

    # Process videos concurrently
    download_tasks = []
    for n, generated_video in enumerate(generated_videos):
        print(f"Video has been generated: {generated_video.video.uri}")
        task = download_and_save_video(generated_video, n)
        download_tasks.append(task)

    # Wait for all downloads to complete
    await asyncio.gather(*download_tasks)


async def download_and_save_video(generated_video, n):
    """Download and save a single video asynchronously"""
    # Run the blocking operations in a thread pool
    loop = asyncio.get_event_loop()

    # Download the file
    await loop.run_in_executor(None, lambda: client.files.download(file=generated_video.video))

    # Save the video
    filename = f"video_{n}.mp4"
    await loop.run_in_executor(None, generated_video.video.save, filename)

    print(f"Video {generated_video.video.uri} has been downloaded to {filename}.")


async def main():
    await generate()


if __name__ == "__main__":
    asyncio.run(main())
