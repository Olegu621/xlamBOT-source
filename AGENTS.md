# xlamBOT development

- This private repository owns Python sources. Public distribution: Olegu621/xlamBOT.
- Use branches and PRs for collaborative changes; merge sources before publishing.
- Publish script updates only through `tools/publish.py`. It pushes sources and a revision tag before reporting success. Never bypass failed source synchronization or reuse a revision.
- Preserve source provenance alongside publisher artifacts. Keep only the installer in public GitHub Releases.
- Never commit signing keys, real login/webhook credentials, device profiles, match history or training recordings.
- Source code for current revision 24 is pinned by `bot-revision-24`; verify its compiled file hashes against `revision-24.json` when checking correspondence.
