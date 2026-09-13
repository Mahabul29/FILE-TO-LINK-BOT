import json
import os
import urllib.request

# Fetch BOT_TOKEN from Netlify Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")

def handler(event, context):
    # Only process POST requests coming from Telegram Webhooks
    if event.get("httpMethod") != "POST":
        return {
            "statusCode": 405,
            "body": json.dumps({"error": "Method Not Allowed"})
        }

    try:
        # Parse incoming Telegram JSON update
        body = json.loads(event.get("body", "{}"))

        if "message" in body:
            chat_id = body["message"]["chat"]["id"]
            
            # Telegram Webhook Response
            telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = json.dumps({
                "chat_id": chat_id,
                "text": "⚠️ Warning: Netlify serverless functions cannot stream files or generate persistent download links."
            }).encode("utf-8")

            req = urllib.request.Request(
                telegram_url, 
                data=payload, 
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req)

        return {
            "statusCode": 200,
            "body": json.dumps({"status": "ok"})
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
      
