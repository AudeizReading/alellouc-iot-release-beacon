# Publishing Release Beacon

The [publication workflow](workflows/release-publish.yaml), displayed as
**Publish image and immutable GitHub release**, belongs to the standalone
application repository. After a subtree export, `.github/` (including its
`scripts/` directory), `Dockerfile`, and `app/` must be at that repository's root.
The workflow does not require the
parent repository, Mise, Ansible, or the GitHub CLI.

## Repository setup

In the application repository, open **Settings → Secrets and variables →
Actions**. Create these repository variables under **Variables**:

| Name | Purpose |
| --- | --- |
| `DOCKERHUB_REGISTRY` | Docker registry host, `docker.io` for Docker Hub. |
| `DOCKERHUB_GROUP` | Docker Hub namespace that owns the image repository. |
| `DOCKERHUB_LOGIN` | Docker Hub account allowed to publish to that namespace. |

Under **Secrets**, create `DOCKERHUB_TOKEN` using a Docker Hub personal access
token with read and write permissions. These values are configured once and
are reused for subsequent releases; local Mise variables are not imported.

The workflow uses the automatic `GITHUB_TOKEN` to create a draft release,
attach its digest file, and publish it. Its job requests `contents: write` for those operations and
`id-token: write` for Cosign. No additional GitHub token is required.
GitHub creates this temporary, repository-scoped token for each job and
exposes it through `secrets.GITHUB_TOKEN` and `github.token`; it is not a
secret you must add in Settings. It expires after the job. The OIDC identity
used by Cosign is separate from this GitHub API token.

This workflow only handles pushes of Git tags matching `publish/**`. Its steps do not need
`event_name != 'pull_request'` conditions, and image publication uses
`push: true`. It first calls the PR workflow's native Python checks for the
exact commit to publish. The build job depends on their success: failed or
skipped checks prevent Docker login, build, and release creation. Validation
has a five-minute timeout; the subsequent build job has a ten-minute timeout.
See [CI.md](CI.md) for time estimates and branch protection setup.

## Publish a version

1. Commit and push the application and workflow changes to the standalone
   repository, following its normal review process.
2. Check `project.version` in `app/pyproject.toml`: `v1` produces Docker tag
   `v1`; `v2` produces Docker tag `v2`. No version is entered in Actions.
3. Push a dedicated publication tag, for example `publish/v2-1`, pointing to
   the application commit to publish. That commit must already belong to the
   default branch history and contain this workflow and its companion files.
   The commands below describe standalone and parent checkouts separately.
4. Follow the jobs in **Actions**. Native Python checks run first against the
   selected commit. Only on success does the build job check out that same
   commit, validate metadata, and log into Docker Hub before preparing tools.
   It builds and pushes the multi-platform image, signs its digest, and
   writes the digest file. It then creates a draft release, attaches the
   file, and publishes the stable release explicitly as **Latest**.

A PR, branch push, unrelated tag push, or manually published release does not
trigger this workflow. A CI-only update therefore does not publish an image
unless a publication tag is explicitly pushed for it. No release needs to be
created in the GitHub interface. The image name comes from `project.name`;
its Docker tag comes from the validated application version. The registry
and namespace come from the repository variables above.

From a standalone application clone, with `HEAD` on the intended commit that
has already been merged into the default branch:

```bash
git tag publish/v2-1 HEAD
git push origin refs/tags/publish/v2-1
```

From the parent `alellouc-iot` checkout, target the application remote's
commit rather than the parent commit. After the subtree changes have reached
the standalone repository's `main`:

```bash
git fetch rb-app
git tag publish/v2-1 rb-app/main
git push rb-app refs/tags/publish/v2-1
```

These commands create a local tag and push it to the selected remote, starting
publication. `publish/v2-1` is an example publication request name; the Docker
version still comes exclusively from `app/pyproject.toml`. Use a fresh request
tag, such as `publish/v2-2`, for another publication. Do not move or force-push
an existing request tag.

Publication reuses [`workflows/pr-checks.yaml`](workflows/pr-checks.yaml)
through `workflow_call`; it does not rely on an older PR status, whose merge
commit may differ from the selected publication commit. No Docker Hub secret
is passed to validation. A branch ruleset must separately require PR checks
before merging; local workflow changes do not activate that GitHub setting.

### Docker tags and immutable GitHub releases

The Docker tag and release title remain the application version, for example
`v2`. The Git tag is generated independently as
`<name>/<version>/build-<github-run-id>-<attempt>`, for example
`release-beacon/v2/build-123456-1`. It points to the exact checked-out commit.
Each attempt gets a new Git tag, including reruns of a failed job.
The triggering tag (`publish/v2-1`) remains a separate publication request.
The generated release tag does not match `publish/**` and cannot start another
publication. Keeping those identities separate permits a failed run to be
retried without reusing an immutable release tag.

GitHub permanently reserves the tag name of a deleted immutable release.
This workflow cannot make a reserved Git tag such as `v2` reusable. It uses a
new Git tag while preserving the required Docker `:v2` tag and GitHub release
title `v2`. A later application version of `v1` similarly produces Docker `:v1`.
Multiple GitHub releases can share a title; their Git tags remain distinct.

