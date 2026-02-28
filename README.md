# AI CPO Agent

This repository contains the source code, prompt architecture, and documentation for an AI‑powered Chief Product Officer (CPO) built for founders of SaaS businesses.

## Purpose

The AI CPO acts as an always‑available executive that translates founder vision into structured product strategy. It owns the product roadmap, writes documentation, prioritizes features, monitors key metrics, and ensures execution discipline so founders can focus on vision and growth.

### Key capabilities

- Define the ideal customer profile (ICP) and articulate the value proposition.
- Capture product‑market‑fit signals and use them to inform roadmaps.
- Generate Product Requirement Documents (PRDs), feature specifications, user stories, technical handoff docs, release notes, and strategy memos.
- Build quarterly roadmaps and break them into sprints with clear prioritization using frameworks like RICE/ICE.
- Analyse activation, retention, churn and revenue data to drive decisions.
- Challenge vague ideas and prevent "shiny object syndrome" by demanding clarity and metrics.

## Repository structure

```
├── README.md               # you are here
├── LICENSE                 # choose an appropriate license (e.g. MIT)
├── .env.example            # example environment variables
├── app/
│   ├── main.py             # API entrypoint / server
│   ├── cpo_agent.py        # agent orchestration logic
│   └── tools.py            # definitions of additional tools/capabilities
├── prompts/
│   ├── system.md           # AI identity and system instructions
│   ├── policies.md         # tone, style, and operational constraints
│   └── workflows/
│       ├── prd.md          # Product Requirements Document template
│       ├── roadmap.md       # Roadmap generation workflow
│       └── sprint_planning.md  # Sprint planning workflow
├── schemas/
│   ├── prd.schema.json     # JSON schema for PRD outputs
│   ├── roadmap.schema.json # JSON schema for roadmap outputs
│   └── sprint.schema.json  # JSON schema for sprint plans
├── memory/
│   ├── product_brief.md    # current SaaS product information
│   └── decisions.md        # decision log for transparency
├── evals/
│   ├── test_cases.json     # test cases to validate agent outputs
│   └── score.py            # simple evaluator script
├── docs/
│   ├── api.md              # API endpoints documentation
│   └── runbook.md          # operational runbook for founders
└── .github/
    └── workflows/
        └── ci.yml          # CI configuration to lint, test and run evals
```

## Getting started

1. Clone the repository and install dependencies.
2. Create a `.env` file based on `.env.example` and add your API keys (e.g. OpenAI).
3. Run `python app/main.py` to start the API or CLI.
4. Review the prompts in the `prompts/` directory and update `memory/product_brief.md` to reflect your own SaaS product details.

## Contributing

Contributions are welcome! Please open issues or pull requests for improvements or bug fixes. See `docs/api.md` and `docs/runbook.md` for more details on how to extend the agent.
