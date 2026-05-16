import datetime
import logging
import os
import time

import flask  # type: ignore
import slack_sdk  # type: ignore
from slack_sdk.errors import SlackApiError  # type: ignore
from slack_sdk.signature import SignatureVerifier  # type: ignore

start_time = time.time()

SOURCE_COMMIT = os.getenv("SOURCE_COMMIT", "")
short_commit = SOURCE_COMMIT[:7] if SOURCE_COMMIT else "unknown"

# Environment variables
try:
    SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
    SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
    UPLOAD_CHANNEL_ID = os.environ["UPLOAD_CHANNEL_ID"]
    OWNER_USER_ID = os.environ["OWNER_USER_ID"]
except KeyError as e:
    raise ValueError(f"Missing required environment variable: {e.args[0]}")

slack_client = slack_sdk.WebClient(SLACK_BOT_TOKEN)
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

try:
    auth_response = slack_client.auth_test()
    if not auth_response.get("ok"):
        raise ValueError(
            f"Failed auth test: {auth_response.get('error', 'Unknown error')}"
        )
except SlackApiError as e:
    raise ValueError(f"Slack API error during auth test: {e.response['error']}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Check if in upload channel
try:
    response = slack_client.conversations_info(channel=UPLOAD_CHANNEL_ID)
    if not response.get("channel", {}).get("is_member", False):
        logger.info(
            f"Bot is not a member of channel {UPLOAD_CHANNEL_ID}, attempting to join..."
        )
        join_response = slack_client.conversations_join(channel=UPLOAD_CHANNEL_ID)
except SlackApiError as e:
    raise ValueError(f"Slack API error: {e.response['error']}")

app = flask.Flask(__name__)


@app.route("/")
def index():
    return flask.Response("Online", status=200, mimetype="text/plain")


@app.route("/health")
def health():
    return flask.jsonify(
        {
            "status": "ok",
            "commit": short_commit,
            "uptime": str(datetime.timedelta(seconds=int(time.time() - start_time))),
        }
    )


@app.errorhandler(404)
def not_found(e):
    return flask.Response("Not Found", status=404, mimetype="text/plain")


@app.route("/slack/events", methods=["POST"])
def slack_events_test(event):
    if "challenge" in event:
        return event.get("challenge"), 200
    print(event)
    return "", 200


def slack_events(event):
    if not signature_verifier.is_valid_request(
        body=flask.request.get_data().decode("utf-8"),
        headers=dict(flask.request.headers),
    ):
        return "Invalid signature", 403

    if "challenge" in event:
        return event.get("challenge"), 200

    logger.info(event)

    if event.get("type") != "message":
        return "", 200

    user_id = event.get("user")
    channel_id = event.get("channel")
    text = event.get("text")

    if channel_id != UPLOAD_CHANNEL_ID:
        return "", 200

    if not text.strip().startswith("!cdn"):
        return "", 200

    if user_id != OWNER_USER_ID:
        slack_client.chat_postEphemeral(
            user=user_id,
            channel=channel_id,
            text=f"Only the owner of this bot (<@{OWNER_USER_ID}>) is allowed to use this!",
        )

    try:
        if event.get("type") == "message":
            # TODO: make sure a file is included
            if not False:
                slack_client.chat_postEphemeral(
                    user="t",
                    channel="",
                    text="No file detected",
                )
                return "", 200

    except Exception as e:
        logger.warning(e)
    return "", 200


# @app.route("/slack/command", methods=["POST"])
# def slack_commands():
#     if not signature_verifier.is_valid_request(
#         body=flask.request.get_data().decode("utf-8"),
#         headers=dict(flask.request.headers),
#     ):
#         return "Invalid signature", 403

#     try:
#         data = flask.request.form
#         command = data["command"]
#         text = data["text"]
#         channel_id = data["channel_id"]
#         user_id = data["user_id"]

#         if command == "":
#             return "", 200
#         else:
#             logger.warning(f"Received unknown command: {command}")
#             slack_client.chat_postEphemeral(
#                 user=user_id,
#                 channel=channel_id,
#                 text=f"Unknown command: {command}",
#             )
#             return "", 200

#     except Exception as e:
#         logger.warning(e)

#     return "", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