The final API request sets `draft: false`, `prerelease: false`, and
`make_latest: "true"`. Every successful publication is promoted as the latest
stable GitHub release, including a later republication of `v1` after `v2`.
This does not add a Docker `latest` tag; Docker tags remain versioned.

Immutable releases reject asset changes after publication. The workflow
therefore uploads the digest while the release is still a draft and publishes
only after the upload succeeds. The standard-library API client in
[`scripts/github_releases.py`](scripts/github_releases.py) owns draft creation,
asset upload, and publication. No GitHub CLI or additional dependency is used.

See [GitHub's immutable release documentation](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).

## Multi-platform build

The build explicitly requests `linux/amd64,linux/arm64`, matching the Ansible
role's default platforms. Buildx alone does not select multiple platforms.
The workflow registers QEMU for ARM64 before creating the `docker-container`
builder, so the AMD64 GitHub runner can execute the Dockerfile's ARM64 RUN
instructions. Both platform images are pushed under the same version tag.

The returned digest identifies the multi-platform image index. Cosign signs
that index digest, and the release file records it. Pulling the pinned index
lets the runtime select the image for its platform; it does not pin only the
AMD64 image. The build settings match the Ansible platform targets, but build
cache, labels, and signing remain workflow-specific. The same source commit
does not promise identical image bytes across separate builds.

## Digest asset

A successful job adds `<name>-<version>.release.yaml` under the release's
**Assets**, for example `release-beacon-v2.release.yaml`. Its format preserves
the existing `docker_image` field:

```yaml
docker_image: "docker.io/<namespace>/<name>:<version>@sha256:<published-digest>"
```

The reference uses the tag produced by the metadata action and the digest
returned by the build action, which is also passed to Cosign. After signing,
the workflow writes the file under the application's existing directory:

```text
img/release/digest/<name>-<version>.release.yaml
```

For example, `img/release/digest/release-beacon-v2.release.yaml` is generated
inside the runner's checkout and uploaded through the release's GitHub API
upload URL. In the parent repository this directory is
`release-beacon/img/release/digest/`; the subtree export removes the leading
`release-beacon/` prefix.

The runner's checkout is temporary. Durable retention is the release asset,
whose filename is flat: GitHub release assets do not preserve directory
paths. No commit is created or pushed: this directory is used in the CI
working copy, and the workflow does not publish changes to Git history.

Download the asset and use its `docker_image` value as the workload's `image`
in the GitOps repository. That manifest change is a separate deployment
decision; this workflow does not edit or deploy it.

## Failure and recovery

- Invalid image metadata, an invalid generated Git tag, or an invalid build digest
  stops the job. An empty digest file is not published as a successful result.
- A Docker Hub login failure stops the job before draft creation and build
  setup. A malformed authorization error still requires correcting the
  Docker Hub account/token in repository settings; release naming cannot fix it.
- Failed Python checks prevent the build job from starting. Build, signing,
  and digest-file failures happen before draft creation, so they create no
  GitHub release. The image may already have been pushed when signing or
  digest generation fails.
- A tagged commit outside the default branch history fails validation before
  dependency installation or Docker authentication. Validation fetches full
  history only for publication calls and checks Git ancestry explicitly.
- Upload failures fail the job. An asset with the same filename causes an
  HTTP 422 error. The draft is retained for inspection; the workflow never
  deletes or replaces releases or assets automatically.
- Rerunning publication validates the selected commit again before rebuilding
  and republishing the same Docker version tag, then creates a fresh draft
  with a new Git tag. A rebuild can change the digest
  even for the same source commit; consumers pinned to the previous digest
  keep that image. Docker Hub must allow updates to that Docker tag. GitHub
  release immutability and registry tag immutability are separate controls.
- A publication failure fails the job after upload. Inspect the draft and
  job logs before rerunning. Old drafts remain separate from the new attempt.
- Concurrent publication runs are serialized. GitHub may replace an older
  pending run with a newer one; this is not an unlimited release queue.
  The reusable validation workflow has a distinct concurrency group and
  cancels superseded runs only for PR events. It cannot cancel its publication
  caller or allow the build to run before validation succeeds.

To revert this change, revert the publication workflow and its accompanying
scripts together, and remove their test invocation from the PR workflow.
This does not delete any image, signature, draft, Git tag, or release asset
already published. Restoring post-publication asset uploads would again be
incompatible with immutable releases.

Local validation can check YAML, the embedded scripts, the generated file,
and the HTTP request with a mocked transport. It does not establish that
Docker Hub authentication, image publication, Cosign, or release uploads have
succeeded on GitHub; those require an actual successful workflow run.
From the standalone repository root, run the API tests without network access:

```bash
cd app
uv run --no-sync python -B -m unittest discover -s ../.github/scripts -p 'test_*.py' -v
```

This command assumes the application environment has already been installed
with `uv sync --no-dev`. The PR workflow runs the same tests automatically.
