# smoke_test.py: checks your Data and Power layers
# Install once: pip install openai python-dotenv requests

import os
import uuid
import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
results = []

def check(name, fn):
    try:
        fn()
        results.append(("PASS", name, ""))
    except Exception as error:
        results.append(("FAIL", name, str(error)[:150]))

def need(*names):
    for name in names:
        assert os.environ.get(name), f"{name} is missing from .env"

def zetaris_web():
    url = os.environ.get("ZETARIS_BASE_URL", "http://localhost:3000")
    requests.get(url, timeout=10).raise_for_status()

def zetaris_sql():
    need("ZETARIS_REST_URL", "ZETARIS_ORG_ID", "ZETARIS_API_KEY")
    url = os.environ["ZETARIS_REST_URL"].rstrip("/") + "/sql-editor/sqls/run"
    
    headers = {
        "Authorization": f"Bearer {os.environ['ZETARIS_API_KEY'].strip()}",
        "X-Org-ID": str(os.environ["ZETARIS_ORG_ID"]).strip(),
        "X-Request-ID": str(uuid.uuid4()),
        "Content-Type": "application/json"
    }
    
    payload = {
        "queryId": str(uuid.uuid4()),
        "sql": "SELECT 1",
        "source": "SqlEditor",
        "limit": 1
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json().get("data")
    assert data and str(data[0][0]) == "1", "unexpected reply: " + response.text[:80]

def nemotron():
    need("MODEL_BASE_URL", "MODEL_API_KEY", "NEMOTRON_MODEL")
    client = OpenAI(
        base_url=os.environ["MODEL_BASE_URL"],
        api_key=os.environ["MODEL_API_KEY"],
    )
    reply = client.chat.completions.create(
        model=os.environ["NEMOTRON_MODEL"],
        messages=[{"role": "user", "content": "Reply with the single word: ready"}],
    )
    assert reply.choices, "no reply from the model"

# Ejecución de los 3 chequeos
check("Data: Zetaris web interface", zetaris_web)
check("Data: Zetaris runs SQL over its REST API", zetaris_sql)
check("Power: Nemotron replies", nemotron)

for status, name, detail in results:
    print(f"{status} {name} {detail}")