# Twitter Service

A comprehensive service for interacting with Twitter/X through both official API and non-API methods. This service provides dual-strategy access to ensure reliable operation and handle API rate limits gracefully.

## Features

- Tweet operations: create, reply, quote, thread creation
- Media handling: image upload and attachment
- Timeline and tweet fetching with fallback strategies
- Search functionality across both API methods
- Profile and tweet metadata retrieval
- Robust error handling and logging
- Async-first design for optimal performance
- Non-API access as a fallback strategy

## Configuration

The Twitter service requires credentials for authentication. You can provide these in a dictionary format:

```python
twitter_config = {
    # Official API credentials
    "consumer_key": "YOUR_CONSUMER_KEY",
    "consumer_secret": "YOUR_CONSUMER_SECRET",
    "access_token": "YOUR_ACCESS_TOKEN",
    "access_token_secret": "YOUR_ACCESS_TOKEN_SECRET",
    "bearer_token": "YOUR_BEARER_TOKEN",
    
    # Non-API credentials (fallback method)
    "username": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"  # Optional but recommended for fallback
}
```

## Core Components

The Twitter service is structured into several components:

- **API**: Official Twitter API interactions
- **Client**: HTTP client and request handling
- **Models**: Data models and type definitions
- **Handlers**: Database operations and data persistence
- **Tools**: Agent-ready functions for AI tools

## Core Functions

### Creating Tweets

```python
await create_tweet(
    twitter: Dict,
    text: str,
    images: Union[str, List[str]] = None,
    reply_id: Optional[int] = None,
    quote_id: Optional[int] = None,
) -> Optional[Dict]
```

Create a tweet with optional media, as a reply, or as a quote tweet.

#### Parameters:
- `twitter`: Dictionary containing credentials
- `text`: Tweet content text
- `images`: Optional URL or list of URLs to images to attach
- `reply_id`: Optional tweet ID to reply to
- `quote_id`: Optional tweet ID to quote

#### Returns:
- Dictionary containing tweet data or None if unsuccessful

### Creating Tweet Threads

```python
async def create_thread(
    twitter: Dict, 
    texts: List[str], 
    image_urls: Union[str, List[str]] = None
) -> Optional[int]
```

Create a thread of tweets with optional media attachment to the first tweet.

#### Parameters:
- `twitter`: Dictionary containing credentials
- `texts`: List of text content for each tweet in the thread
- `image_urls`: Optional URL or list of URLs to images to attach to the first tweet

#### Returns:
- ID of the first tweet in the thread or None if unsuccessful

### Fetching Tweets

```python
async def get_latest_tweets(
    twitter: Dict, 
    username: str, 
    user_id: str, 
    max_results: int = 10
) -> Optional[List[Dict]]
```

Fetch the latest tweets for a user, trying non-API methods first.

#### Parameters:
- `twitter`: Dictionary containing credentials
- `username`: Twitter username
- `user_id`: Twitter user ID
- `max_results`: Maximum number of tweets to retrieve (default 10)

#### Returns:
- List of formatted tweet dictionaries or None if unsuccessful

### Searching Tweets

```python
async def search(
    query: str, 
    twitter: Dict
) -> Optional[List[Dict]]
```

Search tweets based on a query, trying non-API methods as a fallback.

#### Parameters:
- `query`: Search query string
- `twitter`: Dictionary containing credentials

#### Returns:
- List of formatted tweet dictionaries or None if unsuccessful

### Getting a Single Tweet

```python
async def get_tweet(
    tweet_id: str, 
    twitter: Dict
) -> Optional[Dict]
```

Retrieve a single tweet by its ID, trying non-API methods as a fallback.

#### Parameters:
- `tweet_id`: ID of the tweet to retrieve
- `twitter`: Dictionary containing credentials

#### Returns:
- Formatted tweet dictionary or None if unsuccessful

### Indexing User Tweets

```python
async def index_user_tweets(
    twitter_handle: str,

    data_store: Dict[str, Any], 
    twitter_user_id: str = None, 
    max_tweets: int = 100
) -> Dict
```

Index a user's tweets into the data store for later use.

