import subprocess
import logging
import time

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def was_woken_by_automation() -> bool:
    """
    Detects if the current power session was triggered by a timer/scheduled task.
    Supports English and Portuguese Windows outputs for 'powercfg /lastwake'.
    """
    try:
        # Check last wake source
        res = subprocess.run(["powercfg", "/lastwake"], capture_output=True, text=True)
        output = res.stdout.lower()

        # Keywords for timer-based wakeups
        timer_keywords = [
            "timer",
            "temporizador",
            "agendada",
            "scheduled",
            "wake-up timer",
        ]

        if any(key in output for key in timer_keywords):
            logger.info("Detected wake source: Timer/Scheduled Task (Automation).")
            return True

        # Fallback: check event logs for more detail if needed
        # (Usually powercfg is enough for 'Timer' events)

        logger.info(
            "Wake source appears to be manual or peripheral (Mouse/Keyboard/Power Button)."
        )
        return False

    except Exception as e:
        logger.error(f"Error detecting wake source: {e}")
        # Default to False to avoid hibernating the user accidentally if we can't be sure
        return False


def hibernate_now():
    """Forces hibernation immediately."""
    logger.info(
        "🚀 Automation workflow finished. PC was woken up by timer. Returning to Hibernation in 10s..."
    )
    time.sleep(10)
    try:
        # rundll32 command for hibernation (Force=1, DisableWakeEvents=0)
        subprocess.run(
            ["rundll32.exe", "powrprof.dll", "SetSuspendState", "1", "1", "0"]
        )
    except Exception as e:
        logger.error(f"Failed to trigger hibernation: {e}")


if __name__ == "__main__":
    # If called directly, check and hibernate
    if was_woken_by_automation():
        hibernate_now()
    else:
        logger.info("PC will stay awake (User likely active).")
