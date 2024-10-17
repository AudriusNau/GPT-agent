import os
from openai import AzureOpenAI
import dotenv
import re
dotenv.load_dotenv()
import json
from loguru import logger

endpoint = os.environ.get("AOAIEndpoint")
api_key = os.environ.get("AOAIKey")
deployment = os.environ.get("AOAIDeploymentId")
urls = []



def extract_source(response):
    urls.clear()
    text = response.choices[0].message.context["messages"][0]["content"]
    data = json.loads(text)
    pattern = r"source: (\S+)"
    for citation in data["citations"]:
        content = citation["content"]
        found_urls = re.findall(pattern, content)
        urls.extend(found_urls)
    return urls

client = AzureOpenAI(
    base_url=f"{endpoint}/openai/deployments/{deployment}/extensions",
    api_key=api_key,
    api_version="2023-08-01-preview",
)

response = client.chat.completions.create(
    
    model=deployment,
    messages=[
        {
            "role": "user",
            "content": "How to create a campaign?",
        },
    ],
    extra_body={
        "dataSources": [
            {
                "type": "AzureCognitiveSearch",
                "parameters": {
                    "endpoint": os.environ["SearchEndpoint"],
                    "key": os.environ["SearchKey"],
                    "indexName": os.environ["SearchIndex"]
                }
            }
        ]
    }
)
print(response.choices[0].message.content)

logger.remove()
logger.add("general_history.log", rotation="10 day")
user_message = "Hello, how are you?"
response_message = "I'm fine, thank you!"
logger.warning(f"======================= New conversation =========================================")
logger.info(f"User Message: {user_message}")
logger.info(f"Response: {response_message}")