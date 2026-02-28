# AI CPO Agent Runbook

This runbook describes how to set up, operate, and maintain the AI Chief Product Officer (CPO) agent.

## Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-org/ai-cpo-agent.git
   cd ai-cpo-agent
   ```

2. **Install dependencies**:
   Make sure you have Python 3.10+ installed. Then install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   Copy `.env.example` to `.env` and fill in your API keys and other configuration values.

4. **Run the service**:
   Start the agent locally:
   ```bash
   python app/main.py
   ```

## Updating Prompts

- Prompt files live in the `prompts/` directory. Edit the relevant markdown files to adjust the agent's behavior.
- After changing prompts, run the evaluation suite to ensure outputs still meet expectations:
  ```bash
  python evals/score.py
  ```

## Deployment

Deploy the service using your preferred platform (e.g. Docker, Render, Railway). A typical Docker workflow might look like:

```bash
# Build the image
docker build -t ai-cpo-agent .

# Run the container
docker run -p 8000:8000 --env-file .env ai-cpo-agent
```

Ensure that environment variables are provided in production.

## Monitoring

- Monitor logs for errors and performance metrics. Logging can be configured in `app/main.py`.
- Implement metrics collection (e.g. through Prometheus) if needed for production use.

## Troubleshooting

- **Agent does not start**: Verify Python version and that all dependencies are installed.
- **Invalid API key errors**: Ensure your API key is correctly set in the `.env` file.
- **Failed evaluations**: Update or fix prompts or code until tests in `evals/` pass.

For further assistance, refer to the project's README and documentation.
