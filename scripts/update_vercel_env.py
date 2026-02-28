import os
import subprocess
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_env():
    if not load_dotenv:
        return
    load_dotenv(ROOT_DIR / ".env")


def run_command(command, inputs=None):
    """Runs a shell command with optional stdin inputs."""
    print(f"Running: {' '.join(command)}")
    try:
        result = subprocess.run(
            command,
            input=inputs.encode() if inputs else None,
            capture_output=True,
            shell=True,
        )
        return result
    except Exception as e:
        print(f"Error: {e}")
        return None


def main():
    """
    Updates Vercel Environment Variables using values from local `.env`.

    Usage:
      python scripts/update_vercel_env.py
      python scripts/update_vercel_env.py --all
      python scripts/update_vercel_env.py --target production

    Notes:
    - This script intentionally keeps secrets OUT of git.
    - It overwrites the variable value using `vercel env add --force`.
    """
    _load_env()

    update_all = "--all" in sys.argv
    target = "production"
    if "--target" in sys.argv:
        try:
            target = sys.argv[sys.argv.index("--target") + 1].strip()
        except Exception:
            print("[ERROR] Missing value for --target (production|preview|development).")
            return 2

    keys = ["GOOGLE_API_KEY"]
    if update_all:
        keys += [
            "QWEN_API_KEY",
            "QWEN_TTS_ENDPOINT",
            "QWEN_TTS_MODEL",
            "QWEN_TTS_CLONE_MODEL",
            "QWEN_TTS_VOICE",
            "QWEN_TTS_CLONE_VOICE",
            "QWEN_TTS_CLONE_PREFIX",
            "QWEN_TTS_TIMEOUT_SEC",
            "SESSION_SECRET",
            "GROQ_API_KEY",
            "ALLOWED_ORIGINS",
            "RATE_LIMIT_REQUESTS",
            "RATE_LIMIT_WINDOW",
            "CACHE_DIR",
            "GEMINI_MODEL_NAME",
            "GEMINI_THINKING_BUDGET",
            "ADMIN_EMAIL",
            "ADMIN_PASSWORD",
            "TEMP_GLOBAL_UNLOCK_ENABLED",
            "TEMP_GLOBAL_UNLOCK_UNTIL_UTC",
        ]

    env_vars = {}
    missing = []
    for key in keys:
        value = (os.environ.get(key) or "").strip()
        if value:
            env_vars[key] = value
        else:
            missing.append(key)

    if missing:
        print(f"[WARNING] Missing keys in .env (skipping): {', '.join(missing)}")

    if not env_vars:
        print("[ERROR] No variables to update. Check your `.env`.")
        return 1

    print(f"Updating {len(env_vars)} variable(s) in Vercel target={target} ...")

    for key, value in env_vars.items():
        # Remove first to avoid any interactive overwrite confirmations.
        run_command(["vercel", "env", "rm", key, target, "-y"])

        add_cmd = ["vercel", "env", "add", key, target, "--force"]
        # Vercel does not allow sensitive vars for development targets.
        if target != "development":
            add_cmd.append("--sensitive")

        res = run_command(add_cmd, inputs=f"{value}\n")
        if not res or res.returncode != 0:
            stdout = res.stdout.decode(errors="ignore") if res else ""
            stderr = res.stderr.decode(errors="ignore") if res else ""
            print(f"[ERROR] Failed to set {key}.")
            print(stdout)
            print(stderr)
            return 1

        print(f"[OK] {key} updated.")

    print("Done. Trigger a new deployment so Vercel picks up the new env values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
