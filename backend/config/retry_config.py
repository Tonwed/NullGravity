"""
Retry Configuration for API Proxy

Configure intelligent retry behavior for capacity exhaustion errors.
"""

# Maximum number of retries for capacity exhaustion errors
# When a model returns MODEL_CAPACITY_EXHAUSTED or CAPACITY_EXHAUSTED,
# the proxy will retry the request with the same account up to this many times.
MAX_CAPACITY_RETRIES = 3

# Delay between retries in seconds
# After a capacity exhaustion error, wait this many seconds before retrying.
# You can use exponential backoff by setting different delays per attempt.
CAPACITY_RETRY_DELAY = 1.0  # seconds

# Whether to use exponential backoff
# If True, delay will increase: 1s, 2s, 4s, etc.
# If False, delay will be constant: 1s, 1s, 1s, etc.
USE_EXPONENTIAL_BACKOFF = False

# Maximum delay for exponential backoff (in seconds)
# Only used if USE_EXPONENTIAL_BACKOFF is True
MAX_BACKOFF_DELAY = 10.0


def get_retry_delay(attempt: int) -> float:
    """
    Calculate retry delay based on attempt number.
    
    Args:
        attempt: Current retry attempt (0-indexed)
    
    Returns:
        Delay in seconds before next retry
    """
    if USE_EXPONENTIAL_BACKOFF:
        # Exponential backoff: 1s, 2s, 4s, 8s, etc.
        delay = CAPACITY_RETRY_DELAY * (2 ** attempt)
        return min(delay, MAX_BACKOFF_DELAY)
    else:
        # Constant delay
        return CAPACITY_RETRY_DELAY
