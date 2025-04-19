# LangGraph Agent Example

This example demonstrates how to create an agent using Pancaik and LangGraph.

## Installation

### Option 1: For development with local Pancaik source

If you're developing with the local Pancaik source code:

```bash
# Install the example requirements (including the local pancaik package in development mode)
pip install -r requirements.txt
```

### Option 2: For users with the published package

If you're using the published Pancaik package:

```bash
# Edit requirements.txt to use the published package
# Change "-e ../.." to "pancaik" in requirements.txt
pip install -r requirements.txt
```

## Running the example

```bash
# Make sure you have an OpenAI API key in your .env file
python run_agent.py
```

## Example Description

This example creates a TweetAgent that:
1. Generates tweet ideas on random topics
2. Reviews them for quality
3. Publishes the approved tweets

The agent uses LangGraph for workflow management and OpenAI for the language model. 