## Non-API Access (X-Non-API)

⚠️ **IMPORTANT USAGE ADVISORY**

The non-API access component is intended for **testing, development, and fallback purposes only**. For primary production deployments:
- Use the official Twitter/X API through their developer platform
- Obtain proper API credentials and comply with rate limits
- Follow Twitter's Developer Terms of Service

### Legal Disclaimer

1. **Terms of Service Compliance**: Users are solely responsible for ensuring their usage complies with Twitter/X's Terms of Service and Developer Agreement.
2. **No Warranty**: This service is provided "AS IS" without any warranty of any kind.
3. **Production Usage**: For production applications, users SHOULD use Twitter's official API services primarily. The non-API access is a fallback mechanism.
4. **Risk Assumption**: By using this service, you assume all risks associated with its use, including the risk of account suspension, service interruption, or other consequences.

### How Non-API Access Works

The non-API access component works by:
1. Authenticating with Twitter/X using user credentials
2. Managing cookies to maintain session state
3. Making direct HTTP requests to Twitter's web endpoints
4. Parsing responses to extract relevant data

### Setup for Non-API Access

To enable non-API access as a fallback, provide both sets of credentials:

```python
twitter = {
    # Primary API credentials
    "consumer_key": "YOUR_CONSUMER_KEY",
    "consumer_secret": "YOUR_CONSUMER_SECRET",
    "access_token": "YOUR_ACCESS_TOKEN",
    "access_token_secret": "YOUR_ACCESS_TOKEN_SECRET",
    
    # Fallback non-API credentials
    "username": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
}
```

### Troubleshooting Non-API Access

#### Authentication Issues

If you experience authentication issues with the non-API access:

1. **Reset Cookies**: The service automatically persists cookies, but they may need to be refreshed
2. **Check Credentials**: Verify username and password are correct
3. **IP Restrictions**: Twitter may limit access based on IP address or unusual activity
4. **Rate Limiting**: Implement exponential backoff for retries

#### Platform-Specific Issues

For Mac users:
```bash
# If experiencing network issues
brew services restart mongodb-community  # If using MongoDB for cookie storage
```

## Media Handling

The Twitter service provides functions for downloading images and uploading media:

```python
async def download_image(url: str) -> Optional[bytes]
async def upload_media(twitter: Dict[str, str], data: bytes, filename: str = "image.jpg") -> Optional[int]
async def process_images(twitter: Dict, urls: Union[str, List[str]]) -> List[int]
```

## Error Handling

The service implements robust error handling with detailed logging. All errors are logged with appropriate severity levels, and API rate limiting is gracefully handled with fallback strategies.

## Best Practices

1. **Provide both API and non-API credentials** for maximum reliability
2. **Handle rate limiting**: The service attempts to handle rate limiting automatically but applications should implement appropriate retry logic
3. **Monitor logs**: The service provides detailed logging that can help identify issues
4. **Use async patterns**: All methods are async and should be awaited properly
5. **Respect Twitter's Terms of Service**: Use the non-API access responsibly and only as a fallback

## Example Usage

```python
from pancaik.services.twitter import create_tweet, get_latest_tweets

# Configuration with both API and fallback credentials
twitter_config = {
    "consumer_key": "YOUR_CONSUMER_KEY",
    "consumer_secret": "YOUR_CONSUMER_SECRET",
    "access_token": "YOUR_ACCESS_TOKEN",
    "access_token_secret": "YOUR_ACCESS_TOKEN_SECRET",
    "bearer_token": "YOUR_BEARER_TOKEN",
    "username": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
}

# Create a tweet
tweet = await create_tweet(
    twitter_config,
    "Hello world from Pancaik!",
    images=["https://example.com/image.jpg"]
)

# Get latest tweets
tweets = await get_latest_tweets(
    twitter_config,
    "elonmusk",
    "44196397"
)
```

## Implementation Notes

The service follows Design by Contract principles with appropriate precondition and postcondition checks. All operations include detailed logging to enable effective debugging and monitoring. The implementation is designed to gracefully fall back to non-API methods when official API methods fail or hit rate limits. 