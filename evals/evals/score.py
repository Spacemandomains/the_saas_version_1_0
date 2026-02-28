import json
from typing import List, Callable, Dict

def score_response(response: str, expected_contains: List[str]) -> bool:
    """Return True if all expected keywords are found in the response (case-insensitive)."""
    response_lower = response.lower() if response else ""
    return all(keyword.lower() in response_lower for keyword in expected_contains)

def run_tests(agent_function: Callable[[str], str], test_cases_path: str = "test_cases.json") -> List[Dict[str, bool]]:
    """Run evaluation tests against the agent_function using the provided test cases file.

    Args:
        agent_function: The function that generates a response given a prompt.
        test_cases_path: Path to the JSON file containing test cases.

    Returns:
        A list of dicts with the prompt and whether the agent's response passed the test.
    """
    with open(test_cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    results = []
    for case in cases:
        prompt = case.get("prompt")
        expected = case.get("expected_contains", [])
        response = agent_function(prompt)
        passed = score_response(response, expected)
        results.append({"prompt": prompt, "passed": passed})

    return results

# Example usage (pseudo-code):
# from cpo_agent import CPOAgent
# agent = CPOAgent(product_brief=..., tools=...)
# def agent_function(prompt: str) -> str:
#     return agent.handle_input(prompt)
#
# results = run_tests(agent_function)
# for r in results:
#     print(f"Prompt: {r['prompt']} - Passed: {r['passed']}")
