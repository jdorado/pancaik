# X-Non-API Service

⚠️ **IMPORTANT USAGE ADVISORY**

This service is intended for **testing and development purposes only**. For production deployments:
- Use the official Twitter/X API through their developer platform
- Obtain proper API credentials and comply with rate limits
- Follow Twitter's Developer Terms of Service

Using this service in production may:
- Violate Twitter/X's Terms of Service
- Result in account suspension
- Have legal implications
- Be subject to unexpected changes in Twitter/X's systems

## Legal Disclaimer

1. **Terms of Service Compliance**: Users are solely responsible for ensuring their usage complies with Twitter/X's Terms of Service and Developer Agreement.

2. **No Warranty**: This service is provided "AS IS" without any warranty of any kind. The developers make no guarantees about its functionality, reliability, or continued availability.

3. **Production Usage**: For production applications, users MUST use Twitter's official API services. This service is NOT a replacement for official API access.

4. **Risk Assumption**: By using this service, you assume all risks associated with its use, including the risk of account suspension, service interruption, or other consequences.

5. **Liability**: The developers and contributors cannot be held liable for any damages or consequences arising from the use of this service.

The X-Non-API Service is a RESTful API wrapper for the Twitter/X platform that provides a straightforward interface for interacting with Twitter services without requiring official API access. It handles the complexity of Twitter's authentication by persisting cookies in MongoDB, enabling reliable session management across multiple containers.

## Features

- Login and profile information retrieval
- Timeline access (user and home)
- Tweet search and posting
- Interactive API documentation at `/docs` endpoint
- Cookie-based session management with MongoDB
- No Twitter API tokens required

## Setup Instructions

### Mac Users (Recommended)

For Mac users, running the service locally is recommended due to potential Docker networking issues:

```bash
# Clone the repository
git clone https://github.com/jdorado/x-api-service
cd x-api-service

# Install dependencies
npm install

# Install and start MongoDB (if not already installed)
brew install mongodb-community
brew services start mongodb-community

# Create a .env file
cat << EOF > .env
PORT=6011
MONGO_CONNECTION=mongodb://localhost:27017/x-api
EOF

# Start the service
npm start

# The API will be available at http://localhost:6011
```

### Docker Setup (Linux/Windows Recommended)

Prerequisites:
- Docker and Docker Compose installed

```bash
# Clone the repository
git clone https://github.com/jdorado/x-api-service
cd x-api-service

# Start the services (includes MongoDB)
docker-compose up -d

# The API will be available at http://localhost:6011
```

### Configure Pancaik

Add the X-API URL to your Pancaik initialization:

```python
app = await init({
    "run_continuous": True,
    "app_title": "My Twitter Agent",
    "x_api_url": "http://localhost:6011/api"  # Same URL for both local and Docker setups
})
```

## Usage in Agents

### Basic Tweet Posting

```python
from pancaik.utils.x_api import send_tweet

class TwitterAgent(Agent):
    async def post_tweet(self, text: str):
        credentials = {
            "username": "your_twitter_username",
            "password": "your_twitter_password"
        }
        return await send_tweet(text, credentials)
```

### Profile Information

```python
from pancaik.utils.x_api import get_profile

class TwitterAgent(Agent):
    async def get_user_info(self, username: str):
        credentials = {
            "username": "your_twitter_username",
            "password": "your_twitter_password"
        }
        return await get_profile(username, credentials)
```

### Search Tweets

```python
from pancaik.utils.x_api import search

class TwitterAgent(Agent):
    async def search_tweets(self, query: str):
        credentials = {
            "username": "your_twitter_username",
            "password": "your_twitter_password"
        }
        return await search(query, credentials)
```

## API Documentation

Once the service is running, you can access the interactive API documentation at:

