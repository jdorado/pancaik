# LangGraph Integration

Pancaik Agents provides seamless integration with [LangGraph](https://github.com/langchain-ai/langgraph), a library for building stateful, multi-actor applications with LLMs. This integration allows you to create complex, multi-step workflows with conditional logic while keeping the simplicity and power of Pancaik Agents.

## Example Overview

The LangGraph integration example demonstrates a tweet generation agent with a three-step workflow:

1. **Generate**: Create a tweet about a random topic
2. **Review**: Evaluate the tweet for quality and appropriateness
3. **Publish**: Publish the approved tweet or loop back for revision

The power of LangGraph lies in its ability to define complex workflows with conditional logic—in this case, the decision to either publish a tweet or revise it based on quality review.

## Implementation

```python
from typing import Annotated, List, Dict, Any
import random

# Pancaik imports
from pancaik.core.agent import Agent

# LangChain imports
from langchain_openai import ChatOpenAI

# LangGraph imports
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

# Define the state structure for our LangGraph
class State(TypedDict):
    """State maintained throughout the LangGraph workflow"""
    messages: Annotated[list, add_messages]  # Conversation history
    tweets: List[str]  # List of generated tweets

class TweetAgent(Agent):
    """An agent specialized in generating and publishing tweets using LangGraph"""
    name = "tweet_agent"
    
    # Default topics for tweets
    TOPICS = ["AI", "Coding", "Tech", "Data", "Python", "Open source"]
    
    def __init__(self, api_key=None, id=None, yaml_path=None, topics=None):
        super().__init__(yaml_path=yaml_path, id=id)
        self.llm = ChatOpenAI(api_key=api_key)
        self.topics = topics or self.TOPICS
        # Build graph during initialization
        self.graph = self._create_workflow()
    
    def _create_workflow(self):
        """Create the tweet generation workflow as a LangGraph"""
        workflow = StateGraph(State)
        
        # Add nodes for each step in our workflow
        workflow.add_node("generate", self._generate_tweet)
        workflow.add_node("review", self._review_tweet)
        workflow.add_node("publish", self._publish_tweet)
        
        # Connect workflow nodes with conditional logic
        workflow.set_entry_point("generate")
        workflow.add_edge("generate", "review")
        
        # Add conditional logic - if review says "REVISE", go back to generate
        workflow.add_conditional_edges(
            "review",
            lambda state: "DECISION: REVISE" in self._get_last_message_content(state),
            {True: "generate", False: "publish"}
        )
        
        workflow.set_finish_point("publish")
        
        return workflow.compile()
```

### Workflow Methods

Each step in the workflow is implemented as a method that processes the state and returns an updated state:

```python
def _generate_tweet(self, state: State) -> Dict:
    """Generate a tweet about a random topic"""
    # Select random topic
    topic = random.choice(self.topics)
    
    # Initial prompt or use existing messages for revision
    if not state.get("messages") or len(state["messages"]) == 0:
        # First time generating a tweet
        prompt = f"Write a short, engaging tweet (max 280 chars) about {topic}. Include a hashtag."
        messages = [{"role": "user", "content": prompt}]
    else:
        # Revision based on previous feedback
        messages = state["messages"]
    
    # Generate the tweet using LLM
    response = self.llm.invoke(messages)
    tweet_text = response.content.strip()
    
    # Twitter character limit enforcement
    if len(tweet_text) > 280:
        tweet_text = tweet_text[:277] + "..."
        
    # Ensure tweets list exists
    existing_tweets = state.get("tweets", [])
    
    return {
        "messages": messages + [response],
        "tweets": existing_tweets + [tweet_text]
    }

def _review_tweet(self, state: State) -> Dict:
    """Review the generated tweet for quality and appropriateness"""
    # Get the current tweet for review
    current_tweet = state["tweets"][-1]
    
    # Review criteria prompt
    review_prompt = f"""Review this tweet: "{current_tweet}"
    Is it engaging and appropriate?
    End with DECISION: REVISE or DECISION: PUBLISH"""
    
    review_response = self.llm.invoke([{"role": "user", "content": review_prompt}])
    
    # Update state with review feedback
    return {
        "messages": state["messages"] + [review_response],
        "tweets": state["tweets"]
    }

def _publish_tweet(self, state: State) -> Dict:
    """Publish the approved tweet"""
    final_tweet = state["tweets"][-1]
    print(f"\nTWEET PUBLISHED: {final_tweet}\n")
    
    # Return final state
    return {"messages": [], "tweets": state["tweets"]}

async def run_tweet_cycle(self):
    """Run a complete tweet generation cycle"""
    result = self.graph.invoke({"messages": [], "tweets": []})
    return {
        "tweet": result["tweets"][0] if result.get("tweets") and result["tweets"] else None
    }
```

## Configuration

The agent can be configured with a simple YAML file:

```yaml
name: tweet_agent
description: "Tweet generation agent using LangGraph"
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
from langgraph_agent import TweetAgent
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

This example shows several powerful features of integrating LangGraph with Pancaik Agents:

1. **Stateful Workflows**: Maintain state across multiple steps of a workflow
2. **Conditional Logic**: Create branching logic based on LLM decisions
3. **Feedback Loops**: Implement revision cycles for content refinement
4. **Workflow Definition**: Define complex workflows with clear separation of concerns
5. **Integration Simplicity**: Seamlessly integrate LangGraph while maintaining the Pancaik Agent interface

## Dependencies

To run this example, you'll need to install the following packages:

```
langchain
langgraph
langchain-openai
```

This integration demonstrates how Pancaik Agents can leverage the powerful workflow capabilities of LangGraph while maintaining its clean, simple interface—giving you the best of both worlds. 