from app.core.assessment import assess_issue
from app.core.llm import GitHubModelsClient


def analyze_issue(issue, token, model):
    client = GitHubModelsClient(api_key=token)
    return assess_issue(issue, client, model)
