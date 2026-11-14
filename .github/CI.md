# Pull request validation

The [PR validation workflow](workflows/pr-checks.yaml) belongs to the standalone
application repository. On PRs, it runs when the base branch starts with
`main` or equals the repository's current default branch, subject to its path
filters. It also supports `workflow_call` so publication can reuse the same
checks before building an image. No Docker Hub credentials or release are
needed for validation.

## Checks performed

On PRs, the workflow checks out GitHub's proposed merge commit. When called by
publication, it checks out the publication run's exact `github.sha` instead.

Publication calls set `require_default_branch: true`. Their checkout fetches
full history and first runs `git merge-base --is-ancestor` against the fetched
default branch. A commit outside that history fails before dependency setup.
Ordinary PR runs keep a shallow checkout and do not perform this ancestry check.

After checkout and any required ancestry check, validation:

1. Sets up uv and selects Python 3.14, matching the Dockerfile's Python series.
2. Runs `uv sync --no-dev` from `app/`, as in the Dockerfile. There is no
   additional test dependency and no Docker invocation in this workflow.
3. Compiles the Python source using the installed application environment.
4. Executes `tests/run_checks.py` using that same environment. The runner
   starts `python -m server.app` with test-only settings on an available local
   port, then runs the standard-library `unittest` suite. An empty suite fails.
   Tests cover configuration validation, content negotiation, request
   rejection, template rendering, and live HTML, JSON, CSS, and HEAD responses.
   The server may take up to ten seconds to start listening; unsuccessful
   startup or an unexpected process exit fails the checks.
5. Prints the server's logs and stops its process, including when tests fail.
   Cleanup first requests termination, then kills a process that does not stop
   within five seconds.
6. Tests the release API client with a mocked HTTP transport. These tests
   verify draft creation, digest upload before publication, response validation,
   and failure propagation, without Docker, credentials, or network calls.

The installation and application entry point follow the Dockerfile, but this
workflow validates Python on the runner rather than building a container.
The Dockerfile, its base images, COPY instructions, and UID 10001 are not
validated by this PR job. Building and publishing the image remain part of
the separate release workflow. There is no separate package build because
this application declares `package = false`. Dependency resolution is not
frozen, matching the current Dockerfile's installation command.

There is no configured linter or type checker in this application. The syntax
check is not presented as linting. These tests do not prove accessibility,
multi-architecture compatibility, or conformance to the architecture policy;
those require their respective checks or review.

The publication workflow runs this validation as a prerequisite job and its
build job declares `needs: checks`. Failed or skipped validation prevents the
build job from running. Publication is allowed only for commits already in
the default branch history;
its checkout uses the same commit as validation. PR branch and path filters
do not suppress validation for an authorized publication run.

## Make failures block merges

A failing workflow alone does not enforce branch protection. After the
workflow has run on a PR:

1. Open the standalone repository's **Settings → Rules → Rulesets** and
   create or edit an active branch ruleset.
2. Target the default branch and `main` if it is a different branch.
3. Enable **Require a pull request before merging** and **Require status
   checks to pass**. Select the check named **PR checks** from this workflow.
4. Require the branch to be up to date before merging if that is the chosen
   integration policy. Avoid bypass permissions for actors that must remain
   subject to these checks.

The workflow uses only `contents: read` and never uses `pull_request_target`.
PR path filters cover `app/**`, `tests/**`, `.github/scripts/**`, and both
workflow files. A PR changing only other paths does not start the workflow;
a required check may then remain pending and block merging. Non-target
branches skip the job. The ruleset and these filters must agree with the
desired merge policy. Ruleset availability depends on the repository's GitHub plan
and visibility; classic branch protection can require the same status check
where available. These server-side settings are not activated by adding the
workflow file.

## Local commands

From the standalone application's root:

```bash
cd app
uv sync --no-dev
uv run --no-sync python -m compileall -q server
uv run --no-sync python -B ../tests/run_checks.py
uv run --no-sync python -B -m unittest discover -s ../.github/scripts -p 'test_*.py' -v
```

The test runner supplies its own settings and uses an available loopback
port. It does not reuse a running application or require a fixed port.

## Execution time and cost

PR validation uses one standard Ubuntu job. Publication uses two sequential
Ubuntu jobs: the reusable native Python validation, then build and publication.
There is no job matrix. The release build targets AMD64 and ARM64 together
using Buildx and QEMU. Validation has a five-minute timeout; build and
publication have a ten-minute timeout. A successful publication therefore
includes both jobs, with up to fifteen runner minutes before rounding and
execution overhead. These limits are per invocation, not monthly spending caps.

PR validation cancels superseded runs of the same PR to save time. Publication
runs are serialized and an active publication is not cancelled by a new one.
Called validation uses a separate concurrency group, with cancellation disabled
for publication calls, so it cannot cancel its parent workflow.

With the current dependency-free application, budget roughly 1–2 runner
minutes per validation execution and 5–10 per multi-platform release build,
push, signing, and digest upload. A complete publication therefore budgets
roughly 6–12 runner minutes, including its prerequisite validation. These are
planning estimates, not measured workflow durations;
downloads, ARM64 emulation, registry latency, and build cache misses can
increase them. A release exceeding ten minutes fails at the existing timeout;
it is not guaranteed to finish within this estimate. Each
push to an open PR triggers another check execution. Editing or reopening a
PR can also trigger checks when its path filters match. The release job runs
only after a tag matching `publish/**` is pushed and creates the release itself;
see [RELEASES.md](RELEASES.md). Branch pushes, including CI-only merges, do not
publish images. It does not run on PRs or release publication.

For example, ten PR check executions and one complete publication would be
approximately 16–32 runner minutes. GitHub rounds each job's duration up to a whole minute.
Standard runners are free for public repositories. For private repositories,
usage draws from the owner's included allowance and may be billed beyond it.
The repository's visibility, plan, remaining allowance, and actual run times
have not been inspected. Consult the account's billing controls for a spending
limit; a workflow timeout alone is not such a limit.

References: [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
and [runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing).

To remove this validation, remove its required check from the branch ruleset
before deleting the workflow. Otherwise GitHub may keep waiting for a check
that no longer exists. The publication workflow is a separate file.
