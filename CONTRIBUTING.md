# Contributing

Thanks for helping improve **Awesome Bangladeshi FOSS**.

Please review the [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## How to propose a project

You can contribute in two ways:

1. Open a **Submit a New Project** issue using the issue template and complete all required fields.
2. Or fork this repository, create a branch, add your project to the most relevant section in `README.md`, and open a pull request.

If you use the issue template, automation validates your submission, creates a PR, and enables auto-merge after required checks pass.

## Entry requirements

- Add only genuine free and open source software/projects (OSI-approved license or equivalent).
- The submitted project must have at least 10 stars.
- Keep items in **alphabetical order** within each section (for PRs).
- Use this exact format:

```md
- [Name](link) - Short and meaningful description.
```

- Keep descriptions concise and value-focused.
- Avoid duplicate entries.
- Links must point to GitHub repository URLs in this format: `https://github.com/owner/repo`.
- Project Submission Issues must include all required information.
- Pull requests must pass all GitHub Actions checks (`lint` and `validate-readme`).
- Valid and eligible Submission Issues and non-draft pull requests are auto-merged after repository rules and required checks are satisfied.

## Local setup

- In VS Code, the Python extension discovers the pytest suite automatically from the `tests/` folder.
- To enable the repository pre-commit hook in this clone, run `git config core.hooksPath .githooks` once.
