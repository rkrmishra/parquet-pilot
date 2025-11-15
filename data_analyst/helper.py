"""
helper.py
-----------------
Small helper module to load environment variables and return important
configuration values such as OpenAI API key and Phoenix collector endpoint.
Keep secrets out of source code by using a `.env` file or environment vars.
"""

import os
from dotenv import load_dotenv, find_dotenv
                     
def load_env():
    """Load environment variables from a .env file into the process env.

    `find_dotenv` attempts to find a .env file in parent directories; calling
    this at startup makes sensitive config available to the running process.
    """
    _ = load_dotenv(find_dotenv(), override=True)

def get_openai_api_key():
    """Return the OpenAI API key from environment variables (loads .env).

    This is a thin helper that guarantees a `.env` file is loaded first.
    """
    load_env()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    return openai_api_key


def get_phoenix_endpoint():
    """Return the Phoenix collector endpoint from environment variables.

    The function reads `.env` into the process environment and returns the
    `PHOENIX_COLLECTOR_ENDPOINT` value if present (may be None).
    """
    load_env()
    phoenix_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    return phoenix_endpoint


