from flask import Flask, request, Response, stream_with_context, jsonify
from werkzeug.datastructures import ImmutableMultiDict, MultiDict
import requests
import json
import uuid
from datetime import datetime
from urllib.parse import urlparse
import time


app = Flask(__name__)

@app.route('/ohmygpt/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy(subpath):
    # Capture incoming request data
    incoming_data = request.get_json()  # Assuming JSON input
    incoming_headers = request.headers
    incoming_method = request.method
    incoming_args = request.args
    url = ''

    # Check if the model is 'dall-e-3' and adjust the request accordingly
    if incoming_data.get('model') == 'dall-e-3':
        # Extract the last user message content
        prompt_content = next((message['content'] for message in reversed(incoming_data['messages']) if message['role'] == 'user'), '')

        # Change the request body format for 'dall-e-3'
        outgoing_data = {
            "model": "dall-e-3",
            "prompt": prompt_content,
            "n": 1,
            "size": "1024x1024"
        }

        print("prompt_content: ", prompt_content)

        # Set the new URL for 'dall-e-3' requests
        url = f'https://api.ohmygpt.com/v1/images/generations'
    else:
        # For other models, use the original subpath and request data
        outgoing_data = incoming_data
        url = f'https://api.ohmygpt.com/{subpath}'

    # Convert ImmutableMultiDict to a regular mutable dict
    incoming_headers = MultiDict(incoming_headers)

    # Modify the 'Host' header to match the new URL's host
    parsed_url = urlparse(url)
    incoming_headers['Host'] = parsed_url.netloc

    # Convert back to ImmutableMultiDict if necessary
    incoming_headers = ImmutableMultiDict(incoming_headers)

    # Forward the request to the new URL and capture the response
    req = requests.request(incoming_method, url, headers=incoming_headers, json=outgoing_data, params=incoming_args, stream=True, verify=False)

    # Process the response before streaming
    response_json = req.json()
    tokens = []
    for item in response_json.get('data', []):
        revised_prompt = item.get('revised_prompt', 'No prompt provided')
        image_url = item.get('url', '#')

        # Split the revised_prompt into tokens if necessary
        # Here we assume each word is a token for simplicity
        revised_prompt = '`prompt: ' + revised_prompt + '`\n'

        # prompt_tokens = revised_prompt.split()
        prompt_tokens = [revised_prompt]

        # Format the output string for each token
        for token in prompt_tokens:
            tokens.extend(token)

        # Add the image URL and download link as separate characters
        image_url_formatted = f"![image]({image_url})\n"
        download_link_formatted = f"[Download]({image_url})\n"
        for char in image_url_formatted + download_link_formatted:
            tokens.append(char)

    def generate():
        for token in tokens:
            time.sleep(0.06)
            decoded_chunk = token

            chunk_id = str(uuid.uuid4())
            created_time = int(datetime.utcnow().timestamp())

            # Create a JSON object for each chunk
            chunk_data = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": "ohmygpt-convert",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": decoded_chunk
                        },
                        "finish_reason": None
                    }
                ]
            }

            # Convert the JSON object to a string and yield it as a Server-Sent Event
            yield f"data: {json.dumps(chunk_data)}\n\n"
        print("done")

    # Define the response headers for SSE
    headers = {
        'Cache-Control': 'no-cache',
        'Content-Type': 'text/event-stream',
        'Connection': 'keep-alive',
    }

    # Stream the response back to the client
    return Response(stream_with_context(generate()), headers=headers)

if __name__ == '__main__':
    app.run(host= '0.0.0.0', port=54321 , debug=True)

# Run Command: gunicorn -w 3 --threads 2 --bind 0.0.0.0:54321 convert:app --access-logfile "./access-$(date +\%Y-\%m-\%d-\%H-\%M).log" --error-logfile "./error-$(date +\%Y-\%m-\%d-\%H-\%M).log"
