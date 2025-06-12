"""
Example of integrating LangGraph with Pancaik: Tweet Generator Agent

This example demonstrates how to create a Pancaik agent that uses LangGraph
to create a multi-step workflow for generating, reviewing and publishing tweets.
"""

import random
from typing import Annotated, Dict, List

# LangChain imports
from langchain_openai import ChatOpenAI

# LangGraph imports
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

# Pancaik imports
from pancaik.core.agent import Agent


# Define the state structure for our LangGraph
class State(TypedDict):
    """State maintained throughout the LangGraph workflow"""

    messages: Annotated[list, add_messages]  # Conversation history
    tweets: List[str]  # List of generated tweets


class TweetAgent(Agent):
    """An agent specialized in generating and publishing tweets using LangGraph

    This agent demonstrates a 3-step workflow:
    1. Generate a tweet about a random topic
    2. Review the tweet for quality
    3. Publish the approved tweet
    """

    name = "tweet_agent"

    # Default topics for tweets
    TOPICS = ["AI", "Coding", "Tech", "Data", "Python", "Open source"]

    def __init__(self, api_key=None, id=None, yaml_path=None, topics=None):
        """Initialize the Tweet Agent

        Args:
            api_key: OpenAI API key
            id: Agent ID
            yaml_path: Path to YAML configuration
            topics: Optional list of topics to override defaults
        """
        super().__init__(yaml_path=yaml_path, id=id)
        self.llm = ChatOpenAI(api_key=api_key)
        self.topics = topics or self.TOPICS
        # Build graph during initialization
        self.graph = self._create_workflow()

    def _create_workflow(self):
        """Create the tweet generation workflow as a LangGraph

        Workflow steps:
        - generate → review → publish
        - If review decides revision needed: review → generate (loop back)
        """
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
            "review", lambda state: "DECISION: REVISE" in self._get_last_message_content(state), {True: "generate", False: "publish"}
        )

        workflow.set_finish_point("publish")

        return workflow.compile()

    def _get_last_message_content(self, state: State) -> str:
        """Helper to safely extract content from the last message

        Args:
            state: Current workflow state

        Returns:
            The content of the last message, or empty string if none
        """
        if not state["messages"]:
            return ""

        last_message = state["messages"][-1]

        # Handle different message object structures
        if hasattr(last_message, "content"):
            return last_message.content
        return last_message.get("content", "")

    def _generate_tweet(self, state: State) -> Dict:
        """Generate a tweet about a random topic

        Args:
            state: Current workflow state

        Returns:
            Updated state with new tweet and messages
        """
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

        return {"messages": messages + [response], "tweets": existing_tweets + [tweet_text]}

    def _review_tweet(self, state: State) -> Dict:
        """Review the generated tweet for quality and appropriateness

        Args:
            state: Current workflow state

        Returns:
            Updated state with review decision
        """
        # Safety check - ensure we have a tweet to review
        if not state.get("tweets") or len(state["tweets"]) == 0:
            return {"messages": [{"role": "user", "content": "No tweet found. Please generate a new tweet."}], "tweets": []}

        current_tweet = state["tweets"][-1]

        # Review criteria prompt
        review_prompt = f"""Review this tweet: "{current_tweet}"
        Is it engaging and appropriate?
        End with DECISION: REVISE or DECISION: PUBLISH"""

        review_response = self.llm.invoke([{"role": "user", "content": review_prompt}])

        # Handle revision decision
        if "DECISION: REVISE" in review_response.content:
            revision_request = f"Revise this tweet based on feedback: {review_response.content}"
            return {"messages": [{"role": "user", "content": revision_request}], "tweets": state["tweets"][:-1]}  # Remove draft tweet

        # Continue to publish
        return {"messages": state["messages"] + [review_response], "tweets": state["tweets"]}

    def _publish_tweet(self, state: State) -> Dict:
        """Publish the approved tweet

        Args:
            state: Current workflow state

        Returns:
            Final state with published tweet
        """
        # Safety check - ensure we have a tweet to publish
        if not state.get("tweets") or len(state["tweets"]) == 0:
            print("\nNo tweet to publish\n")
            return {"messages": [], "tweets": []}

        final_tweet = state["tweets"][-1]
        print(f"\nTWEET PUBLISHED: {final_tweet}\n")

        # Return final state
        return {"messages": [], "tweets": state["tweets"]}

    async def run_tweet_cycle(self):
        """Run a complete tweet generation cycle

        Returns:
            Dict containing the published tweet
        """
        result = self.graph.invoke({"messages": [], "tweets": []})
        return {"tweet": result["tweets"][0] if result.get("tweets") and result["tweets"] else None}
