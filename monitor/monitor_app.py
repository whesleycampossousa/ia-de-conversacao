"""
Monitor Application - Main Orchestrator
Runs all test suites against configured environments
"""
import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor.utils.logger import get_logger
from monitor.utils.api_client import APIClient
from monitor.utils.validators import Validators
from monitor.utils.auto_fix import AutoFix
from monitor.suites.test_suite_endpoints import EndpointTestSuite


class MonitorApp:
    """Main monitoring application"""

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = Path(__file__).parent / "config"
        else:
            config_dir = Path(config_dir)

        self.config_dir = config_dir
        self.run_id = f"mon_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.report_dir = Path(__file__).parent / "reports" / self.run_id

        # Load configurations
        self.deployment_urls = self._load_json(config_dir / "deployment_urls.json")
        self.monitor_config = self._load_json(config_dir / "monitor_config.json")

        # Setup logger
        self.logger = get_logger("monitor", config=self.monitor_config.get('logging', {}))
        self.logger.info(f"Monitor started with run_id: {self.run_id}")

        # Prepare report directory
        self.report_dir.mkdir(parents=True, exist_ok=True)

        self.all_results = []

    def _load_json(self, filepath: Path) -> Dict:
        """Load JSON config file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            sys.exit(1)

    def _get_password(self) -> str:
        """Get password from environment variable (optional)."""
        password_env = self.deployment_urls.get('auth', {}).get('password_env', 'MONITOR_PASSWORD')
        password = os.getenv(password_env)

        if not password:
            # Fallback: use admin password from .env if available
            password = os.getenv('ADMIN_PASSWORD')

        if not password:
            self.logger.warning(
                f"No password found in env vars ({password_env}/ADMIN_PASSWORD); "
                "monitor will try login without password"
            )
            return ""

        return password

    def test_environment(self, env_config: Dict) -> Dict[str, Any]:
        """Test a single environment"""
        env_name = env_config['name']
        env_url = env_config['url']

        self.logger.info(f"Testing environment: {env_name} ({env_url})")

        if not env_config.get('enabled', True):
            self.logger.info(f"Environment {env_name} is disabled, skipping")
            return {
                "environment": env_name,
                "url": env_url,
                "skipped": True,
                "reason": "disabled"
            }

        # Check if URL is placeholder
        if "PREENCHER" in env_url.upper():
            self.logger.warning(f"Environment {env_name} has placeholder URL, skipping")
            return {
                "environment": env_name,
                "url": env_url,
                "skipped": True,
                "reason": "placeholder_url"
            }

        try:
            # Get credentials
            email = self.deployment_urls.get('auth', {}).get('email')
            password = self._get_password()

            # Create API client
            api_client = APIClient(
                base_url=env_url,
                email=email,
                password=password,
                timeout=self.monitor_config.get('timeouts', {}).get('default_request_timeout', 30),
                logger=self.logger
            )

            # Authenticate
            if not api_client.login():
                return {
                    "environment": env_name,
                    "url": env_url,
                    "error": "Authentication failed",
                    "critical": True
                }

            # Setup dependencies
            validators = Validators()
            auto_fix = AutoFix(
                api_client=api_client,
                logger=self.logger,
                config=self.monitor_config.get('auto_fix', {})
            )

            # Run test suites
            suite_results = []

            # Level 1: Endpoints (always run)
            if self.monitor_config.get('test_selection', {}).get('level1_endpoints', True):
                endpoint_suite = EndpointTestSuite(
                    api_client=api_client,
                    logger=self.logger,
                    validators=validators,
                    auto_fix=auto_fix,
                    config=self.monitor_config.get('thresholds', {})
                )
                endpoint_result = endpoint_suite.run()
                suite_results.append(endpoint_result)

            # TODO: Add other test suites (scenarios, grammar, audio, e2e)
            # For now, endpoint testing is the core functionality

            # Aggregate results
            total_tests = sum(r.get('total_tests', 0) for r in suite_results)
            total_passed = sum(r.get('passed', 0) for r in suite_results)
            total_failed = sum(r.get('failed', 0) for r in suite_results)

            pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

            result = {
                "environment": env_name,
                "url": env_url,
                "priority": env_config.get('priority', 'medium'),
                "total_tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "pass_rate": pass_rate,
                "suites": suite_results,
                "status": "PASS" if total_failed == 0 else "FAIL"
            }

            return result

        except Exception as e:
            self.logger.error(f"Error testing environment {env_name}: {e}")
            return {
                "environment": env_name,
                "url": env_url,
                "error": str(e),
                "critical": True
            }

    def run(self, environments: List[str] = None) -> int:
        """
        Run monitoring for specified environments
        Returns exit code: 0=success, 1=warnings, 2=critical
        """
        start_time = time.time()

        # Get environments to test
        all_envs = self.deployment_urls.get('environments', [])

        if environments:
            # Filter to specified environments
            envs_to_test = [e for e in all_envs if e['name'] in environments]
        else:
            # Test all enabled environments
            envs_to_test = [e for e in all_envs if e.get('enabled', True)]

        self.logger.info(f"Testing {len(envs_to_test)} environments")

        # Test each environment
        for env_config in envs_to_test:
            result = self.test_environment(env_config)
            self.all_results.append(result)

        # Generate summary
        duration = time.time() - start_time

        total_tests = sum(r.get('total_tests', 0) for r in self.all_results)
        total_passed = sum(r.get('passed', 0) for r in self.all_results)
        total_failed = sum(r.get('failed', 0) for r in self.all_results)
        pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

        critical_failures = [r for r in self.all_results if r.get('critical', False)]
        warnings = [r for r in self.all_results if r.get('status') == 'FAIL' and not r.get('critical', False)]

        summary = {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "duration_minutes": round(duration / 60, 2),
            "environments_tested": [r['environment'] for r in self.all_results if not r.get('skipped')],
            "environments_skipped": [r['environment'] for r in self.all_results if r.get('skipped')],
            "summary": {
                "total_tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "pass_rate": round(pass_rate, 1)
            },
            "by_environment": {
                r['environment']: {
                    "passed": r.get('passed', 0),
                    "failed": r.get('failed', 0),
                    "pass_rate": round(r.get('pass_rate', 0), 1)
                }
                for r in self.all_results if not r.get('skipped')
            },
            "failures": [
                {
                    "environment": r['environment'],
                    "error": r.get('error', 'Unknown error'),
                    "critical": r.get('critical', False)
                }
                for r in self.all_results if r.get('error') or r.get('status') == 'FAIL'
            ],
            "health_status": "HEALTHY" if not critical_failures and not warnings else
                            "DEGRADED" if warnings and not critical_failures else "CRITICAL"
        }

        # Save summary to file
        summary_file = self.report_dir / "summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        # Create "latest" symlink
        latest_link = self.report_dir.parent / "latest"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        try:
            latest_link.symlink_to(self.report_dir.name, target_is_directory=True)
        except Exception:
            pass  # Symlinks might not work on all Windows systems

        # Log summary
        self.logger.info(f"Monitoring completed: {summary['health_status']}")
        self.logger.info(f"Results: {total_passed}/{total_tests} passed ({pass_rate:.1f}%)")
        self.logger.info(f"Report saved to: {summary_file}")

        # Determine exit code
        if critical_failures:
            return 2  # Critical
        elif warnings or total_failed > 0:
            return 1  # Warnings
        else:
            return 0  # Success


def main():
    parser = argparse.ArgumentParser(description="Monitor IA de Conversação deployments")
    parser.add_argument('--env', type=str, help="Test specific environment (e.g., production)")
    parser.add_argument('--all-envs', action='store_true', help="Test all enabled environments")
    parser.add_argument('--dry-run', action='store_true', help="Dry run (doesn't make changes)")

    args = parser.parse_args()

    app = MonitorApp()

    if args.env:
        exit_code = app.run(environments=[args.env])
    else:
        exit_code = app.run()

    # Open HTML report if critical failure
    if exit_code == 2 and app.monitor_config.get('notifications', {}).get('open_html_on_critical', True):
        html_report = app.report_dir / "summary.html"
        if html_report.exists():
            os.startfile(str(html_report))  # Windows only

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
