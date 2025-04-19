# Examples

Pancaik Agents provides a flexible framework for building various types of agents. This section showcases example agents for different use cases and demonstrates how Pancaik integrates with popular frameworks.

## Use Case Examples

Here are some examples of how Pancaik Agents can be used in various scenarios:

### Social Media Management Agent

This agent automatically generates and posts content to social media platforms.

```yaml
agent:
  name: social_media_bot
  description: "Posts daily content to Twitter and other platforms"
  tasks:
    - name: daily_tweet
      schedule: "0 10 * * *"  # Every day at 10 AM
      handler: social.post_to_twitter
      parameters:
        content_generator: "daily_thoughts"
        hashtags: ["ai", "automation"]
        
    - name: weekly_summary
      schedule: "0 18 * * 5"  # Every Friday at 6 PM
      handler: social.weekly_engagement_summary
      parameters:
        platforms: ["twitter", "linkedin"]
```

### Customer Support Chatbot

A chat-based agent that can answer customer inquiries and create tickets for complex issues.

```yaml
agent:
  name: support_assistant
  description: "Customer support chatbot with knowledge base"
  chat:
    enabled: true
    greeting: "Hello! I'm your support assistant. How can I help you today?"
    knowledge_base: "support_docs"
    fallback_action: "create_ticket"
  tasks:
    - name: sync_knowledge
      schedule: "0 */3 * * *"  # Every 3 hours
      handler: support.update_knowledge_base
```

### Quotation System

An agent that can receive inquiries, process them, and generate quotations.

```yaml
agent:
  name: quotation_system
  description: "Processes quotation requests and generates quotes"
  chat:
    enabled: true
    forms:
      - name: quote_request
        fields:
          - name: product_type
            type: select
            options: ["Software", "Hardware", "Services"]
          - name: quantity
            type: number
          - name: delivery_date
            type: date
  tasks:
    - name: process_quotes
      schedule: "*/30 * * * *"  # Every 30 minutes
      handler: quotes.process_pending
    - name: send_followups
      schedule: "0 9 * * *"  # Every day at 9 AM
      handler: quotes.send_followup_emails
```

### Content Aggregator

An agent that regularly aggregates content from different sources and creates a digest.

```yaml
agent:
  name: news_digest
  description: "Creates a daily digest of news from multiple sources"
  tasks:
    - name: fetch_content
      schedule: "0 */4 * * *"  # Every 4 hours
      handler: content.fetch_from_sources
      parameters:
        sources: 
          - name: "tech_blog"
            url: "https://techblog.com/rss"
          - name: "industry_news"
            url: "https://industrynews.com/feed"
    
    - name: generate_digest
      schedule: "0 6 * * *"  # Every day at 6 AM
      handler: content.create_digest
      parameters:
        format: "html"
        distribution: ["email", "website"]
```

## Framework Integrations

Pancaik Agents provides seamless integration with popular AI orchestration frameworks, allowing you to leverage their capabilities while maintaining the simplicity and power of the Pancaik ecosystem.

### [Basic Agent](examples/basic_agent.md)

Our [Basic Greeter Agent](examples/basic_agent.md) demonstrates the core functionality of Pancaik Agents, showing how to:

- Create a simple agent with multiple methods
- Configure task pipelines and schedules
- Return structured data between method calls
- Combine tasks into more complex workflows

[Read more about the Basic Agent example →](examples/basic_agent.md)

### [LangGraph Integration](examples/langgraph_integration.md)

The [LangGraph integration](examples/langgraph_integration.md) demonstrates how to create complex workflows with conditional logic and stateful execution:

- Define multi-step workflows with branching
- Maintain state across multiple processing steps
- Implement feedback loops for content refinement
- Create complex decision trees with LLM-based decisions

[Read more about the LangGraph integration →](examples/langgraph_integration.md)

### [CrewAI Integration](examples/crewai_integration.md)

The [CrewAI integration](examples/crewai_integration.md) showcases how to create specialized agent teams with different roles:

- Create role-based agents with specific goals and backstories
- Design tasks with clear descriptions and expected outputs
- Enable agent collaboration and context sharing
- Orchestrate multi-agent workflows with sequential execution

[Read more about the CrewAI integration →](examples/crewai_integration.md)

---

Each of these examples demonstrates how Pancaik Agents can be adapted to different use cases and integrated with different frameworks while maintaining a consistent, simple interface. All examples are available in the repository under the `examples` directory. 