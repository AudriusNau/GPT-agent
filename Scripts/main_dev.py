import os
from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import re
import logging
import redis
from langchain.schema import HumanMessage, AIMessage,SystemMessage 
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone
from tqdm.autonotebook import tqdm
from langchain_openai import ChatOpenAI
from langchain_pinecone import PineconeVectorStore as LPPinecone
from langchain.chains import RetrievalQAWithSourcesChain
from langchain.memory import ConversationBufferMemory



slack_bot_token = os.getenv("SLACK_BOT_TOKEN_dev")
slack_signing_secret = os.getenv("SLACK_SIGNING_SECRET_dev")

logging.basicConfig(filename='general_history_dev.log', level=logging.INFO,
                    format='%(asctime)s -  %(levelname)s - %(message)s')

logging.getLogger('werkzeug').disabled = True


app = App(token=slack_bot_token, signing_secret=slack_signing_secret)
slack_client  = WebClient(token=slack_bot_token)

flask_app = Flask(__name__)
flask_app.logger.setLevel(logging.ERROR)
handler = SlackRequestHandler(app)
# r = redis.Redis(host='localhost', port=6379, db=1)
thread_ids = []
#==============================================
#==============================================
pc = Pinecone(api_key=os.environ.get('PINECONE_API_KEY'))
model_name = 'text-embedding-ada-002'
embed = OpenAIEmbeddings(
    model=model_name,
    openai_api_key=os.environ['OPENAI_API_KEY']
)
index_name = 'pilot'
index = pc.Index(index_name)

text_field = "text"  # the metadata field that contains text
vectorstore = LPPinecone(
    index, embed, text_field
)

llm = ChatOpenAI(
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    model_name='gpt-3.5-turbo',
    temperature=1,
    max_tokens=800
)
#==============================================
#==============================================

def get_openai_response(chat_log):
    # separate last message from chat_log
    last_message = chat_log.pop()
    last_message = last_message.content
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True, input_key="question", output_key="answer")
    qa_with_sources = RetrievalQAWithSourcesChain.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vectorstore.as_retriever(),
        memory=memory
    )
    for query in chat_log:
        memory.chat_memory.add_message(query)
    result = qa_with_sources.invoke(last_message)
    return result['answer'] + ' ' + result['sources']

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
    with open('message.log', 'r') as file:
        message = file.read()
    chat_log.append(SystemMessage(content= message))

    return chat_log

def parse_conversation (messages):
    chat_log = create_chatlog()
    logging.warning("======================= New Conversation ===================================")
    first_message = messages[0]['text']
    bot_mention, bot_name = extract_bot_id(first_message)
    for index, message in enumerate(messages):
        if index == 0:
            text = message['text'].replace(bot_mention, "").strip()
            chat_log.append(HumanMessage(content = text))
            logging.info(text)
        elif message['user'] == bot_name:
            reply = remove_urls(message['text'])
            chat_log.append(AIMessage(content = reply))
            logging.info(reply)
        else:
            chat_log.append(HumanMessage(content = message['text']))
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
            conversation = response.data.get('messages', [])
            chat_log = parse_conversation(conversation)
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
    thread_ids.append(thread_ts)
    # r.set(thread_ts, "True", ex=86400)
    bot_mention, bot_name = extract_bot_id(user_message)
    text = user_message.replace(bot_mention, "").strip()
    chat_log.append(HumanMessage(content = text))
    response_message = get_openai_response(chat_log)
    logging.warning("======================= New Conversation ===================================")
    logging.info(text)
    logging.info(response_message)
    slack_client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=response_message)

if __name__ == "__main__":
    flask_app.run(port=3001)
