import os
from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from openai import AzureOpenAI
import json
import re
import logging
import redis

api_key = os.environ.get("AOAIKey")
endpoint = os.environ.get("AOAIEndpoint")
deployment = os.environ.get("AOAIDeploymentId")
slack_bot_token = os.getenv("SLACK_BOT_TOKEN")
slack_signing_secret = os.getenv("SLACK_SIGNING_SECRET")

logging.basicConfig(filename='general_history.log', level=logging.INFO,
                    format='%(asctime)s -  %(levelname)s - %(message)s')

logging.getLogger('werkzeug').disabled = True

openai_client = AzureOpenAI(
  api_key = api_key,
  api_version = "2023-08-01-preview",
  base_url=f"{endpoint}/openai/deployments/{deployment}/extensions"
)
app = App(token=slack_bot_token, signing_secret=slack_signing_secret)
slack_client  = WebClient(token=slack_bot_token)

flask_app = Flask(__name__)
flask_app.logger.setLevel(logging.ERROR)
handler = SlackRequestHandler(app)
replied_threads = {}
# r = redis.Redis(host='localhost', port=6379, db=0)
thread_ids = []

def get_openai_response(chat_log):
    
    response = openai_client.chat.completions.create(
        model=deployment,
        messages=chat_log,
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
        },
        temperature=0,
        max_tokens=800,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None
    )
    assistant_response = response.choices[0].message.content
    matches = re.findall(r"\[doc\d+\]", assistant_response)
    if matches:
        urls = extract_urls(response)
        assistant_response = assistant_response + "\n" + "\n".join(urls)

    return assistant_response

def extract_urls(response):
    urls = []
    data = json.loads(response.choices[0].message.context["messages"][0]["content"])
    pattern = r"source: (\S+)"
    for citation in data["citations"]:
        content = citation["content"]
        found_urls = re.findall(pattern, content)
        urls.extend(found_urls)
    return urls

def extract_bot_id(text:str)-> str:
    pattern = r"<@(\w+)>"
    bot_name = re.findall(pattern, text)
    bot_ids = re.search(pattern, text)
    return str(bot_ids[0]), str(bot_name[0]) if bot_ids else ''

def remove_urls(text):
    url_pattern = r'<https?://\S+'
    text_without_urls = re.sub(url_pattern, '', text).strip()
    return text_without_urls



@flask_app.route("/", methods=["POST"])
def slack_events():
    response = handler.handle(request)
    response.headers['x-slack-no-retry'] = '1'
    return response

def create_chatlog():
    chat_log = []
    chat_log.append({"role":"system", "content": """You are an AI assistant that helps people find information about Marketo.
                  All questions will be about Marketo. Assistant should always be polite and helpful. 
                 Always include references to documentation in assistant answers."""})
    return chat_log

def parse_conversation (messages):
    chat_log = create_chatlog()
    logging.warning("======================= New Conversation ===================================")
    first_message = messages[0]['text']
    bot_mention, bot_name = extract_bot_id(first_message)
    for index, message in enumerate(messages):
        if index == 0:
            text = message['text'].replace(bot_mention, "").strip()
            chat_log.append({"role":"user", "content": text})
            logging.info(text)
        elif message['user'] == bot_name:
            reply = remove_urls(message['text'])
            chat_log.append({"role": "assistant", "content": reply})
            logging.info(reply)
        else:
            chat_log.append({"role":"user", "content": message['text']})
            logging.info(message['text'])
    
    return chat_log


@app.event("message")
def handle_message_events(event):

    if 'parent_user_id' in event:
        channel_id = event['channel']
        thread_ts = event.get('thread_ts', event['ts'])
        # if r.exists(thread_ts):
        if thread_ts in thread_ids:
            response = slack_client.conversations_replies(channel=channel_id, ts=thread_ts)
            messages = response.data.get('messages', [])
            chat_log = parse_conversation(messages)
            try:
                response_message = get_openai_response(chat_log)
                logging.info(response_message)
                slack_client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=response_message)
            except SlackApiError as e:
                print(f"Error in follow-up reply: {e}")

@app.event("app_mention")
def handle_mention_events(event, say):
    chat_log = create_chatlog()
    channel_id = event['channel']
    thread_ts = event.get('thread_ts', event['ts'])
    user_message = event['text']
    replied_threads[thread_ts] = True
    thread_ids.append(thread_ts)
    # r.set(thread_ts, "True", ex=86400)
    bot_mention, bot_name = extract_bot_id(user_message)
    text = user_message.replace(bot_mention, "").strip()
    chat_log.append({"role":"user", "content": text})
    response_message = get_openai_response(chat_log)
    logging.warning("======================= New Conversation ===================================")
    logging.info(text)
    logging.info(response_message)
    slack_client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=response_message)

if __name__ == "__main__":
    flask_app.run(port=3000)
