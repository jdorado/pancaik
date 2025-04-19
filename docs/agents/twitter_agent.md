# TwitterAgent

The TwitterAgent allows you to monitor Twitter accounts, index tweets, and interact with the Twitter platform programmatically.

## Tasks

### index_followed_users

This task indexes tweets from the users specified in the `followed_users` configuration.

```yaml
tasks:
  index_followed_users:
    scheduler:
      type: "cron"
      params:
        expression: "*/5 * * * *"  # Runs every 5 minutes
    pipeline:
      - index_tweets
```

### index_own_mentions

This task indexes mentions of the agent's Twitter account, allowing you to monitor and respond to tweets that mention your account.

```yaml
tasks:
  index_own_mentions:
    scheduler:
      type: "cron"
      params:
        expression: "*/5 * * * *"  # Runs every 5 minutes
    pipeline:
      - index_mentions
```

### reply_own_mentions

This task automatically replies to mentions of the agent's Twitter account.

```yaml
tasks:
  reply_own_mentions:
    scheduler:
      type: "cron"
      params:
        expression: "*/5 * * * *"  # Runs every 5 minutes
    pipeline:
      - select_mention_to_reply
      - compose_tweet_from_context
      - publish_tweet
      - mark_mention_as_reviewed
      - index_tweet_by_id
```

### post_from_followed_users

This task creates posts based on content from followed users.

```yaml
tasks:
  post_from_followed_users:
    scheduler:
      type: "random_interval"
      params:
        min_minutes: 120
        max_minutes: 360
    pipeline:
      - select_topics_from_followed_users
      - compose_tweet_from_context
      - publish_tweet
      - index_tweet_by_id
```

### post_from_daily_research

This task generates and posts content based on daily research of followed topics.

```yaml
tasks:
  post_from_daily_research:
    scheduler:
      type: "random_interval"
      params:
        min_minutes: 120
        max_minutes: 360
    pipeline:
      - get_daily_content_from_followed_users
      - generate_daily_research
      - generate_daily_topics_from_research
      - select_topics_from_daily_research
      - research_topic
      - compose_tweet_from_context
      - publish_tweet
      - index_tweet_by_id
      - mark_topic_as_posted
```

### comment_on_followed_users

This task automatically comments on posts from followed users.

```yaml
tasks:
  comment_on_followed_users:
    scheduler:
      type: "random_interval"
      params:
        min_minutes: 30
        max_minutes: 60
    pipeline:
      - select_post_from_followed_user_to_comment
      - compose_tweet_from_context
      - publish_tweet
      - index_tweet_by_id
      - mark_post_as_commented
```

### reply_to_search_results

This task searches for relevant tweets and replies to them based on daily research.

```yaml
tasks:
  reply_to_search_results:
    scheduler:
      type: "random_interval"
      params:
        min_minutes: 15
        max_minutes: 30
    pipeline:
      - get_daily_content_from_followed_users
      - generate_daily_research
      - generate_daily_search_queries_from_research
      - search_posts_to_reply
      - compose_tweet_from_context
      - publish_tweet
      - index_tweet_by_id
```

The scheduler can be configured with different types:

- `cron`: Uses cron expressions for scheduling
- `interval`: Runs at fixed intervals (in seconds)
- `once`: Runs once at startup
- `random_interval`: Runs at random intervals between specified minutes

## Configuration

TwitterAgent is configured using a YAML file. You can place this in your project directory or specify a path when initializing the agent.

### Basic Configuration Structure

```yaml
name: "Twitter Agent"
twitter:
  credentials:
    username: ""
    user_id: ""
    password: ""
    email: ""
    consumer_key: ""
    consumer_secret: ""
    access_token: ""
    access_token_secret: ""
    bearer_token: ""
  followed_users:
    username1:
      index_minutes: 10  # Override default frequency for this user
    username2:  # Use default frequency
  default_index_user_frequency: 60  # Default frequency in minutes
tasks:
  index_followed_users:
    scheduler:
      type: "cron"
      params:
        expression: "*/5 * * * *"  # Runs every 5 minutes
    pipeline:
      - index_tweets
```

### Twitter Credentials

The `twitter.credentials` section requires valid Twitter API credentials:

| Field | Description |
|-------|-------------|
| `username` | Your Twitter username |
| `user_id` | Your Twitter user ID |
| `password` | Your Twitter password |
| `email` | Email associated with your Twitter account |
| `consumer_key` | API consumer key |
| `consumer_secret` | API consumer secret |
| `access_token` | OAuth access token |
| `access_token_secret` | OAuth access token secret |
| `bearer_token` | Bearer token for API access |

### Followed Users Configuration

The `twitter.followed_users` section defines which Twitter accounts to monitor:

```yaml
followed_users:
  elonmusk:  # Twitter handle without the @ symbol
    index_minutes: 10  # Custom indexing frequency for this user
  satyanadella:  # Uses the default frequency
```

- Each user can have an optional `index_minutes` setting to override the default frequency
- Without an `index_minutes` value, the user will be indexed according to the global `default_index_user_frequency` setting

### Global Twitter Settings

In the `twitter` section, you can set the following global parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `default_index_user_frequency` | Default frequency (in minutes) for indexing user tweets | 60 |

## Advanced Global Settings

Additional Twitter-related settings can be configured when initializing the Pancaik system:

```python
import pancaik

app = await pancaik.init({
    "db_connection": "mongodb://localhost:27017",
    "twitter_concurrency": 5,  # Maximum concurrent Twitter operations
    "twitter_max_concurrent_indexing_users": 30  # Max users to process in one batch
})
```

| Setting | Description | Default |
|---------|-------------|---------|
| `twitter_concurrency` | Maximum number of concurrent Twitter API calls | 5 |
| `twitter_max_concurrent_indexing_users` | Maximum number of users to index in a single batch | 30 |

## Example Configuration

```yaml
name: "Twitter Agent"
twitter:
  credentials:
    username: "my_twitter_username"
    user_id: "12345678"
    password: "my_password"
    email: "email@example.com"
    consumer_key: "abcdefghijklmnopqrstuvwxyz"
    consumer_secret: "123456789abcdefghijklmnopqrstuvwxyz"
    access_token: "123456789-abcdefghijklmnopqrstuvwxyz"
    access_token_secret: "abcdefghijklmnopqrstuvwxyz123456789"
    bearer_token: "AAAAAAAAAAAAAAAAAAAAAA%3DBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
  followed_users:
    elonmusk:
      index_minutes: 10
    satyanadella:
    OpenAI:
  default_index_user_frequency: 60
tasks:
  index_followed_users:
    scheduler:
      type: "cron"
      params:
        expression: "*/5 * * * *"
    pipeline:
      - index_tweets
``` 