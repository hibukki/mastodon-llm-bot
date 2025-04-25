import os
import re
import html
import google.generativeai as genai
from mastodon import Mastodon, StreamListener
from dotenv import load_dotenv
import logging
import random  # Added for probability check

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- Configuration ---
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN")
MASTODON_API_BASE_URL = os.getenv("MASTODON_API_BASE_URL")
BOT_USERNAME = os.getenv("BOT_USERNAME")  # Used to prevent self-replies

if not all(
    [GEMINI_API_KEY, MASTODON_ACCESS_TOKEN, MASTODON_API_BASE_URL, BOT_USERNAME]
):
    logging.error(
        "Error: Required environment variables are missing. Check your .env file."
    )
    exit(1)

# Gemini configuration
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Using flash for speed and cost-effectiveness in a chat context
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
    logging.info("Gemini API configured successfully.")
except Exception as e:
    logging.error(f"Failed to configure Gemini API: {e}")
    exit(1)


SYSTEM_PROMPT = """
You are a compassionate and insightful psychologist bot. Your goal is to offer brief, supportive, and potentially thought-provoking comments based on the user's post.
Keep your responses concise, typically one or two sentences. Focus on empathy, validation, or gentle reframing.
Do not give direct advice or diagnosis. Avoid overly clinical language.
If the post seems like a cry for help or indicates immediate danger, gently suggest seeking professional help or contacting emergency services, but do not attempt to handle the crisis yourself.
Example Interaction:
User posts: "Feeling really overwhelmed with work deadlines this week."
Your response: "It sounds like a lot is on your plate right now. Remember to take small breaks if you can."
"""

# --- Mastodon API Initialization ---
BOT_ACCOUNT_ID = None
try:
    mastodon = Mastodon(
        access_token=MASTODON_ACCESS_TOKEN, api_base_url=MASTODON_API_BASE_URL
    )
    # Verify authentication and get bot's own ID
    my_account = mastodon.account_verify_credentials()
    BOT_ACCOUNT_ID = my_account["id"]
    logging.info(
        f"Successfully connected to Mastodon as {my_account['username']} (ID: {BOT_ACCOUNT_ID})"
    )

except Exception as e:
    logging.error(f"Failed to connect to Mastodon: {e}")
    exit(1)


# --- Utility Function to clean HTML ---
def strip_html(text_html):
    # Decode HTML entities first (e.g., &amp; -> &)
    text = html.unescape(text_html)
    # Remove mentions (@user@domain) - they might confuse Gemini
    text = re.sub(r"@\w+(?:@[-.\w]+)?", "", text)
    # Remove hashtags (#tag) - they might confuse Gemini
    text = re.sub(r"#\w+", "", text)
    # Basic HTML tag removal (remove content between < and >)
    text = re.sub(r"<[^>]+>", "", text)
    # Remove leftover whitespace
    text = " ".join(text.split())
    return text.strip()


