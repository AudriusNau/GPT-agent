import os
from langchain_openai import OpenAI
from pinecone import Pinecone
from pinecone import ServerlessSpec

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from langchain_openai import ChatOpenAI
from langchain.vectorstores import Pinecone


os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY") 

client = ChatOpenAI(
    openai_api_key=os.environ["OPENAI_API_KEY"],
    model='gpt-3.5-turbo'
)


messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="Hi AI, how are you today?"),
    AIMessage(content="I'm great thank you. How can I help you?"),
    HumanMessage(content="I'd like to understand machine learning.")
]

res = client.invoke(messages)

messages.append(res)
prompt = HumanMessage(
    content="What do you know about campaign?"
)
messages.append(prompt)
res = client.invoke(messages)
# print(response.choices[0].message.content)

pine_api_key = os.getenv("PINECONE_API_KEY") 

# configure client
pc = Pinecone(api_key=pine_api_key)


spec = ServerlessSpec(
    cloud="aws", region="us-west-1"
)

import time

index_name = 'pilot'
existing_indexes = [
    index_info["name"] for index_info in pc.list_indexes()
]

if index_name not in existing_indexes:
    pc.create_index(
        index_name,
        dimension=1536,  # dimensionality of ada 002
        metric='dotproduct',
        spec=spec
    )
    while not pc.describe_index(index_name).status['ready']:
        time.sleep(1)

index = pc.Index(index_name)
time.sleep(1)


