# Deploy Script Design

## Goal

Add a root-level `deploy.sh` that updates and restarts the Vibe Research backend and frontend in one command. The backend listens on port 8900 and the frontend listens on port 5899.

## Deployment flow

1. Resolve the project root from the script location and enable strict Bash error handling.
2. Restore the tracked `deploy.sh`, then pull the latest code from `origin/main`.
3. Ensure the backend virtual environment exists and install `backend/requirements.txt`.
4. Install frontend dependencies from `frontend/package.json` and its lockfile.
5. Stop the previously launched backend and frontend using PID files when available, then stop any remaining process occupying ports 8900 or 5899. Prefer graceful termination and use forced termination only after a timeout.
6. Start both services with `nohup`:
   - Backend: Uvicorn on `0.0.0.0:8900`.
   - Frontend: Vite on `0.0.0.0:5899`.
7. Store PID files and write separate logs to `backend/nohup.out` and `frontend/nohup.out`.
8. Verify the backend health endpoint and both listening ports. On failure, print the relevant log tail and return a nonzero status. On success, print process IDs, addresses, and recent logs.

## Safety and failure behavior

- Quote all paths and derive them without assuming the caller's working directory.
- Do not overwrite or clean unrelated working-tree changes.
- Abort when code pull or dependency installation fails.
- Avoid broad process-name termination. PID files and exact port ownership are the primary stop mechanisms.
- Validate discovered PIDs before sending signals.
- Keep output concise and label backend and frontend actions separately.

## Dependencies and assumptions

- The deployment host provides Bash, Git, Python 3, npm, `curl`, and either `lsof` or `ss` for port checks.
- The repository remote is `origin`, and the deployment branch is `main`.
- The frontend is intentionally run with the Vite development server, matching the current project documentation and requested port.
- Both services bind to all interfaces so they can be reached outside the host when firewall rules allow it.

## Verification

- Run `bash -n deploy.sh` for syntax validation.
- Run shell linting if ShellCheck is installed.
- Exercise safe helper behavior where possible without pulling code or replacing currently running services.
- Confirm the final commands match the project README and configuration.
