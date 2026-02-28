import json
import os


def score_response(response: str, expected_contains: list) -> float:
    """
    Scores a response based on the presence of expected keywords or phrases.

    :param response: The agent's response.
    :param expected_contains: List of keywords or phrases expected in the response.
    :return: A float score between 0 and 1.
    """
    if not expected_contains:
        return 1.0

    response_lower = response.lower()
    matches = sum(1 for keyword in expected_contains if keyword.lower() in response_lower)
    return matches / len(expected_contains)


def run_tests(agent_function):
    """
    Runs the test cases against the provided agent function.

    :param agent_function: Function that takes a prompt and returns a response.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_file_path = os.path.join(script_dir, 'test_cases.json')

    with open(test_file_path, 'r') as file:
        test_cases = json.load(file)

    results = []
    for test in test_cases:
        prompt = test['prompt']
        expected_contains = test['expected_contains']
        response = agent_function(prompt)
        score = score_response(response, expected_contains)
        results.append({
            'prompt': prompt,
            'expected_contains': expected_contains,
            'response': response,
            'score': score
        })

    return results

# Example usage:
# def dummy_agent(prompt):
#     return "This is a dummy response."
#
# if __name__ == '__main__':
#     test_results = run_tests(dummy_agent)
#     for result in test_results:
#         print(f"Prompt: {result['prompt']}")
#         print(f"Score: {result['score']}")
#         print("-" * 50)
