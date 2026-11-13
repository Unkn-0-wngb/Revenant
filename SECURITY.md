# Security

Revenant never plays online and doesn't take any accounts or passwords, but it does run local code and talks to the game over a local port, so security reports are welcome.

## Reporting a problem

Please don't open a public issue for a security problem. Use GitHub's private reporting instead:

1. Go to the **Security** tab of this repo.
2. Press **Report a vulnerability**.

I'll reply as soon as I can and keep you updated until it's fixed.

## What's in scope

- The dashboard and the scripts in this repo
- The website in `site/`
- Anything that could run code or leak files on someone's PC

Problems in Trackmania, TMLoader, TMInterface or Linesight themselves should go to their own projects.

## Antivirus warnings

TMLoader injects into the game, so some antivirus programs flag it. That's a known false positive and not a security report.
