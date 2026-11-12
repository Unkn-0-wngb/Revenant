# Troubleshooting

Start with the dashboard's **Setup** tab. Most problems show up there as an amber ! with a button next to it.

## Starting up

**Revenant.bat closes straight away or says setup failed.**
Run `setup.ps1` from PowerShell so you can read the error:
```
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```
The usual causes are no internet (it downloads about 3 GB) or winget missing on old Windows 10 installs. If winget is missing, install Python 3.11 from python.org yourself and run it again.

**The dashboard shows "hit an error and closed".**
The full error is in `logs/dashboard_error.log`. If it mentions a missing module, run `setup.ps1` again (Revenant.bat also does this by itself when a library is missing).

**"Python packages: missing ..." on the Setup tab.**
Press *Run setup*. If it keeps failing on `python-lzo`, make sure you're on 64-bit Python 3.11.

**"NVIDIA graphics card: the GPU can't run the AI".**
Update your NVIDIA driver (the button opens the download page). RTX 50 series cards aren't supported yet because the AI is pinned to PyTorch 2.5. AMD and Intel graphics can't run it.

## The game

**Setup can't find TrackMania Nations Forever.**
Install it from Steam (it's free). If it's somewhere unusual, open TMLoader once, point it at the game, then press *Check again*.

**TMLoader says "failed to find profile default".**
Press *Fix* next to *TMLoader profile with TMInterface* on the Setup tab. If it still happens, open TMLoader yourself, make a profile called `default`, and tick TMInterface.

**My antivirus deleted or blocked TMLoader.**
It injects into the game, which looks suspicious to antivirus programs, but it's a false positive. Add `%LocalAppData%\TMLoader` as an exception.

**The games open fullscreen.**
Run `TmForeverLauncher.exe` in the game folder once, choose windowed mode, and save.

**The games stay on "Select your Profile".**
The clicker presses the Revenant row for you, about 25 seconds after a game opens. If it doesn't:
- Check the Profile tab says *Now driving as: Revenant*.
- If you have lots of profiles, the list may scroll. Delete the ones you don't use from the game's profile screen.
- Look at `logs/auto_click.log`.

**The car isn't the Revenant car.**
Close the game, open the Profile tab and press *Make and use Revenant*. That reinstalls the skin and fixes its checksum in the profile.

## While training

**Training stops with "CUDA error: out of memory".**
Something else used the graphics memory, usually Discord Clips, the Xbox Game Bar, a browser with hardware acceleration, or a game. Close them and start again. If it keeps happening, lower the batch size or the number of games on the Machine tab.

**The dashboard says "Stalled".**
The training log hasn't changed for 10 minutes. Usually a game has frozen or is stuck on a dialog. Use *Stop now*, close any games still open, and start again. It carries on from the last save.

**The PC gets slow or runs out of RAM.**
Run the benchmark on the Machine tab and press *Use these settings*. Fewer games and a smaller replay memory help.

**It's stuck at the same point on a level for hours.**
That's what the lap follower and demo starts are for (Run tab):
1. Start the lap follower on that level and let it build a lap. Watch `logs/follow_<level>.log`.
2. When it has a lap (or runs out of time, it keeps the part it managed in `bruteforce/<level>_follow_partial.npy`), start demo starts on that level, with a step range that begins a bit before the hard part.
3. Set focus to that level so the loop stays there.

**I changed the memory size and the learner crashed.**
The replay memory can't shrink while training runs. The dashboard blocks that, but editing `config.py` by hand doesn't. Stop training, change it, then start again.

**Ports already in use.**
Something else is using 8478 to 8480. Press *Fix* next to *Network ports* and Revenant moves to free ones.

## Logs worth knowing about

| File | What's in it |
|---|---|
| `logs/train_run1.log` | everything the learner and collectors print, including level changes and errors |
| `logs/auto_click.log` | the profile clicker |
| `logs/follow_<level>.log` | the lap follower |
| `logs/bruteforce_<level>.log` | bruteforce |
| `logs/refeed_<level>.log` | demo starts |

The Run tab's *Open training log* button opens the main one.
