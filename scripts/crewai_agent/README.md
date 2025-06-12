# CrewAI Tweet Generator Agent

This example demonstrates how to create a Pancaik agent that uses CrewAI to create a multi-step workflow for generating, reviewing, and publishing tweets.

## Overview

The CrewAI Tweet Generator agent demonstrates how to use CrewAI to create a collaborative workflow with multiple specialized agents working together. The workflow consists of three steps:

1. Generate a tweet about a random topic
2. Review the tweet for quality
3. Publish the approved tweet

## Setup

1. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set up your environment variables by creating a `.env` file:
   ```
   OPENAI_API_KEY=your_openai_api_key
   ```

## Usage

Run the agent with:

```
python run_agent.py
```

This will:
1. Create a new tweet using the CrewAI workflow
2. Register a scheduled task to create tweets at regular intervals
3. Start a web server to expose the agent's functionality

## Configuration

The agent's behavior can be configured through the `config.yaml` file, which defines:
- Task scheduling parameters
- Pipeline configuration

By default, the agent generates a new tweet every minute.

## How It Works

The CrewAI implementation uses three specialized agents:
- **Tweet Generator**: Creates engaging tweets on random topics
- **Tweet Reviewer**: Reviews tweets for quality and appropriateness
- **Tweet Publisher**: Makes the final decision on publishing

These agents collaborate through a series of tasks, passing information between them to achieve the final goal of creating high-quality tweets. 