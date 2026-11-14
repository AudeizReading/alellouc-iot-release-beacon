# Publishing Release Beacon

The [Docker workflow](workflows/docker-publish.yaml) belongs to the standalone
application repository. After a subtree export, `.github/`, `Dockerfile`, and
`app/` must be at that repository's root. The workflow does not require the
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

The workflow uses the automatic `GITHUB_TOKEN` to attach the digest file to
the release. Its job requests `contents: write` for that operation and
`id-token: write` for Cosign. No additional GitHub token is required.
GitHub creates this temporary, repository-scoped token for each job and
exposes it through `secrets.GITHUB_TOKEN` and `github.token`; it is not a
secret you must add in Settings. It expires after the job. The OIDC identity
used by Cosign is separate from this GitHub API token.

This workflow only handles `release.published`. Its steps do not need
`event_name != 'pull_request'` conditions, and image publication uses
`push: true`. The job has a ten-minute timeout. The separate PR workflow
checks Python without Docker; see [CI.md](CI.md) for time estimates and
branch protection setup.

## Publish a version

1. Commit and push the application and workflow changes to the standalone
   repository, following its normal review process.
2. Check `project.version` in `app/pyproject.toml`. The release tag must match
   that value exactly, including any leading `v`.
3. In GitHub, open **Releases → Draft a new release**. Select an existing tag
   or create one on the commit to publish. Add release notes and select
   **Publish release**.
4. Follow the Docker job in **Actions**. It checks out the release tag,
   validates the application metadata, publishes the image, signs its digest,
   and attaches the digest file to that same release.

A pull request or tag push alone does not trigger this workflow. The trigger
is `release.published`. The image name comes from `project.name`; its Docker
tag comes from the validated application version. The registry and namespace
come from the repository variables above.

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

- Invalid image metadata, a mismatched release tag, or an invalid build digest
  stops the job. An empty digest file is not published as a successful result.
- A signing failure prevents the digest asset steps from running. The image
  may already have been pushed; release publication alone does not prove the
  job succeeded.
- Upload failures fail the job. An asset with the same filename causes an
  HTTP 422 error; the workflow does not delete or replace existing assets.
- Rerunning the entire job rebuilds and republishes the image before the
  asset upload. A rebuild can change the digest even for the same source
  commit. An existing asset is not updated by such a rerun. Prefer a new
  version and release for a new publication.

To revert this asset integration, remove the two steps after Cosign and
restore the job's `contents` permission to `read`. This does not delete any
image, signature, or release asset already published.

Local validation can check YAML, the embedded scripts, the generated file,
and the HTTP request with a mocked transport. It does not establish that
Docker Hub authentication, image publication, Cosign, or release uploads have
succeeded on GitHub; those require an actual successful workflow run.
