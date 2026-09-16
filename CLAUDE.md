# Working on this repository

The repository-wide rules live in [`.github/copilot-instructions.md`](.github/copilot-instructions.md)
— one file, read by GitHub Copilot and intended for any assistant or contributor.

They are not style preferences. Each one exists because the plausible-looking code is
wrong in a way that is hard to detect afterwards: an `english` full-text index that
retrieves the opposite of what was asked, a provider call that discloses a confidential
document, a chunk that loses the page its citation points to.

Read them before changing anything. The reasoning behind each is in `docs/ARCHITECTURE.md`.
