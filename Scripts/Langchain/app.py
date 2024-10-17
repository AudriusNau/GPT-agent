import os
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk.errors import SlackApiError
from flask import Flask, request

# Initialize the Slack app
app = App(
    token=token,
    signing_secret=signing_secret
)

# Initialize a Flask app
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

@flask_app.route("/", methods=["POST"])
def slack_events():
    # Handles Slack events by using the handler from slack_bolt
    return handler.handle(request)

@app.event("app_mention")
def mention_handler(event, say):
    try:
        channel_id = event['channel']
        text = event['text']

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Hi there! To start Marketo chat press the button"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "New Chat"
                        },
                        "url": "https://omc-co-pilot.azurewebsites.net/"
                    }
                ]
            }
        ]

        say(channel=channel_id, blocks=blocks)

    except SlackApiError as e:
        print(f"Error responding to app mention: {e}")

# Run the Flask app
if __name__ == "__main__":
    flask_app.run(port=3000)
