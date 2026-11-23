import os
import requests

from dotenv import load_dotenv

load_dotenv()

RPC_URL = os.getenv("ALCHEMY_RPC_URL")

def rpc_call(method, params):

    response = requests.post(
        RPC_URL,
        json={
            'jsonrpc': '2.0',
            'id': 1,
            'method': method,
            'params': params
        },
        timeout=60
    )

    response.raise_for_status()

    result = response.json()

    if 'error' in result:
        raise RuntimeError(result['error'])

    return result['result']

