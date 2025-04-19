"""
Example of integrating CrewAI with Pancaik: Tweet Generator Agent

This example demonstrates how to create a Pancaik agent that uses CrewAI
to create a multi-step workflow for generating, reviewing and publishing tweets.
"""

import random

# CrewAI imports
from crewai import Agent as CrewAgent
from crewai import Crew, Task

# LangChain imports
from langchain_openai import ChatOpenAI

# Pancaik imports
from pancaik.core.agent import Agent


class TweetAgent(Agent):
    """An agent specialized in generating and publishing tweets using CrewAI

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
        self.api_key = api_key
        self.llm = ChatOpenAI(api_key=api_key)
        self.topics = topics or self.TOPICS
        self.crew = self._create_crew()

    def _create_crew(self):
        """Create the tweet generation workflow as a CrewAI Crew

        Workflow involves three agents:
        - Generator: Creates tweets
        - Reviewer: Reviews and provides feedback
        - Publisher: Makes final publishing decision
        """
        # Define CrewAI agents for each role
        generator = CrewAgent(
            role="Tweet Generator",
            goal="Create engaging, concise tweets on various topics",
            backstory="You are a social media expert who can create engaging tweets that resonate with audiences.",
            verbose=True,
            llm=self.llm,
        )

        reviewer = CrewAgent(
            role="Tweet Reviewer",
            goal="Ensure tweets are engaging, appropriate, and error-free",
            backstory="You have a keen eye for quality and can spot issues in content before publication.",
            verbose=True,
            llm=self.llm,
        )

        publisher = CrewAgent(
            role="Tweet Publisher",
            goal="Make final decisions on tweet publication",
            backstory="You understand what makes content go viral and make the final call on publishing.",
            verbose=True,
            llm=self.llm,
        )

        # Create tasks for the workflow
        topic = random.choice(self.topics)

        generate_task = Task(
            description=f"Write a short, engaging tweet (max 280 chars) about {topic}. Include a hashtag.",
            agent=generator,
            expected_output="A well-crafted tweet ready for review.",
        )

        review_task = Task(
            description="Review the tweet for quality, engagement potential, and appropriateness. Suggest revisions if needed.",
            agent=reviewer,
            expected_output="Feedback on the tweet with DECISION: REVISE or DECISION: PUBLISH",
            context=[generate_task],
        )

        publish_task = Task(
            description="Publish the approved tweet if it meets quality standards.",
            agent=publisher,
            expected_output="The final published tweet.",
            context=[review_task],
        )

        # Create and return the crew
        crew = Crew(agents=[generator, reviewer, publisher], tasks=[generate_task, review_task, publish_task], verbose=True)

        return crew

    async def run_tweet_cycle(self):
        """Run a complete tweet generation cycle

        Returns:
            Dict containing the published tweet
        """
        # Re-initialize crew with new random topic each time
        self.crew = self._create_crew()

        # Execute the crew workflow
        result = self.crew.kickoff()

        # Extract the tweet from the result
        # CrewOutput objects don't have strip() method, extract the string content
        tweet = str(result)

        # Twitter character limit enforcement
        if len(tweet) > 280:
            tweet = tweet[:277] + "..."

        print(f"\nTWEET PUBLISHED: {tweet}\n")

        return {"tweet": tweet}