# --- Mastodon Stream Listener ---
class TimelineListener(StreamListener):  # Renamed from MentionListener
    def on_update(self, status):
        # This method now receives status updates directly

        # --- Filter incoming statuses ---
        # Only process public, top-level statuses from other users
        if (
            status.get("in_reply_to_id") is not None
            or status.get("account", {}).get("id") == BOT_ACCOUNT_ID
            or status.get("visibility") != "public"
            or status.get("reblog") is not None
        ):
            # logging.debug("Ignoring non-public/reply/own/boost status.") # Optional: debug logging
            return

        # --- Probability Check (e.g., 10% chance to reply) ---
        if random.random() > 0.95:
            # logging.debug("Skipping status based on probability.") # Optional: debug logging
            return

        # --- Process the eligible status ---
        sender_acct = status["account"]["acct"]
        sender_id = status["account"]["id"]  # Still useful for logging
        status_id = status["id"]
        content_html = status["content"]

        logging.info(f"Processing public status from {sender_acct} (ID: {status_id})")

        # Clean the HTML content to get plain text
        plain_content = strip_html(content_html)
        logging.info(f"Cleaned content: '{plain_content}'")

        if not plain_content:
            logging.warning("Status content is empty after cleaning, skipping.")
            return

        # --- Call Gemini API ---
        try:
            logging.info("Sending content to Gemini...")
            # Combine system prompt with user content for context
            full_prompt = f'{SYSTEM_PROMPT}\n\nUser post: "{plain_content}"'

            # Generate content using Gemini
            response = gemini_model.generate_content(full_prompt)

            gemini_reply_text = ""
            # Check if response has text content (new API versions might differ)
            try:
                gemini_reply_text = response.text
            except ValueError:
                # Handle cases where generation might fail or be blocked by safety filters
                logging.warning(
                    f"Gemini did not return text. Response parts: {response.parts}"
                )
                # Check safety feedback if available
                safety_feedback = getattr(response, "prompt_feedback", None)
                block_reason = getattr(safety_feedback, "block_reason", None)
                if block_reason:
                    logging.warning(
                        f"Gemini generation blocked. Reason: {block_reason}"
                    )
                    # Reply with a generic message indicating blockage
                    gemini_reply_text = "I'm unable to respond to that specific content due to safety guidelines."
                else:
                    logging.warning(
                        "Gemini response structure unexpected or generation failed without specific block reason."
                    )
                    gemini_reply_text = (
                        "I had trouble processing that request. Please try rephrasing."
                    )

            logging.info(f"Gemini response: '{gemini_reply_text}'")

            # --- Post Reply to Mastodon ---
            if gemini_reply_text:
                # Ensure the reply mentions the original poster correctly
                # Use the acct which includes the domain for remote users if needed,
                # but for local dev, username might suffice. acct is safer.
                reply_text = f"@{sender_acct} {gemini_reply_text}"

                # Truncate if response is too long (Mastodon limits are usually 500 chars)
                # Be mindful of character vs byte limits if using complex unicode
                max_len = 490  # Leave some room for the mention and potential buffer
                if len(reply_text) > max_len:
                    reply_text = reply_text[:max_len] + "..."
                    logging.warning("Truncated Gemini response due to length.")

                logging.info(f"Posting reply to status {status_id}: '{reply_text}'")
                mastodon.status_post(
                    status=reply_text,
                    in_reply_to_id=status_id,
                    # Consider 'unlisted' instead of 'direct' for replies to public posts
                    visibility="unlisted",
                )
                logging.info("Reply posted successfully.")
            else:
                logging.warning(
                    "Gemini response was empty or invalid, not posting reply."
                )

        except Exception as e:
            # Log the full exception traceback for debugging
            logging.error(
                f"Error processing status {status_id} or calling APIs: {e}",
                exc_info=True,
            )
            # Optionally post an error message back? Be careful not to spam.
            try:
                mastodon.status_post(
                    status=f"@{sender_acct} Sorry, I encountered an internal error while trying to respond.",
                    in_reply_to_id=status_id,
                    visibility="direct",  # Error message can be direct
                )
                logging.info("Posted error message to user.")
            except Exception as post_error:
                logging.error(f"Failed to post error message reply: {post_error}")

    # Add other handlers if needed (e.g., on_delete, on_error)
    def on_error(self, error):
        logging.error(f"Stream connection error: {error}")


# --- Main Execution ---
if __name__ == "__main__":
    logging.info("Starting Mastodon local timeline listener...")  # Updated log message
    try:
        # Connect to the local public stream
        mastodon.stream_public(
            TimelineListener(),
            local=True,  # Only listen to statuses from the local instance
            run_async=False,
            reconnect_async=False,
        )
    except KeyboardInterrupt:
        logging.info("Listener stopped by user (KeyboardInterrupt).")
    except Exception as e:
        # Log unexpected errors during streaming
        logging.error(f"Mastodon stream encountered an error: {e}", exc_info=True)
    finally:
        logging.info("Bot shutting down.")
