from firecrawl import FirecrawlApp
from pydantic import BaseModel, Field

# Initialize the FirecrawlApp with your API key
app = FirecrawlApp(api_key='fc-79e1e50bf0da4a4fbfcfd85de4dc4944')

class ExtractSchema(BaseModel):
    company_mission: str
    supports_sso: bool
    is_open_source: bool
    is_in_yc: bool

prompt = """
for the given company, find me their general info, about, contact info, news from the latest blog, top clients/customers
"""
data = app.extract([
  'https://toccominerale.com/*', 
], prompt=prompt, schema=ExtractSchema.model_json_schema())
print(data)