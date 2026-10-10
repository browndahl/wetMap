# GitHub repository setup

The repository workflows cannot configure their own protection rules. Configure `main` in repository settings with:

- pull requests required, including one approving review and stale-review dismissal;
- required status checks: `web`, `worker`, `api`, and `containers` from `CI`;
- required conversation resolution and linear history;
- force-pushes and branch deletion disabled;
- production environment approval by a designated maintainer;
- secret scanning, push protection, Dependabot alerts, and private vulnerability reporting enabled.

Commits use Conventional Commits. After CI succeeds on `main`, `release.yml` calculates the next semantic version, creates a `v*` tag, generates release notes, and publishes a GitHub Release. The package workspace stays private, so no npm package is published.
