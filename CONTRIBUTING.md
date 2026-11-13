# Contributing

Thanks for taking a look. Bug reports, ideas and pull requests are all welcome.

## Before you start

- Check the [troubleshooting guide](docs/TROUBLESHOOTING.md), most problems I ran into are in there.
- Search the existing issues and discussions in case it's already been covered.
- For anything big, open an issue or discussion first so we don't both build the same thing.

## Reporting a bug

Use the bug report form. The most useful things to include are:

- Your GPU, CPU and RAM (the Machine tab shows these)
- What the Setup tab says
- The last few lines of the training log

## Running it from source

Revenant targets Windows 10 and 11 because Trackmania Nations Forever and TMLoader are Windows only.

1. Clone the repo.
2. Double-click `Revenant.bat`, or run `setup.ps1` for the one-off install.
3. Python 3.11 with the pinned PyTorch in `constraints.txt`.

The website in `site/` is plain Node: `cd site && npm install && npm run build`.

## Pull requests

- Keep each pull request to one change.
- Match the style of the code around it.
- Don't commit trained models, logs or anything in `.gitignore`. Trained brains go on the Releases page.
- Describe what you changed and how you tested it.

By contributing you agree your work is released under the MIT licence.
