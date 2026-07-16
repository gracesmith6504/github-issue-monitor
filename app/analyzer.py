from app.core.assessment import assess_issue
from app.core.llm import LLMClient


def analyze_issue(issue, token, model):
    client = LLMClient(api_key=token)
    return assess_issue(issue, client, model)
