# 296 — Windows commit shell (no bash heredoc)

Version: **0.3.290** · Status: **locked**  
Amends [293](293-ship-preflight-checklist.md)

## Why

0.3.289 ship was smooth after the commit existed. Getting the commit in was not:

1. PowerShell `bash` is the WSL stub, not Git Bash.  
2. `bash -lc` plus a heredoc drops the message. `git commit` then opens an editor and fails (`EDITOR unset`).  
3. `git commit -m` / `-m` from PowerShell succeeded on the third try.

Cloud pair and APK already go through `scripts/ship_cloud_pair.ps1`, which pins `C:\Program Files\Git\bin\bash.exe`.

## Rules

1. On Windows, commit only with `scripts/git_commit.ps1 -Message "..." -Body "..."`.  
2. That script must not call `bash` and must not accept `<<`.  
3. Do not run bare `bash` from PowerShell for commit or ship.

## Non-goals

- Changing Cloud Run deploy behavior  
- Version bump  

## Acceptance

`tests/test_design_296_windows_commit_shell.py`
