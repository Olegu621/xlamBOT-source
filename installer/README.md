# PC bootstrap installer

Installer 0.8.21 offers Russian and English. `/LANG=ru` and `/LANG=en` select
the language for unattended tests. Standard pages, custom progress, shortcuts
and recovery errors follow that language. Verify both languages with the isolated
installer and inspect welcome, progress and completion pages before publishing.

The small installer downloads the unchanged 0.8.18 runtime and a separately rebuilt
0.8.19 bootstrap ZIP (EXE plus matching static/templates) from immutable repository commits. Both downloads have SHA-256
checks embedded in the installer. The bootstrap descriptor is also Ed25519 signed.
Checks and extraction finish before the old installation is stopped or replaced.
Existing profiles, models and user data retain the established backup/restore flow.

Build the program with Python 3.13 using `tools/build_bootstrap.py`, test the new EXE
against the unchanged runtime, merge sources, publish scripts with `tools/publish.py`,
then generate the bootstrap descriptor using `tools/publish_bootstrap.py`.

Compile `web-installer.iss` using Inno Setup 6 with `/DPayloadHash`, `/DPayloadSize`,
`/DPayloadBase`, `/DPartsCount=7`, `/DBootstrapHash` and `/DBootstrapUrl`.
Read runtime hashes/sizes from its immutable `runtime.json`; bootstrap hashes come
from the verified signed descriptor. Do not use mutable branch URLs for downloads.

For isolated installation tests define `/DTestInstaller`, choose a new folder whose
last component is `xlamBOT`, and pass verified `/PAYLOAD` and `/BOOTSTRAP` caches.
Test a wrong bootstrap hash: setup must fail before replacing any installation.
Public releases contain only the installer; runtime, bootstrap and script payloads
remain in the distribution repository. APK/Mobile are outside this workflow.
