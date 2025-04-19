# CrewAI Integration

Pancaik Agents offers seamless integration with [CrewAI](https://github.com/crewai/crewai), a framework for orchestrating role-playing AI agents. This integration allows you to create specialized agent teams with different roles working together while maintaining the simplicity and power of Pancaik Agents.

## Example Overview

The CrewAI integration example demonstrates a tweet generation agent that orchestrates a team of specialized agents:

1. **Generator**: Creates engaging, concise tweets on various topics
2. **Reviewer**: Ensures tweets are appropriate, engaging, and error-free
3. **Publisher**: Makes final decisions on tweet publication

This example showcases how Pancaik Agents can leverage CrewAI's role-based agent design while maintaining a clean, consistent interface.

## Implementation

```python
from typing import Dict, List, Any
import random

# Pancaik imports
from pancaik.core.agent import Agent

# LangChain imports
from langchain_openai import ChatOpenAI

# CrewAI imports
from crewai import Crew, Task, Agent as CrewAgent

class TweetAgent(Agent):
    """An agent specialized in generating and publishing tweets using CrewAI"""
    name = "tweet_agent"
    
    # Default topics for tweets
    TOPICS = ["AI", "Coding", "Tech", "Data", "Python", "Open source"]
    
    def __init__(self, api_key=None, id=None, yaml_path=None, topics=None):
        """Initialize the Tweet Agent"""
        super().__init__(yaml_path=yaml_path, id=id)
        self.api_key = api_key
        self.llm = ChatOpenAI(api_key=api_key)
        self.topics = topics or self.TOPICS
        self.crew = self._create_crew()
```

### Creating the Crew

The core of the CrewAI integration is the creation of a crew with specialized agents and tasks:

```python
def _create_crew(self):
    """Create the tweet generation workflow as a CrewAI Crew"""
    # Define CrewAI agents for each role
    generator = CrewAgent(
        role="Tweet Generator",
        goal="Create engaging, concise tweets on various topics",
        backstory="You are a social media expert who can create engaging tweets that resonate with audiences.",
        verbose=True,
        llm=self.llm
    )
    
    reviewer = CrewAgent(
        role="Tweet Reviewer",
        goal="Ensure tweets are engaging, appropriate, and error-free",
        backstory="You have a keen eye for quality and can spot issues in content before publication.",
        verbose=True,
        llm=self.llm
    )
    
    publisher = CrewAgent(
        role="Tweet Publisher",
        goal="Make final decisions on tweet publication",
        backstory="You understand what makes content go viral and make the final call on publishing.",
        verbose=True,
        llm=self.llm
    )
    
    # Create tasks for the workflow
    topic = random.choice(self.TOPICS)
    
    generate_task = Task(
        description=f"Write a short, engaging tweet (max 280 chars) about {topic}. Include a hashtag.",
        agent=generator,
        expected_output="A well-crafted tweet ready for review."
    )
    
    review_task = Task(
        description="Review the tweet for quality, engagement potential, and appropriateness. Suggest revisions if needed.",
        agent=reviewer,
        expected_output="Feedback on the tweet with DECISION: REVISE or DECISION: PUBLISH",
        context=[generate_task]
    )
    
    publish_task = Task(
        description="Publish the approved tweet if it meets quality standards.",
        agent=publisher,
        expected_output="The final published tweet.",
        context=[review_task]
    )
    
    # Create and return the crew
    crew = Crew(
        agents=[generator, reviewer, publisher],
        tasks=[generate_task, review_task, publish_task],
        verbose=True
    )
    
    return crew
```

### Running the Workflow

```python
async def run_tweet_cycle(self):
    """Run a complete tweet generation cycle"""
    # Re-initialize crew with new random topic each time
    self.crew = self._create_crew()
    
    # Execute the crew workflow
    result = self.crew.kickoff()
    
    # Extract the tweet from the result
    tweet = str(result)
    
    # Twitter character limit enforcement
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."
        
    print(f"\nTWEET PUBLISHED: {tweet}\n")
        
    return {
        "tweet": tweet
    }
```

## Configuration

The agent can be configured with a simple YAML file:

```yaml
name: tweet_agent
description: "Tweet generation agent using CrewAI"
openai_api_key: ${OPENAI_API_KEY}

default_topics:
  - Technology
  - AI
  - Programming
  - Data Science
  - Cloud Computing
```

## Running the Agent

```python
from crewai_agent import TweetAgent
import os

async def main():
    # Initialize the agent
    api_key = os.environ.get("OPENAI_API_KEY")
    agent = TweetAgent(api_key=api_key, yaml_path="config.yaml")
    
    # Run the tweet generation workflow
    result = await agent.run_tweet_cycle()
    
    print(f"Published tweet: {result['tweet']}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## Key Features Demonstrated

This example shows several powerful features of integrating CrewAI with Pancaik Agents:

1. **Role-Based Agents**: Create specialized agents with specific goals and backstories
2. **Task Definition**: Define tasks with clear descriptions and expected outputs
3. **Agent Collaboration**: Allow agents to work together, building on each others' outputs
4. **Sequential Workflows**: Create logical sequences of tasks that pass context between steps
5. **Integration Simplicity**: Seamlessly integrate CrewAI while maintaining the Pancaik Agent interface

## Dependencies

To run this example, you'll need to install the following packages:

```
crewai
langchain-openai
```

## Why Use CrewAI Integration?

The CrewAI integration is particularly useful when:

1. You need multiple specialized agents to solve different aspects of a problem
2. Role-playing and agent personalities are important to your application
3. You want to create a team of agents with clear responsibilities
4. You need to orchestrate complex multi-agent workflows

This integration demonstrates how Pancaik Agents can leverage the role-based design of CrewAI while maintaining a clean, consistent interface—allowing you to create powerful multi-agent systems with minimal complexity. 