- Local: [http://localhost:6011/docs](http://localhost:6011/docs)
- Docker: [http://localhost:6011/docs](http://localhost:6011/docs)

The Swagger UI provides:
- Complete documentation of all endpoints
- Request/response schemas
- Interactive testing interface

## Security Considerations

- Store credentials securely using environment variables or a secure configuration management system
- Use HTTPS in production environments
- Implement rate limiting for production deployments
- Monitor for suspicious activity

## Troubleshooting

### Platform-Specific Issues

1. **Mac-Specific Issues**
   - Docker networking problems are common on Mac:
     ```bash
     # If using Docker and seeing connection issues, switch to local setup:
     brew services stop mongodb-community  # Stop any existing MongoDB
     brew services start mongodb-community # Ensure fresh MongoDB start
     npm start  # Run service locally
     ```
   - Local MongoDB connection issues:
     ```bash
     # Verify MongoDB is running
     brew services list | grep mongodb
     # Check MongoDB logs
     tail -f /usr/local/var/log/mongodb/mongo.log
     ```
   - Port conflicts:
     ```bash
     # Check if port 6011 is in use
     lsof -i :6011
     # If needed, change port in .env file
     echo "PORT=6012" >> .env
     ```

### First-Time Setup Issues

The most common issue is the initial authentication setup. Follow these steps for first-time setup:

1. **Mobile Device Login (Recommended Method)**
   ```bash
   # First, start the X-API service
   docker-compose up -d
   ```
   Then:
   - Open X (Twitter) on your mobile device
   - Ensure your mobile device is on the same network as the X-API service
   - Log in to your X account on the mobile device
   - Wait a few minutes for the cookies to be cached
   - Try running your agent script again

2. **HTTP 500 Errors**
   If you're getting 500 Internal Server Error responses:
   - This usually means the authentication cookies are invalid or missing
   - Follow the mobile device login process above
   - Check MongoDB connection and data:
   ```bash
   # Connect to MongoDB container
   docker exec -it x-api-mongodb mongosh
   # Check cookies collection
   use x-api
   db.cookies.find()
   ```

### Common Runtime Issues

1. **Connection Problems**
   - Verify the X-API service is running:
   ```bash
   docker ps | grep x-api
   curl http://localhost:6011/health
   ```
   - Check MongoDB container status:
   ```bash
   docker logs x-api-mongodb
   ```
   - Ensure correct environment variables:
   ```python
   # In your .env file
   X_API="http://localhost:6011/api"
   ```

2. **Authentication Failures**
   - Verify your credentials in the configuration:
   ```yaml
   # twitter_agent.yaml
   twitter:
     credentials:
       username: "your_username"
       password: "your_password"
   ```
   - Check for IP restrictions or suspicious activity flags
   - Try refreshing cookies by repeating the mobile login process
   - Ensure you're not using a VPN that might block Twitter

3. **Rate Limiting and Performance**
   - Implement exponential backoff:
   ```python
   import random
   import asyncio
   
   async def with_retry(func, max_retries=3):
       for attempt in range(max_retries):
           try:
               return await func()
           except Exception as e:
               if attempt == max_retries - 1:
                   raise
               wait_time = (2 ** attempt) + random.uniform(0, 1)
               await asyncio.sleep(wait_time)
   ```
   - Monitor response headers for rate limits
   - Consider using multiple accounts for high-volume operations

### Verification Steps

You can verify your setup is working with this simple test:

```python
from pancaik.utils.x_api import get_profile
import asyncio

async def verify_setup():
    credentials = {
        "username": "your_username",
        "password": "your_password"
    }
    profile = await get_profile(credentials["username"], credentials)
    
    if not profile:
        print("\nX-API Service Connection Issue:")
        print("--------------------------------")
        print("1. Open X (Twitter) on your mobile device")
        print("2. Ensure device is on the same network")
        print("3. Log in to your X account")
        print("4. Try again in a few minutes")
        return False
    
    print("✓ Setup verified successfully!")
    return True

# Run the verification
asyncio.run(verify_setup())
```

### Best Practices

1. **Environment Setup**
   - Use separate development and production configurations
   - Keep credentials in environment variables
   - Monitor service logs regularly

2. **Error Handling**
   - Implement proper error handling and retries
   - Log all API interactions for debugging
   - Set up alerts for authentication failures

3. **Maintenance**
   - Regularly verify cookie validity
   - Update Docker images periodically
   - Monitor MongoDB storage usage

## License

This middleware is licensed under the MIT License. See the LICENSE file in the repository for details.

## Disclaimer

This service is not affiliated with, maintained, authorized, endorsed, or sponsored by Twitter, Inc. or any of its affiliates. 